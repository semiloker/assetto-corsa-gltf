#!/usr/bin/env python3
"""Look at an Assetto Corsa car before you import it, and pick its colour.

    kn5-studio "<...>/content/cars/ks_mazda_mx5_nd/ks_mazda_mx5_nd.kn5"
    kn5-studio <car.kn5> --out build/import --port 8731 --no-open

Converts the car with kn5_to_gltf, serves the result to a local page and opens
it. The page turns the model round; clicking a livery re-converts and reloads.
Ctrl-C stops it. Nothing is written outside `--out`.

WHY A BROWSER. The conversion has always lived in Python and the engine has
never needed to know about kn5. A viewer in the engine would have inverted that
- it would put an Assetto Corsa panel, a process launcher and a staging folder
into the editor to answer a question the editor has no stake in. A browser is a
glTF renderer that is already installed and already right: PBR, sRGB, tone
mapping, mipmaps, an orbit camera. three.js is vendored beside this file, so
there is no network dependency and no CDN moving under the tool.

WHY IT RE-CONVERTS RATHER THAN RE-TINTING. On a Kunos road car the paint is not
a texture the page could swap - it is a base-colour FACTOR the converter derives
from the livery's flat detail map (see kn5_to_gltf.detail_tint). Changing colour
therefore changes the glTF, and the honest way to show the result is to produce
it. A conversion is a few seconds and the page says it is working.

Conversions run IN THIS PROCESS, not through a subprocess: kn5_to_gltf is a
module, so there is nothing to quote, nothing to find on PATH, and a traceback
arrives as a traceback.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import threading
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

from . import convert as K
from . import __version__

VIEWER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'viewer')


def main_kn5(folder, car_id):
    """The car's TOP-DETAIL model in `folder`, or None if there is no car in it.

    Every kn5 in a car folder is a valid kn5 and every one of them converts, so
    picking the wrong file fails SILENTLY - the result is a car with no interior,
    or a car that is eight boxes, and it reads as a broken converter rather than
    as the wrong input. Three shapes, in this order:

      `<car_id>.kn5`     the older Kunos layout and most mods.
      `*_lod_a.kn5`      the current one, and the trap: AC's top LOD is lod_A,
                         so a rule that skips everything with `_lod_` in it
                         skips the actual car. On ks_mazda_mx5_nd there is no
                         file named after the folder at all - it is
                         mazda_mx5_lod_a.kn5 - and the naive rule fell through
                         to `collider.kn5`, which is eight boxes.
      anything else      first by name, LODs and the collider excluded.

    `collider.kn5` is never the answer: it is the physics hull AC drives, not
    the model it draws.
    """
    try:
        names = sorted(f for f in os.listdir(folder) if f.lower().endswith('.kn5'))
    except OSError:
        return None
    names = [f for f in names if os.path.splitext(f)[0].lower() != 'collider']
    exact = [f for f in names if os.path.splitext(f)[0].lower() == car_id.lower()]
    if exact:
        return os.path.join(folder, exact[0])
    lod_a = [f for f in names if f.lower().endswith('_lod_a.kn5')]
    if lod_a:
        return os.path.join(folder, lod_a[0])
    # SHORTEST name, then alphabetical. The LOD suffix zoo is wider than
    # `_lod_`: this install alone has `_LOD_B`, `_LOD_1`, `_B`, and `grB`. What
    # they all share is that a LOD's name is its base name plus something, so
    # the base is the short one - and where they are all the same length
    # (mazda_mx5_lod_a/b/c/d) alphabetical picks A, which is the top LOD anyway.
    plain = [f for f in names if '_lod_' not in f.lower()]
    plain.sort(key=lambda f: (len(f), f))
    return os.path.join(folder, plain[0]) if plain else None


def find_cars(target):
    """[(id, kn5 path)] for a whole `content/cars` folder, or for one file.

    A folder is the normal way in: an install has a couple of hundred cars and
    naming the file for each of them is the part nobody wants to do. One file
    still works, because sometimes you already know which car you mean.
    """
    if os.path.isfile(target):
        return [(os.path.splitext(os.path.basename(target))[0],
                 os.path.abspath(target))]
    out = []
    for d in sorted(os.listdir(target)):
        folder = os.path.join(target, d)
        if not os.path.isdir(folder):
            continue
        k = main_kn5(folder, d)
        if k:
            out.append((d, os.path.abspath(k)))
    return out


class Studio:
    """The cars this run can show, and whatever has been converted of one."""

    def __init__(self, target, outdir, name):
        self.outdir = os.path.abspath(outdir)
        self.name_override = name
        self.cars = find_cars(target)
        self.car = None
        self.kn5 = None
        self.name = None
        self.report = {'car': '-', 'skins': []}
        self.current = None
        # Textures already written for the CURRENT car. A livery overrides three
        # maps out of fifty, and decoding the other forty-seven again is five of
        # the seven seconds a conversion takes - measured on bmw_z4: 5.92 s for
        # the first livery, 0.86 s for every one after it. Dropped when the car
        # changes, because then none of them apply.
        self.tex_cache = {}
        self.bake_cache = {}
        # Bumped on every conversion and appended to the glTF's URL as a query.
        # Everything is served no-store, so this is not the cache defence - it
        # is three.js's: GLTFLoader keys its own parsed result on the URL, and a
        # re-picked livery at the same URL would come back as the model it
        # already had. Which is the colour appearing not to change.
        self.version = 0
        self.lock = threading.Lock()
        # One car in, one car selected: naming a file is already the choice.
        if len(self.cars) == 1:
            self.select_car(self.cars[0][0])

    def select_car(self, car_id):
        """Point the studio at one car. Reading a kn5's materials is cheap
        (kn5.load(geometry=False)), so this is a folder listing plus a header
        parse - it is the CONVERSION that costs seconds, and that waits for a
        livery to be picked."""
        for cid, path in self.cars:
            if cid == car_id:
                self.car = cid
                self.kn5 = path
                self.name = self.name_override or cid
                self.report = K.skin_report(path)
                self.current = None
                self.tex_cache = {}
                self.bake_cache = {}
                return True
        return False

    def cars_json(self):
        return {'cars': [c for c, _ in self.cars], 'current': self.car}

    # ---- what the page asks for --------------------------------------------
    def skins_json(self):
        # The FOLDER name, not the kn5's. ks_mazda_mx5_nd is what the folder,
        # the AC UI and this tool's own picker all call the car;
        # mazda_mx5_lod_a is a filename nobody chose.
        out = {'car': self.car or self.report['car'], 'current': self.current,
               'selected': self.car, 'skins': []}
        if self.report.get('error'):
            out['error'] = self.report['error']
            return out
        for sk in self.report['skins']:
            top = sk['colours'][0] if sk['colours'] else None
            out['skins'].append({
                'name': sk['name'],
                'hex': ('%02X%02X%02X' % tuple(top['rgb'])) if top else None,
                'material': top['material'] if top else None,
                'source': top['source'] if top else None,
            })
        return out

    def paint_line(self, skin):
        """The one line under the swatches: what this livery actually painted.

        `from the kn5` is the important case and the reason the source is
        carried this far - it means the livery does not ship that texture, so
        the body wears the export-time template and picking a different livery
        cannot change it. Without saying so the tool looks broken.
        """
        for sk in self.report['skins']:
            if sk['name'] != skin:
                continue
            if not sk['colours']:
                return 'no flat colour in this livery - its paint is a pattern'
            c = sk['colours'][0]
            return '%s  #%02X%02X%02X  (%d tris, %s)' % (
                c['material'], c['rgb'][0], c['rgb'][1], c['rgb'][2], c['tris'],
                'from the livery' if c['source'] == 'skin'
                else 'from the kn5, NOT the livery')
        return ''

    def convert(self, skin):
        """Convert with `skin` and return (url, warning). Serialised."""
        with self.lock:
            if not self.kn5:
                raise RuntimeError('no car selected')
            # A folder per car, so switching car cannot leave the previous
            # one's textures behind to be served as this one's.
            out = os.path.join(self.outdir, self.car)
            os.makedirs(out, exist_ok=True)
            K.convert([{'file': self.kn5, 'pos': [0.0] * 3, 'rot': [0.0] * 3}],
                      out, self.name, False, False, None,
                      skin=K.skin_dir(self.kn5, skin),
                      tex_cache=self.tex_cache, bake_cache=self.bake_cache)
            self.current = skin
            self.version += 1
            warn = ''
            for sk in self.report['skins']:
                if sk['name'] == skin and sk['colours'] \
                        and sk['colours'][0]['source'] != 'skin':
                    warn = ('this livery does not ship %s, so the body colour '
                            'came out of the kn5 and is the same for every skin'
                            % sk['colours'][0]['texture'])
            # The version is a query, not a path segment: the glTF names its
            # .bin and its images RELATIVELY, so a version in the path would
            # change their URLs too and re-download eight megabytes of geometry
            # that did not change. Everything is served no-store anyway; this
            # only stops the browser reusing a parsed glTF it already has.
            return ('/model/%s/%s.gltf?v=%d' % (self.car, self.name, self.version),
                    warn)


class Handler(SimpleHTTPRequestHandler):
    studio = None          # set on the class before the server starts

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def translate_path(self, path):
        """Map a URL onto one of exactly two roots, and nowhere else.

        SimpleHTTPRequestHandler serves the working directory, which here is the
        whole repository. Two explicit prefixes instead: the vendored viewer and
        the output folder. Anything else is a 404 rather than a file.
        """
        p = urlparse(path).path
        parts = [unquote(x) for x in p.split('/') if x not in ('', '.', '..')]
        if not parts:
            return os.path.join(VIEWER_DIR, 'index.html')
        if parts[0] == 'viewer':
            return os.path.join(VIEWER_DIR, *parts[1:])
        if parts[0] == 'model':
            return os.path.join(Handler.studio.outdir, *parts[1:])
        return os.path.join(VIEWER_DIR, '__nothing__')

    def do_GET(self):
        route = urlparse(self.path).path
        if route == '/api/cars':
            self._json(Handler.studio.cars_json())
            return
        if route == '/api/car':
            q = parse_qs(urlparse(self.path).query)
            cid = (q.get('id') or [''])[0]
            if not Handler.studio.select_car(cid):
                self._json({'error': 'no car %r in this folder' % cid})
                return
            self._json(Handler.studio.skins_json())
            return
        if route == '/api/skins':
            self._json(Handler.studio.skins_json())
            return
        if route == '/api/select':
            q = parse_qs(urlparse(self.path).query)
            skin = (q.get('skin') or [''])[0]
            try:
                url, warn = Handler.studio.convert(skin)
            except SystemExit as e:            # kn5_to_gltf refuses some files
                print('! %s' % e)
                self._json({'error': str(e)})
                return
            except Exception as e:             # noqa: BLE001
                # To the terminal as well as to the page. A car that fails is
                # the one thing worth a traceback, and the page has room for a
                # sentence.
                import traceback
                traceback.print_exc()
                self._json({'error': '%s: %s' % (type(e).__name__, e)})
                return
            self._json({'url': url, 'warning': warn,
                        'paint': Handler.studio.paint_line(skin)})
            return
        SimpleHTTPRequestHandler.do_GET(self)

    def end_headers(self):
        # Nothing is cached. The files are rewritten in place under one name per
        # car, so a cached anything is a stale anything - and this is loopback,
        # where eight megabytes costs less than working out what changed.
        self.send_header('Cache-Control', 'no-store')
        SimpleHTTPRequestHandler.end_headers(self)

    def log_message(self, fmt, *args):
        # The converter's own output is the interesting thing in this terminal.
        # A request log per texture would bury it.
        pass


def main():
    ap = argparse.ArgumentParser(prog='kn5-studio', description=__doc__.splitlines()[0])
    ap.add_argument('target', metavar='CAR-OR-FOLDER',
                    help="either one .kn5, or a whole content/cars folder - in "
                         "which case the page gets a car picker and nothing is "
                         "converted until you choose one")
    ap.add_argument('--out', default=None,
                    help='keep the converted glTF here. WITHOUT this nothing is '
                         'kept: the conversion goes to a temporary folder that '
                         'is deleted when the tool stops, because looking at a '
                         'car is not the same as importing it and browsing '
                         'twenty of them should not leave twenty on disk.')
    ap.add_argument('--name', default=None, help='basename for the .gltf')
    ap.add_argument('--port', type=int, default=8731)
    ap.add_argument('--no-open', action='store_true',
                    help='do not launch a browser; just print the URL')
    ap.add_argument('--version', action='version',
                    version='%(prog)s ' + __version__)
    a = ap.parse_args()

    if not os.path.exists(a.target):
        sys.exit('no such file or folder: %s' % a.target)

    # No --out: a temp folder, gone on exit. The browser needs FILES - it
    # cannot be handed a glTF over a pipe - so something has to be written; what
    # is avoidable is it surviving the session.
    tmp = None
    outdir = a.out
    if not outdir:
        tmp = tempfile.mkdtemp(prefix='kn5studio-')
        outdir = tmp

    studio = Studio(a.target, outdir, a.name)
    if not studio.cars:
        sys.exit('no .kn5 under %s - point this at a car or at content/cars'
                 % a.target)
    print('cars   : %d' % len(studio.cars))
    if studio.car:
        if studio.report.get('error'):
            # Still serve: the page shows the reason, which beats a traceback.
            print('! %s: %s' % (studio.report['car'], studio.report['error']))
        else:
            print('car    : %s' % studio.report['car'])
            print('skins  : %s'
                  % ', '.join(sk['name'] for sk in studio.report['skins']))

    Handler.studio = studio
    srv = ThreadingHTTPServer(('127.0.0.1', a.port), Handler)
    url = 'http://127.0.0.1:%d/' % a.port
    print('output : %s%s' % (outdir, '   (temporary - deleted on exit)' if tmp
                              else '   (kept: --out)'))
    print('serving: %s   (Ctrl-C to stop)' % url)
    if not a.no_open:
        threading.Timer(0.3, webbrowser.open, (url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('')
    finally:
        srv.server_close()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
            print('removed: %s' % tmp)
    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
