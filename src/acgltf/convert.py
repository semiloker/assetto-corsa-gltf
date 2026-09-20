#!/usr/bin/env python3
"""kn5 -> glTF 2.0, keeping every node.

Assetto Corsa ships cars AND tracks in `kn5`, a plain container. This reads the
whole node tree and writes a glTF whose hierarchy MATCHES IT ONE FOR ONE, because
the hierarchy is the useful part: a car's 250-odd empty nodes are its wheel
centres, suspension pickups, steering column and door hinges, already positioned,
and a track's mesh names carry its physics surfaces. A converter that flattens
the tree throws that away and leaves a lump of triangles.

    # a car — one kn5
    kn5-to-gltf <car.kn5> <outdir> [--name NAME] [--skin NAME]

    # a track — several kn5 placed by a models_*.ini
    kn5-to-gltf --models <models_east.ini> <outdir> --name mulholland
                                [--surfaces <data/surfaces.ini>]

Refuses files carrying the CSP encryption trailer: on those the textures and
several meshes in the plain section are decoys (1x1 PNGs and 6 cm cubes), so a
"successful" conversion would silently produce a car with boxes for wheels.

Axes. kn5 is +X left, +Z forward, right-handed with CCW winding — measured, not
assumed: the signed volume of the closed body shells and all four tyres comes out
positive. glTF is +X right, -Z forward, also right-handed CCW. The two differ by
a half turn about Y, which has determinant +1, so it goes on the root node as a
matrix and NO winding or normal has to be touched.
"""
import argparse
import io
import json
import math
import os
import re
import struct
import sys

from . import kn5
from . import __version__

# Written into asset.generator, so a file can be traced back to the tool
# and the version that produced it.
GENERATOR = 'assetto-corsa-gltf %s' % __version__


# --- glTF constants ---------------------------------------------------------
FLOAT, USHORT, UINT = 5126, 5123, 5125
ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 34962, 34963
IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]

# Runtime VARIANTS: meshes AC swaps in and out, which a static glTF cannot.
# Exported alongside the originals they do not read as extra detail, they read as
# a broken model — the damage shells sit a fraction of a millimetre off the clean
# panels and z-fight with them, and the blurred wheels are opaque discs over the
# spokes. Dropped by default, subtree and all.
VARIANT_RE = re.compile(r'BLUR|DAMAGE', re.I)


def lowres_twins(names):
    """The in-file LOD pairs: names whose `_HR` partner is also present.

    Separate lod_a/lod_b/lod_c files are not the whole story. AC also ships two
    versions of the cockpit and the steering wheel INSIDE the top LOD --
    COCKPIT_HR/COCKPIT_LR, STEER_HR/STEER_LR -- and swaps them at runtime by
    camera. 192 of the 215 readable cars here do it. Exported together they
    overlap: two dashboards and two steering wheels in the same place.

    The partner test is the whole trick, and it is not decoration. `_LR` is
    LEFT REAR far more often than it is low-res -- WHEEL_LR, SUSP_LR, RIM_LR,
    DISC_LR, SPRING_LR, ROLL_BAR_LR -- so a rule that matched the suffix alone
    would take a corner of the suspension off every car. None of those has an
    `_HR` twin; every genuine LOD name does.
    """
    have = {n.lower() for n in names}
    return {n for n in names
            if n.lower().endswith('_lr') and n[:-3].lower() + '_hr' in have}


def scrub(rows, fallback):
    """Replace non-finite vertex attributes in place; return how many.

    Real kn5 files carry NaN — the Honda's dash-light meshes have NaN tangents
    and three of its dummies have an all-NaN matrix. Left alone they reach the
    JSON, and Python writes a bare `NaN` token there, which is not valid JSON:
    the file parses in Python and is rejected by every glTF loader.
    """
    bad = 0
    for i, r in enumerate(rows):
        if not all(math.isfinite(c) for c in r):
            rows[i] = fallback(i)
            bad += 1
    return bad


def perp(v):
    """Any unit vector perpendicular to `v` — a stand-in for a lost tangent."""
    if not all(math.isfinite(c) for c in v):
        return [1.0, 0.0, 0.0]
    a = [1.0, 0.0, 0.0] if abs(v[0]) < 0.9 else [0.0, 1.0, 0.0]
    t = [a[1] * v[2] - a[2] * v[1],
         a[2] * v[0] - a[0] * v[2],
         a[0] * v[1] - a[1] * v[0]]
    n = math.sqrt(sum(c * c for c in t)) or 1.0
    return [c / n for c in t]


class Buf:
    """The single .bin, plus the bufferViews/accessors that index into it."""

    def __init__(self):
        self.data = bytearray()
        self.views = []
        self.accessors = []

    def _view(self, blob, target):
        while len(self.data) % 4:
            self.data.append(0)
        off = len(self.data)
        self.data += blob
        self.views.append({'buffer': 0, 'byteOffset': off,
                           'byteLength': len(blob), 'target': target})
        return len(self.views) - 1

    def floats(self, rows, ncomp):
        flat = []
        for r in rows:
            flat.extend(r)
        v = self._view(struct.pack('<%df' % len(flat), *flat), ARRAY_BUFFER)
        self.accessors.append({
            'bufferView': v, 'componentType': FLOAT, 'count': len(rows),
            'type': {2: 'VEC2', 3: 'VEC3', 4: 'VEC4'}[ncomp],
            'min': [min(r[i] for r in rows) for i in range(ncomp)],
            'max': [max(r[i] for r in rows) for i in range(ncomp)]})
        return len(self.accessors) - 1

    def indices(self, idx):
        big = max(idx) > 65535 if idx else False
        fmt, ctype = ('<%dI', UINT) if big else ('<%dH', USHORT)
        v = self._view(struct.pack(fmt % len(idx), *idx), ELEMENT_ARRAY_BUFFER)
        self.accessors.append({'bufferView': v, 'componentType': ctype,
                               'count': len(idx), 'type': 'SCALAR'})
        return len(self.accessors) - 1


# ---------------------------------------------------------------------------
#  AC's two .ini files
# ---------------------------------------------------------------------------
def read_ini(path):
    """AC ini: [SECTION] then KEY=VALUE.

    Hand-rolled rather than configparser, which objects to all three things
    these files do: duplicate keys, empty values, and `%` in a value.
    """
    out, cur = [], None
    for line in io.open(path, encoding='utf-8', errors='replace'):
        line = line.strip()
        if not line or line.startswith(';') or line.startswith('//'):
            continue
        if line.startswith('['):
            cur = (line.strip('[]'), {})
            out.append(cur)
        elif cur is not None and '=' in line:
            k, v = line.split('=', 1)
            cur[1][k.strip().upper()] = v.strip()
    return out


def read_models_ini(path):
    """[MODEL_n] FILE / POSITION / ROTATION -> the list of kn5 that make a track."""
    base = os.path.dirname(os.path.abspath(path))
    out = []
    for sec, kv in read_ini(path):
        if not sec.upper().startswith('MODEL') or 'FILE' not in kv:
            continue

        def triple(key, kv=kv):
            raw = kv.get(key, '0,0,0').split(',')[:3]
            try:
                v = [float(x) for x in raw]
            except ValueError:
                return [0.0, 0.0, 0.0]
            return v + [0.0] * (3 - len(v))
        out.append({'file': os.path.join(base, kv['FILE']),
                    'pos': triple('POSITION'), 'rot': triple('ROTATION')})
    return out


def read_surfaces_ini(path):
    """[SURFACE_n] KEY=... -> {KEY: properties}.

    Only the fields a collider or a grip model can act on; the rest of the block
    is sound and force feedback.
    """
    out = {}
    for sec, kv in read_ini(path):
        if not sec.upper().startswith('SURFACE') or 'KEY' not in kv:
            continue

        def f(k, d=0.0, kv=kv):
            try:
                return float(kv.get(k, d))
            except ValueError:
                return d
        out[kv['KEY'].upper()] = {
            'friction': f('FRICTION', 1.0),
            'damping': f('DAMPING'),
            'dirtAdditive': f('DIRT_ADDITIVE'),
            'validTrack': f('IS_VALID_TRACK') != 0.0,
            'pitlane': f('IS_PITLANE') != 0.0,
            'vibrationGain': f('VIBRATION_GAIN'),
        }
    return out


def classify_surface(node_name, keys):
    """What a track mesh is to the physics, from its name.

    Returns (kind, detail):
      ('visual',  None)  no leading digit — scenery, the solver never sees it
      ('wall',    prefix) a barrier. WALL is not a surface and is deliberately
                          absent from surfaces.ini: it has no friction, it is
                          something you hit.
      ('surface', KEY)   matched a surfaces.ini key
      ('default', prefix) physics on, but the prefix names no key. AC falls back
                          to the track default for these, and there are a lot of
                          them — Mulholland has 97 meshes prefixed DIRT and 15
                          GRASS with neither key defined. Reported rather than
                          silently dropped, because a caller may well want to
                          give DIRT its own friction.

    The key match takes the LONGEST key that fits: the keys overlap (this track
    defines both ROAD and RDOLD, others define ASPH and ASPHNEW) and a shortest
    match would swallow every mesh of the longer one.
    """
    m = re.match(r'^\d+(.*)$', node_name)
    if not m:
        return ('visual', None)
    rest = m.group(1).upper()
    if rest.startswith('WALL'):
        return ('wall', rest)
    best = None
    for k in keys:
        if rest.startswith(k) and (best is None or len(k) > len(best)):
            best = k
    if best:
        return ('surface', best)
    return ('default', re.match(r'^[A-Z_]*', rest).group(0) or rest)


def skin_dir(kn5_path, want):
    """The `skins/<name>` folder to take textures from, or None.

    THIS IS WHY AN IMPORTED CAR WAS WHITE. A livery in Assetto Corsa lives
    OUTSIDE the model. The kn5 carries whichever skin happened to be loaded when
    it was exported -- on ks_mazda_mx5_nd that is the untouched grey template,
    `Skin_00.dds` averaging (174,174,174) -- and at load time the game replaces
    it, by filename, with the contents of `skins/<chosen>/`. A converter that
    reads only the container therefore gets the template every single time, and
    the car arrives in primer no matter which colour the folder next door holds.

    Default is the first folder, which is what AC itself picks when nothing says
    otherwise (the MX-5's is `00_soul_red_metallic`). `--skin none` keeps the
    embedded textures. Tracks have no skins directory, so this is a no-op there.
    """
    if want == 'none':
        return None
    root = os.path.join(os.path.dirname(os.path.abspath(kn5_path)), 'skins')
    if not os.path.isdir(root):
        return None
    have = sorted(d for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d)))
    if want:
        hit = next((d for d in have if d.lower() == want.lower()), None)
        if hit is None:
            sys.exit('no skin %r in %s -- have: %s'
                     % (want, root, ', '.join(have)))
        return os.path.join(root, hit)
    return os.path.join(root, have[0]) if have else None


# The bodywork, named. Half of this library labels it (108 of 217 cars have a
# *carpaint* material) and the other half does not, so this is a preference and
# never the only test - the triangle count still decides inside a band.
PAINT_HINT = re.compile(r'car[_ ]?paint|(?:^|[^a-z])body(?:[^a-z]|$)|chassis', re.I)
# ...and the things a car is painted BESIDE, which is the half that matters. A
# rim is a painted material on most Kunos cars and on the MX-5 it carries 33 024
# triangles against the bodywork's 23 554 - so "the biggest painted material"
# picks the WHEELS, and the colour picker offers a grey that never changes.
NOT_BODY = re.compile(r'rim|wheel|tyre|tire|brake|calip|disc|glass|window|'
                      r'light|lamp|badge|logo|plate|mirror|seat|interior|'
                      r'cockpit|dash|carpet|leather|belt|driver|steer|engine|'
                      r'exhaust|grill|plastic|chrome|rubber|shadow', re.I)


def paint_rank(name):
    """Sort key band for a painted material: lower is more likely the bodywork.

    Three bands, and the middle one is why this is not just a name match: on the
    109 cars that do not label their paint, an unrecognised name still beats a
    name that positively says wheel.
    """
    low = name.lower()
    # An interior copy of the paint (INT_OCC_Carpaint) is the same colour on the
    # inside of the same panels; the exterior is the one to show.
    inside = 1 if low.startswith('int') else 0
    if NOT_BODY.search(low):
        return (2, inside)
    if PAINT_HINT.search(low):
        return (0, inside)
    return (1, inside)


def paint_slots(materials, tris):
    """(index, name, txDetail) for every material that HAS a paint slot,
    bodywork first.

    useDetail is AC's own switch: without it the shader never samples txDetail,
    so whatever sits in that slot is not on screen and must not be offered as a
    colour of anything.

    The ORDER is a contract, not a nicety: everything downstream takes slot 0 as
    "the car's colour" - the --list-skins swatch, the studio's picker, the line
    under it. A car has a dozen painted materials and one of them is the
    bodywork.

    Ordering by triangle count alone was wrong, and wrong in the way that looks
    like a broken tool rather than a wrong sort: on ks_mazda_mx5_nd the rims
    carry 33 024 triangles and the bodywork 23 554, so every livery in the
    picker showed the RIM's grey - which comes out of the kn5, not the skin, and
    is therefore identical for all seven. Changing colour appeared to do
    nothing. Name first, then size inside the band.
    """
    out = [(i, m['name'], m['textures'].get('txDetail', ''))
           for i, m in enumerate(materials)
           if m['textures'].get('txDetail', '') and m['props'].get('useDetail', 0.0) > 0.0]
    out.sort(key=lambda t: paint_rank(t[1]) + (-tris.get(t[0], 0),))
    return out


def skin_report(kn5_path):
    """Every livery the car ships, and the colour each one paints it.

    The editor's import panel needs two things before it converts anything:
    what the choices ARE, and what each one looks like. Both live in the car
    folder rather than in the model - see skin_dir - so neither can be answered
    by opening the kn5 alone, and neither should be re-implemented in C++: the
    "double, then linearise" arithmetic and the flat-colour test are subtle
    enough that a second copy would drift from this one within a month.

    Geometry is skipped (`geometry=False`): this reads material names, texture
    slots and triangle counts, which is the difference between listing a car in
    a fraction of a second and unpacking forty megabytes of vertices to throw
    them away. The triangle counts are here to ORDER the answer - a car has a
    dozen painted materials and only one of them is the bodywork, and the
    bodywork is the one with the triangles. So colours[0] is the car's colour
    and the panel can draw it as the swatch without knowing anything about AC.

    `none` is listed last as a real choice, because it is one: it means keep the
    textures embedded in the kn5, which is the export-time template - usually
    grey primer, occasionally the colour the artist happened to have loaded.
    """
    model = kn5.load(kn5_path, geometry=False)
    fold_texture_case(model)
    out = {'car': os.path.splitext(os.path.basename(kn5_path))[0],
           'encrypted': bool(model.encrypted), 'skins': []}
    if model.encrypted:
        out['error'] = ('carries the CSP kn5 encryption trailer - its textures '
                        'are decoys, so no colour here would be the real one')
        return out

    tris = {}
    for n, _ in model.walk():
        if n.type in (kn5.MESH, kn5.SKINNED) and n.material >= 0 and n.ntris:
            tris[n.material] = tris.get(n.material, 0) + n.ntris

    painted = paint_slots(model.materials, tris)

    root = os.path.join(os.path.dirname(os.path.abspath(kn5_path)), 'skins')
    names = (sorted(d for d in os.listdir(root)
                    if os.path.isdir(os.path.join(root, d)))
             if os.path.isdir(root) else [])

    own = {t[0]: t[2] for t in model.textures}
    # Keyed by the FILE the colour comes from, not by the material. Several
    # materials share one detail map - EXT_Carpaint, INT_OCC_Carpaint and
    # INT_LR_carpaint are all metal_detail.dds - so without this every livery
    # decodes the same DDS once per material that wears it, and a car with
    # thirty liveries spends most of a minute decoding the same few textures
    # over and over.
    seen = {}

    def colour_of(key, blob):
        if key not in seen:
            seen[key] = flat_colour(blob)
        return seen[key]

    for skin in names + [None]:
        over = {}
        if skin is not None:
            d = os.path.join(root, skin)
            over = {f.lower(): os.path.join(d, f) for f in os.listdir(d)}
        entry = {'name': skin if skin is not None else 'none', 'colours': []}
        for mi, mname, dds in painted:
            path = over.get(dds.lower())
            if path and os.path.isfile(path):
                key, src = path, 'skin'
                blob = None if key in seen else open(path, 'rb').read()
            else:
                key, src, blob = 'kn5:' + dds, 'kn5', own.get(dds)
            c = colour_of(key, blob)
            if c is None:
                continue                    # a grain or a pattern, not a colour
            entry['colours'].append({'material': mname, 'texture': dds,
                                     'rgb': c[0], 'tris': tris.get(mi, 0),
                                     'source': src})
        out['skins'].append(entry)
    return out


def print_skins(report):
    """skin_report as TAB-separated lines. Returns the process exit code.

    Lines, not JSON, and that is a decision rather than laziness. The consumer
    is the editor's import panel, which is C++: JSON there means pulling a
    25 000-line header into a build that has never needed one, to read a
    document with two fields in it. A tab-separated line is fifteen lines of
    parsing, greppable, awk-able, and readable in a terminal without a tool.

        # car  ks_mazda_mx5_nd
        skin<TAB>NAME<TAB>MATERIAL<TAB>RRGGBB<TAB>TRIS<TAB>skin|kn5

    One line per painted material, skins in the order AC would offer them and
    materials biggest-first within each - so the FIRST line of a skin is its
    bodywork, and a caller that wants one swatch per livery takes exactly that.
    Anything else on stdout starts with '#' and can be ignored wholesale.
    """
    print('# car\t%s' % report['car'])
    if report.get('error'):
        sys.stderr.write('%s: %s\n' % (report['car'], report['error']))
        return 1
    for sk in report['skins']:
        if not sk['colours']:
            # A livery whose paint is a pattern rather than a colour is still a
            # livery - it just has no swatch. Saying so beats omitting it and
            # leaving the panel to imply the car does not have it.
            print('skin\t%s\t-\t-\t0\t-' % sk['name'])
            continue
        for c in sk['colours']:
            print('skin\t%s\t%s\t%02X%02X%02X\t%d\t%s'
                  % (sk['name'], c['material'], c['rgb'][0], c['rgb'][1],
                     c['rgb'][2], c['tris'], c['source']))
    return 0


def describe_paint(model, dds, use_detail, swapped):
    """One line saying what this material's paint slot resolved to, or why not.

    Every reason a body can come out the wrong colour is one of these, and
    without them the failure is indistinguishable: the car is white, or black,
    or the same as it was, and nothing on screen says whether the livery lacked
    the texture, the shader ignores the slot, or the map is a pattern.
    """
    if not dds:
        return 'no txDetail slot - this material has no paint to change'
    tag = dds + ('*' if dds in swapped else '')
    if use_detail <= 0.0:
        return '%s  IGNORED: useDetail is 0, the shader never samples it' % tag
    blob = next((x[2] for x in model.textures if x[0] == dds), None)
    if not blob or len(blob) < 128:
        return '%s  NO TINT: not in the container (encrypted, or a stub)' % tag
    c = flat_colour(blob)
    if c is None:
        return '%s  NO TINT: the map varies - a pattern, not one colour' % tag
    return '%s  #%02X%02X%02X  (useDetail %.2f)' % (tag, c[0][0], c[0][1],
                                                    c[0][2], use_detail)


def print_materials(model, gltf_mats, mat_base, tex_files, swapped, keeps_alpha):
    """What every material ACTUALLY got, and where each half of it came from.

    The report that answers the two questions a colour change raises and
    nothing else could:

      "I changed the livery and the body did not change."  Look for a `*` on
      the body's detail texture. No star means the livery does not ship that
      texture at all, so the tint came out of the kn5 and is the same for every
      skin - the change was never going to reach the bodywork.

      "I changed the livery and the car went black."  Look at the FACTOR. glTF
      multiplies it into the diffuse, so a factor near zero is a black car
      however bright the texture is, and the paint line above says which texture
      produced it. A genuinely dark livery reads the same way, which is the
      point: the report tells you the two apart by naming the colour.
    """
    print('')
    print('materials: %d   (* = the chosen skin overrides this texture)'
          % len(model.materials))
    for i, m in enumerate(model.materials):
        p, t = m['props'], m['textures']
        pbr = gltf_mats[mat_base + i]['pbrMetallicRoughness']
        f = pbr['baseColorFactor']
        print('  %-26s %s' % (m['name'], m['shader']))
        dds = t.get('txDiffuse', '')
        if dds:
            png = tex_files.get(dds)
            print('    diffuse   %s%s -> %s%s'
                  % (dds, '*' if dds in swapped else '',
                     png or 'NOT WRITTEN (missing, encrypted, or a stub)',
                     '   [alpha kept]' if dds in keeps_alpha else ''))
        else:
            print('    diffuse   (none)')
        print('    paint     %s' % describe_paint(model, t.get('txDetail', ''),
                                                  p.get('useDetail', 0.0), swapped))
        print('    factor    %.4f %.4f %.4f    roughness %.3f'
              % (f[0], f[1], f[2], pbr['roughnessFactor']))


def fold_texture_case(model):
    """Collapse texture entries that differ only in case; point the materials at
    the spelling that survives. Returns how many entries were folded away.

    Assetto Corsa is a Windows game and matches texture names case-insensitively,
    so a car can carry `INT_DEcals.dds` in its texture table, ask a material for
    `INT_Decals.dds`, and render fine. ks_mazda_mx5_nd does exactly that, and it
    is not the only one -- sloppy case costs a modder nothing because nothing
    ever tells them.

    Written out literally it costs the IMPORT everything: the glTF names an image
    that exists on disk only under a different capitalisation. On Windows it
    still loads, by accident, which is why this went unnoticed; on Linux, on
    macOS, and in any browser fetching from a case-sensitive server the material
    arrives untextured. Two entries can also collide into one file on a
    case-insensitive disk, so one of them was being silently overwritten by the
    other.

    The surviving entry is the one with the LARGEST blob. The two are the same
    texture as far as the game is concerned, and the bigger one is never the
    1x1 placeholder.
    """
    keep = {}
    for i, (name, _active, data) in enumerate(model.textures):
        k = name.lower()
        if k not in keep or len(data) > len(model.textures[keep[k]][2]):
            keep[k] = i
    folded = len(model.textures) - len(keep)
    canon = {k: model.textures[i][0] for k, i in keep.items()}
    model.textures = [model.textures[i] for i in sorted(keep.values())]
    for m in model.materials:
        for slot, want in list(m['textures'].items()):
            have = canon.get(want.lower())
            if have is not None and have != want:
                m['textures'][slot] = have
    return folded


def apply_skin(model, skin):
    """Overwrite kn5 texture blobs with the same-named files from `skin`.

    Done to the model up front rather than inside save_textures because the
    livery is not only the albedo: the skin folder also ships `*_MAP.dds`, which
    bake_roughness reads straight out of `model.textures`, and on some cars the
    plate and badge sheets too. Patching the container once means every consumer
    downstream sees the chosen skin without knowing skins exist.

    Returns the SET of texture names it replaced. len() of that is the count the
    caller used to print, and the names themselves are what --materials needs:
    "the body did not change colour when I changed livery" is answered by
    whether that livery overrides the body's detail map AT ALL, and nothing
    else in the pipeline knows.
    """
    if not skin:
        return set()
    over = {f.lower(): os.path.join(skin, f) for f in os.listdir(skin)}
    swapped = set()
    for i, (name, active, _data) in enumerate(model.textures):
        path = over.get(name.lower())
        if path and os.path.isfile(path):
            with open(path, 'rb') as fh:
                model.textures[i] = (name, active, fh.read())
            swapped.add(name)
    return swapped


def save_textures(model, outdir, used, written, keeps_alpha=frozenset(),
                  force=frozenset()):
    """Decode the DDS blobs to PNG beside the glTF. Only what a material asks for.

    Alpha is dropped unless a material actually reads it, which in AC means the
    material is alpha-blended or alpha-tested (`keeps_alpha`). Two reasons, and
    the second one is not an optimisation:

    - most of these maps carry a fully-white alpha that costs a third of the file
      for nothing;
    - and some carry a fully BLACK one. AC's shader does not sample alpha on an
      opaque material, so nothing in the game ever noticed that the Lancer's
      carpaint_evo, seatsao, dashao and nine others decode to a completely
      transparent image. A PBR renderer samples it, and the car arrived with no
      paint and no interior — the texture was there, and invisible.

    `written` is shared across the models of a track, so a texture used by five
    of its kn5 is decoded once. `force` re-decodes anyway, which is what makes
    changing livery cheap: a skin overrides three textures out of fifty, the
    other forty-seven are already on disk and identical, and decoding them again
    is five seconds of a seven-second conversion spent to produce the same
    bytes.
    """
    from PIL import Image
    Image.init()
    for name, active, data in model.textures:
        # `len(data) < 128` is the stub test -- an encrypted or placeholder
        # entry. It stays AFTER apply_skin on purpose: the Evo III's embedded
        # body texture is a 192-byte flat colour and the real one is in the skin
        # folder, so the gate has to see the blob that will actually be written.
        if name not in used or len(data) < 128:
            continue
        if name in written and name not in force:
            continue
        try:
            im = Image.open(io.BytesIO(data))
            im.load()
        except Exception as e:                     # noqa: BLE001
            print('  ! %s: %s' % (name, e))
            continue
        if im.mode in ('RGBA', 'LA', 'PA'):
            if name not in keeps_alpha:
                im = im.convert('RGB')          # opaque material: alpha is noise
            elif im.getchannel('A').getextrema() == (255, 255):
                im = im.convert('RGB')          # ...or it is uniformly opaque
        elif im.mode not in ('RGB', 'L'):
            im = im.convert('RGBA')
        png = os.path.splitext(name)[0] + '.png'
        im.save(os.path.join(outdir, png), 'PNG', compress_level=6)
        written[name] = png
    return written


def flat_colour(blob):
    """(srgb_bytes, linear_factor) if this texture is ONE colour, else None.

    Split out of detail_tint so the paint arithmetic has exactly one home: the
    converter needs the linear glTF factor, and the skin listing needs the
    8-bit colour to draw a swatch with. Two copies of "double, then linearise"
    would drift, and the order is the whole subtlety (see detail_tint).

    The 8-bit half is the texture's own colour, NOT the doubled one - a swatch
    should show the paint, and Ceramic Metallic at (148,148,148) doubles past
    white.
    """
    if not blob or len(blob) < 128:
        return None
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(blob))
        im.load()
        im = im.convert('RGB')
    except Exception:                              # noqa: BLE001
        return None
    # Extrema over the FULL image, deliberately not a downsample: box-averaging
    # first would flatten leather grain and brushed metal to a constant too, and
    # this then tints those parts by a mean the shader never showed. Only a map
    # that is one colour everywhere is one the whole material can wear.
    ext = im.getextrema()                           # ((rlo,rhi),(glo,ghi),(blo,bhi))
    if max(hi - lo for lo, hi in ext) > 6:          # not a flat colour
        return None
    srgb, lin = [], []
    for lo, hi in ext:
        mid = (lo + hi) * 0.5 / 255.0
        srgb.append(int(round(mid * 255.0)))
        c = min(2.0 * mid, 1.0)
        lin.append(round(c / 12.92 if c <= 0.04045
                         else ((c + 0.055) / 1.055) ** 2.4, 5))
    return srgb, lin


def detail_tint(model, dds, cache):
    """AC's txDetail as a base-colour factor, when it is a FLAT COLOUR.

    THIS IS WHERE A KUNOS ROAD CAR KEEPS ITS PAINT, and not knowing it is why an
    imported MX-5 arrived white. Its `skins/*/` folders contain no body texture
    at all: the diffuse (`Skin_00.dds`) is a shared panel/AO template, average
    grey 174, byte-identical for all seven liveries. What differs between them
    is `metal_detail.dds`, a single flat RGBA -- (126,1,0) Soul Red Metallic,
    (15,14,14) Jet Black Mica, (213,210,208) Arctic White, (30,33,36) Blue
    Reflex Mica. AC's ksPerPixelMultiMap multiplies it into the diffuse, so the
    "shader that produces the colour" is, for the body, literally this one texel.
    Drop the slot -- as this converter did -- and every car is the template.

    The doubling is AC's detail convention, not a fudge: a detail map is
    neutral at mid-grey, so it enters as `diffuse * detail * 2`. And it enters
    in GAMMA space, which is why the factor is linearised AFTER the doubling
    rather than before -- on Ceramic Metallic (148,148,148) the two orders
    differ by a stop and a half.

    Returns None when the map actually varies. Then it is a genuine detail or
    flake pattern -- the plastics and the interior leather use those -- and
    folding its mean in would tint the part by an arbitrary average.

    ponytail: the flat-colour case only. A varying detail map is still dropped,
    exactly as before; carry it as a second UV set if a car ever needs one.
    """
    if dds in cache:
        return cache[dds]
    cache[dds] = None
    blob = next((t[2] for t in model.textures if t[0] == dds), None)
    out = flat_colour(blob)
    if out is None:
        return None
    cache[dds] = out[1]
    return out[1]


def bake_roughness(model, outdir, cache, dds, spec_exp):
    """AC's txMaps -> a glTF metallicRoughness image, or None if it holds nothing.

    The slot is documented as R = specular intensity, G = glossiness. On every
    *_map measured so far G is a FLAT 255: there is no glossiness variation to
    carry over. R does vary, and it is the specular multiplier, which core glTF
    has no slot for.

    It converts, though, and not by hand-waving: a specular multiplier scales the
    peak of the Blinn lobe, which is what the exponent does, so folding it in as
    `exp * s` and running the same exponent->roughness conversion is the same
    arithmetic already used for the constant case. `spec_exp` arrives with the
    material's scalar ksSpecular already folded in, so this applies the per-pixel
    part on top of it — AC multiplies the two as well. At s = 1 it reproduces the
    constant exactly, so nothing that was right becomes wrong; below that the
    trim and rubber go matte, which is the flatness you can see.
    """
    from PIL import Image
    key = (dds, round(spec_exp, 2))
    if key in cache:
        return cache[key]
    blob = next((t[2] for t in model.textures if t[0] == dds), None)
    if not blob or len(blob) < 128:
        cache[key] = None
        return None
    try:
        im = Image.open(io.BytesIO(blob))
        im.load()
    except Exception:                              # noqa: BLE001
        cache[key] = None
        return None
    r = im.getchannel('R') if im.mode in ('RGB', 'RGBA') else im.convert('L')
    lut = []
    for v in range(256):
        s_ = max(v / 255.0, 0.02)
        lut.append(int(round(min(max((2.0 / (spec_exp * s_ + 2.0)) ** 0.5,
                                     0.04), 1.0) * 255)))
    zero = Image.new('L', im.size, 0)               # metallic = 0, dielectric
    out = Image.merge('RGB', (zero, r.point(lut), zero))
    fn = '%s_rough%d.png' % (os.path.splitext(dds)[0], int(spec_exp))
    out.save(os.path.join(outdir, fn), 'PNG', compress_level=6)
    cache[key] = fn
    return fn


def gen_normal(blob, outdir, cache, dds, strength, cap=1024):
    """Fabricate a tangent-space normal map from an albedo. None = not worth it.

    WHY THIS EXISTS. Mulholland has 136 materials and not one `txNormal`: 125 of
    them carry a diffuse and nothing else. The track is flat by construction, in
    AC too — AC hides it with its own shading. Under a PBR renderer that flatness
    is all you see, and no amount of tuning roughness puts it back.

    WHAT IT IS. Luminance read as height, Sobel for the slope, (-dh/du, dh/dv, 1)
    written out. Deliberately NOT normalised: every shader normalises the sampled
    normal anyway, so leaving it out turns per-pixel maths into three channel
    operations and makes a 4096-square texture a second rather than a minute.

    WHAT IT IS NOT. It is an inference from colour, not a measurement of shape.
    It is right where the albedo IS the surface — asphalt, gravel, brick, bark,
    grass — and wrong wherever the albedo is PAINT: a white lane line becomes a
    raised kerb, a logo becomes embossing. That is what `strength` is for, and
    why alpha-masked cutouts are skipped entirely: embossing the border of a leaf
    card puts relief on empty space.

    Capped at `cap` pixels. Relief is low-frequency, the diffuse is not, and the
    full 4096 square would double a folder that is already too big for what it
    adds.
    """
    from PIL import Image, ImageFilter
    key = (dds, round(strength, 3))
    if key in cache:
        return cache[key]
    cache[key] = None
    try:
        im = Image.open(io.BytesIO(blob))
        im.load()
    except Exception:                              # noqa: BLE001
        return None
    if min(im.size) < 64:                          # a swatch has no relief
        return None
    g = im.convert('L')
    if g.getextrema()[1] - g.getextrema()[0] < 8:  # flat colour, nothing to read
        return None
    if max(g.size) > cap:
        k = cap / float(max(g.size))
        g = g.resize((max(int(g.size[0] * k), 1), max(int(g.size[1] * k), 1)),
                     Image.LANCZOS)

    # Sobel, pre-negated on X so the output IS the normal channel rather than the
    # gradient. glTF normal maps are OpenGL convention (+Y up) and glTF's V grows
    # downward, which is the same direction the kernel differences in — so Y
    # needs no flip and X does.
    scale = max(4.0 / max(strength, 0.01), 0.2)
    nx = g.filter(ImageFilter.Kernel((3, 3), [1, 0, -1, 2, 0, -2, 1, 0, -1],
                                     scale=scale, offset=128))
    ny = g.filter(ImageFilter.Kernel((3, 3), [-1, -2, -1, 0, 0, 0, 1, 2, 1],
                                     scale=scale, offset=128))
    flat = Image.new('L', g.size, 255)              # z, before normalisation
    fn = '%s_gn.png' % os.path.splitext(dds)[0]
    Image.merge('RGB', (nx, ny, flat)).save(os.path.join(outdir, fn), 'PNG',
                                            compress_level=6)
    cache[key] = fn
    return fn


class Gltf:
    """Accumulates one glTF across however many kn5 go into it."""

    def __init__(self, outdir):
        self.outdir = outdir
        self.buf = Buf()
        self.nodes, self.meshes, self.materials = [], [], []
        self.images, self.textures = [], []
        self.tint_cache = {}
        self.tex_index, self.tex_files, self.bake_cache = {}, {}, {}
        self.gn_cache, self.gen_normals, self.n_generated = {}, 0.0, 0
        self.ext_used = set()
        self.stats = {'dummy': 0, 'mesh': 0, 'tris': 0, 'empty': 0,
                      'skipped': 0, 'nan': 0, 'nanmat': 0,
                      'folded': 0}
        self.mesh_names = []
        self.lowres = set()

    def _by_uri(self, uri):
        if uri is None:
            return None
        if uri not in self.tex_index:
            self.images.append({'uri': uri})
            self.textures.append({'source': len(self.images) - 1, 'sampler': 0})
            self.tex_index[uri] = len(self.textures) - 1
        return self.tex_index[uri]

    def add_materials(self, model):
        """AC shader parameters -> metallic-roughness, as close as the two get.

        AC is Blinn-Phong: a specular colour and an exponent. The exponent
        converts to a roughness properly; the specular COLOUR does not convert at
        all, so metallic stays 0 and painted metal comes out as a dielectric.
        That is the honest mapping — inventing a metalness from the specular
        intensity makes chrome out of every polished plastic.

        Returns the index this model's material 0 landed on: a track's kn5 each
        bring their own material list, and a mesh's material index is relative to
        its own file.
        """
        base = len(self.materials)
        for m in model.materials:
            p, t = m['props'], m['textures']
            exp = max(p.get('ksSpecularEXP', 20.0), 1.0)
            # ksSpecular is the INTENSITY, and ignoring it is why trees and grass
            # came out wet-looking: 56 of Mulholland's 61 materials set it to
            # 0.000 — no specular at all in AC — and every one of them was being
            # handed a full dielectric highlight at roughness 0.4.
            #
            # It folds in the same way the txMaps R channel does, and for the
            # same reason: an intensity multiplier scales the peak of the Blinn
            # lobe, which is what the exponent does. At ksSpecular 1 nothing
            # changes; at 0 the material goes matte, which is what it is.
            spec = p.get('ksSpecular', 1.0)
            # ksMultilayer parks its specular somewhere else: every one of
            # Mulholland's 14 multilayer materials sets ksSpecular to 0.0 and
            # drives the sheen from tarmacSpecularMultiplier instead. Taking
            # ksSpecular at face value there makes the ROAD as matte as the
            # grass beside it.
            #
            # fresnelMaxLevel is what separates them, and it is the author's own
            # switch: the road sets 0.45, the shoulder 1.0, and the grass does
            # not set it at all. So the multiplier only applies where a
            # reflection was asked for.
            if 'multilayer' in m['shader'].lower() and p.get('fresnelMaxLevel', 0.0) > 0.0:
                spec = max(spec, p.get('tarmacSpecularMultiplier', spec))
            eff = exp * max(spec, 0.02)
            rough = min(max((2.0 / (eff + 2.0)) ** 0.5, 0.04), 1.0)
            # The paint colour. See detail_tint: on these cars the diffuse
            # is a shared grey template and the livery is the flat txDetail.
            tint = (detail_tint(model, t.get('txDetail', ''), self.tint_cache)
                    if p.get('useDetail', 0.0) > 0.0 else None)
            pbr = {'baseColorFactor': (tint + [1]) if tint else [1, 1, 1, 1],
                   'metallicFactor': 0.0,
                   'roughnessFactor': round(rough, 4)}
            d = self._by_uri(self.tex_files.get(t.get('txDiffuse', '')))
            if d is not None:
                pbr['baseColorTexture'] = {'index': d}
            mr = bake_roughness(model, self.outdir, self.bake_cache,
                                t.get('txMaps', ''), eff)
            if mr:
                # A per-pixel roughness supersedes the constant, so the factor
                # goes to 1 — glTF MULTIPLIES the two.
                pbr['metallicRoughnessTexture'] = {'index': self._by_uri(mr)}
                pbr['roughnessFactor'] = 1.0
            mat = {'name': m['name'], 'pbrMetallicRoughness': pbr,
                   'doubleSided': False}
            # fresnelMaxLevel is AC's cap on how much a surface may reflect: the
            # Lancer's black trim and window glass set 0.2, its paint 0.6. glTF's
            # dielectric Fresnel has no such knob — it runs 0.04 head-on to 1.0
            # at the silhouette — and these materials carry a 16x16 near-black
            # diffuse, so the reflection IS their appearance. Uncapped, a curved
            # moulding or a cage tube rendered as nothing but sky.
            #
            # KHR_materials_specular is exactly this quantity, and a renderer
            # that implements the extension picks it up with no extra work.
            fml = p.get('fresnelMaxLevel', 0.0)
            if fml > 0.0:
                mat['extensions'] = {'KHR_materials_specular':
                                     {'specularFactor': round(min(fml, 1.0), 4)}}
                self.ext_used.add('KHR_materials_specular')
            # ---- Car paint: AC's SECOND specular lobe ----------------------
            # A carpaint material in AC carries two highlights and this
            # converter was only carrying one. `ksSpecularEXP` (50 on the MX-5)
            # is the base coat -- the wide sheen off the aluminium flake in the
            # pigment. `sunSpecular` / `sunSpecularEXP` (12 / 1500 there, 40 /
            # 6000 on the Evo III) is the CLEAR LACQUER over it: a separate,
            # much brighter, much tighter lobe fed by the sun alone. Averaged
            # into one GGX the needle-sharp glint that reads as "paint" comes
            # out a soft blob, and the car reads as moulded plastic.
            #
            # Only paint sets it. The MX-5's leather, stitching, carpet and
            # glass all leave it out, so the parameter's presence is the
            # author's own marker for "this panel is painted" -- which is
            # exactly the classifier needed, and better than a name match.
            sun = p.get('sunSpecular', 0.0)
            if sun > 0.0:
                sx = max(p.get('sunSpecularEXP', 1500.0), 1.0)
                # sunSpecular is an intensity in AC's units, not a coverage.
                # /20 puts the two measured cars either side of the range the
                # extension wants (MX-5 0.6, Evo III 1.0) instead of pinning
                # both at full and losing the difference the authors set.
                cc = {'clearcoatFactor': round(min(sun / 20.0, 1.0), 4),
                      'clearcoatRoughnessFactor':
                          round(min(max((2.0 / (sx + 2.0)) ** 0.5, 0.02), 1.0), 4)}
                # NOT part of the extension, and deliberately a key inside it
                # rather than an extension of its own: the metallic flake is the
                # same coat, few consumers read it, and a glTF loader
                # ignores keys it does not know. AC spells flake as a tiled
                # detail texture (`metal_detail` at detailUVMultiplier 50) --
                # a texture only because AC had nowhere else to put a per-pixel
                # sparkle, so what carries over is the fact that it is there.
                det = t.get('txDetail', '').lower()
                if p.get('useDetail', 0.0) > 0.0 and ('metal' in det or 'flake' in det):
                    cc['flakeFactor'] = round(min(p['useDetail'], 1.0), 4)
                mat.setdefault('extensions', {})['KHR_materials_clearcoat'] = cc
                self.ext_used.add('KHR_materials_clearcoat')
            # txNormal is NOT always a normal map. On AC's damage shaders the
            # slot holds the DENT map, which the game blends in proportion to
            # accumulated damage — zero on an undamaged car. Bound
            # unconditionally it renders every panel permanently caved in.
            nm = t.get('txNormal', '')
            n = None if 'damage' in nm.lower() else self._by_uri(self.tex_files.get(nm))
            if n is None and self.gen_normals > 0.0 and not m['alpha_tested']                     and not m['alpha_blend']:
                # Only where the source has none, and never on a cutout — see
                # gen_normal. A material that already ships a normal map keeps it.
                dds = t.get('txDiffuse', '')
                blob = next((x[2] for x in model.textures if x[0] == dds), None)
                if blob and len(blob) > 128:
                    n = self._by_uri(gen_normal(blob, self.outdir, self.gn_cache,
                                                dds, self.gen_normals))
                    if n is not None:
                        self.n_generated += 1
            if n is not None:
                mat['normalTexture'] = {'index': n}
            if m['alpha_blend']:
                mat['alphaMode'] = 'BLEND'
            elif m['alpha_tested']:
                mat['alphaMode'] = 'MASK'
                # ksAlphaRef is NOT a glTF cutoff, and taking it literally is
                # what produced the grey rectangles: 14 of this track's
                # materials set it to 0.0, and a MASK at 0 passes every fragment
                # — the whole texture card renders opaque, fringe and all. The
                # tree shader's 0.01 is barely better. Both come from AC's own
                # coverage path, which glTF has no equivalent for, so anything
                # below a usable threshold falls back to glTF's default 0.5.
                ref = p.get('ksAlphaRef', 0.0)
                mat['alphaCutoff'] = ref if ref >= 0.02 else 0.5
            if p.get('ksEmissive', 0.0) > 0.0:
                e = min(p['ksEmissive'], 1.0)
                mat['emissiveFactor'] = [e, e, e]
            self.materials.append(mat)
        return base

    def emit(self, n, mat_base, flip_uv, keep_variants):
        """One kn5 node -> one glTF node, children and all. None = dropped."""
        if not keep_variants and (VARIANT_RE.search(n.name)
                                  or n.name in self.lowres):
            self.stats['skipped'] += 1
            return None
        g = {'name': n.name}
        if n.type == kn5.DUMMY:
            self.stats['dummy'] += 1
            # kn5 stores a DirectX row-major matrix; glTF wants column-major.
            # Those two layouts hold the SAME bytes for the same transform, so
            # this is a copy, not a transpose.
            if n.matrix and n.matrix != IDENTITY:
                if all(math.isfinite(x) for x in n.matrix):
                    g['matrix'] = [float(x) for x in n.matrix]
                else:
                    self.stats['nanmat'] += 1
        elif not n.idx or not n.pos:
            self.stats['empty'] += 1
        else:
            self.stats['mesh'] += 1
            self.stats['tris'] += len(n.idx) // 3
            self.mesh_names.append(n.name)
            self.stats['nan'] += scrub(n.pos, lambda i: [0.0, 0.0, 0.0])
            self.stats['nan'] += scrub(n.nrm, lambda i: [0.0, 1.0, 0.0])
            self.stats['nan'] += scrub(n.uv, lambda i: [0.0, 0.0])
            self.stats['nan'] += scrub(n.tan, lambda i: perp(n.nrm[i]))
            attrs = {'POSITION': self.buf.floats(n.pos, 3),
                     'NORMAL': self.buf.floats(n.nrm, 3),
                     'TEXCOORD_0': self.buf.floats(
                         [[u[0], -u[1] if flip_uv else u[1]] for u in n.uv], 2),
                     # kn5 tangents are vec3; glTF needs handedness in w. The
                     # source does not record it, so it is 1.
                     'TANGENT': self.buf.floats(
                         [[t[0], t[1], t[2], 1.0] for t in n.tan], 4)}
            prim = {'attributes': attrs, 'indices': self.buf.indices(n.idx)}
            if 0 <= n.material + mat_base < len(self.materials):
                prim['material'] = n.material + mat_base
            self.meshes.append({'name': n.name, 'primitives': [prim]})
            g['mesh'] = len(self.meshes) - 1

        self.nodes.append(g)
        me = len(self.nodes) - 1
        kids = [k for k in (self.emit(c, mat_base, flip_uv, keep_variants)
                            for c in n.children) if k is not None]
        if kids:
            self.nodes[me]['children'] = kids
        return me


def write_glb(gltf, buf, outdir, name):
    """Fold the .bin and every PNG into one self-contained .glb; return its path.

    GLB is the same glTF, with the JSON and the binary blob in two chunks of one
    file, so nothing about the conversion changes -- what changes is that the
    images stop being `uri` references to files beside it and become
    bufferViews inside it. That is the whole reason the format exists: a car is
    a .gltf, a .bin and sixty-odd PNGs, and every one of them has to travel
    together or the model arrives untextured.

    The images are appended to the SAME buffer the geometry is in, because GLB
    allows exactly one binary chunk. Both the chunks and every bufferView have
    to start on a four-byte boundary: the JSON chunk is padded with spaces
    (0x20) and the binary one with zeros, which is what the spec asks for and
    not an arbitrary choice -- a parser is allowed to hand the JSON chunk
    straight to a string reader, and trailing NULs there are not valid JSON.
    """
    blob = bytearray(buf.data)

    def view(data):
        while len(blob) % 4:
            blob.append(0)
        off = len(blob)
        blob.extend(data)
        gltf['bufferViews'].append({'buffer': 0, 'byteOffset': off,
                                    'byteLength': len(data)})
        return len(gltf['bufferViews']) - 1

    embedded = []
    for img in gltf.get('images', []):
        uri = img.pop('uri')
        path = os.path.join(outdir, uri)
        with open(path, 'rb') as f:
            img['bufferView'] = view(f.read())
        # Keeping the filename as the image name costs nothing and is what
        # makes a .glb debuggable: an extractor gives the textures back under
        # the names the car used for them instead of image0..image61.
        img['name'] = uri
        img['mimeType'] = 'image/png'
        embedded.append(path)

    # No `uri` on the buffer is what marks it as the GLB binary chunk.
    gltf['buffers'] = [{'byteLength': len(blob)}]

    js = json.dumps(gltf, separators=(',', ':'), allow_nan=False).encode('utf-8')
    js += b' ' * (-len(js) % 4)
    blob += b'\0' * (-len(blob) % 4)

    path = os.path.join(outdir, name + '.glb')
    with open(path, 'wb') as f:
        f.write(struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob)))
        f.write(struct.pack('<II', len(js), 0x4E4F534A))
        f.write(js)
        f.write(struct.pack('<II', len(blob), 0x004E4942))
        f.write(blob)
    return path, embedded


def model_matrix(pos, rot):
    """A track model's placement from models.ini, as a column-major glTF matrix.

    It goes UNDER the axis-flip root, so the position is written in AC's frame
    and the root converts it with everything else — which is the point of doing
    the flip once at the top instead of per vertex.
    """
    rx, ry, rz = (math.radians(a) for a in rot)
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    m = [[cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
         [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
         [-sy,     cy * sx,                cy * cx]]
    return [m[0][0], m[1][0], m[2][0], 0.0,
            m[0][1], m[1][1], m[2][1], 0.0,
            m[0][2], m[1][2], m[2][2], 0.0,
            pos[0],  pos[1],  pos[2],  1.0]


def convert(sources, outdir, name, flip_uv, keep_variants, surfaces_ini,
            gen_normals=0.0, skin=None, materials_report=False, tex_cache=None,
            bake_cache=None, glb=False):
    os.makedirs(outdir, exist_ok=True)
    G = Gltf(outdir)
    G.gen_normals = gen_normals
    # Textures already written to THIS outdir by a previous call, so a caller
    # converting the same car again (a different livery) does not re-decode the
    # forty-odd maps the livery does not touch. Mutated in place, so the caller's
    # dict is up to date afterwards. None = decode everything, the old behaviour.
    if tex_cache is not None:
        G.tex_files = tex_cache
    # The same argument for the roughness bakes, and they are the BIGGER half:
    # on ks_porsche_911_r the diffuse/normal pass costs 2.1 s and the 53
    # roughness bakes cost 5.9 s. Keyed by (texture, exponent) and the file is
    # already beside the glTF, so a re-run with the same materials writes
    # nothing. Entries the livery overrides are dropped below, once the swap is
    # known - a skin can ship a *_MAP.dds too.
    if bake_cache is not None:
        G.bake_cache = bake_cache
    roots = []
    multi = len(sources) > 1

    for src in sources:
        model = kn5.load(src['file'])
        G.stats['folded'] += fold_texture_case(model)
        if model.encrypted:
            sys.exit('refusing: %s carries the CSP kn5 encryption trailer.\n'
                     'Its textures and several meshes are decoys in the plain '
                     'section, so the output would be wrong without looking it.'
                     % os.path.basename(src['file']))

        swapped = apply_skin(model, skin)
        for k in [k for k in G.bake_cache if k[0] in swapped]:
            del G.bake_cache[k]
        if swapped:
            print('skin   : %s (%d textures)'
                  % (os.path.basename(skin), len(swapped)))

        used = set()
        # AC reads a diffuse's ALPHA only where the material is alpha-blended or
        # alpha-tested. Everywhere else the channel is whatever happened to be in
        # the DDS, and on this car that is zero: carpaint_evo, seatsao, dashao,
        # carpet_ao and eight more decode to a fully transparent image. AC's
        # shader never looks, so nobody noticed; a PBR renderer does, and the
        # body paint and the whole interior arrived with no visible texture.
        keeps_alpha = set()
        for m in model.materials:
            for slot in ('txDiffuse', 'txNormal'):
                v = m['textures'].get(slot)
                if v and not (slot == 'txNormal' and 'damage' in v.lower()):
                    used.add(v)
                    if v and (m['alpha_blend'] or m['alpha_tested']):
                        keeps_alpha.add(v)
        # The livery's own textures are re-decoded even when the cache has them:
        # they are the bytes that just changed.
        G.tex_files = save_textures(model, outdir, used, G.tex_files, keeps_alpha,
                                    force=swapped)
        mat_base = G.add_materials(model)
        if materials_report:
            print_materials(model, G.materials, mat_base, G.tex_files,
                            swapped, keeps_alpha)

        before = G.stats['tris']
        G.lowres = (set() if keep_variants
                    else lowres_twins([n.name for n, _ in model.walk()]))
        child = G.emit(model.root, mat_base, flip_uv, keep_variants)
        if child is None:
            continue
        if src['pos'] != [0.0, 0.0, 0.0] or src['rot'] != [0.0, 0.0, 0.0]:
            G.nodes.append({'name': os.path.basename(src['file']),
                            'matrix': model_matrix(src['pos'], src['rot']),
                            'children': [child]})
            child = len(G.nodes) - 1
        roots.append(child)
        if multi:
            print('  + %-36s %8d tris' % (os.path.basename(src['file']),
                                          G.stats['tris'] - before))

    # The half turn about Y that takes AC's axes to glTF's. Determinant +1, so
    # winding stays valid and nothing per-vertex is touched.
    G.nodes.append({'name': name,
                    'matrix': [-1, 0, 0, 0, 0, 1, 0, 0, 0, 0, -1, 0, 0, 0, 0, 1],
                    'children': roots})
    root = len(G.nodes) - 1

    binname = name + '.bin'
    gltf = {
        'asset': {'version': '2.0', 'generator': GENERATOR},
        'scene': 0, 'scenes': [{'nodes': [root]}],
        'nodes': G.nodes, 'meshes': G.meshes, 'materials': G.materials,
        'buffers': [{'uri': binname, 'byteLength': len(G.buf.data)}],
        'bufferViews': G.buf.views, 'accessors': G.buf.accessors,
    }
    if G.ext_used:
        gltf['extensionsUsed'] = sorted(G.ext_used)
    if G.images:
        gltf['images'] = G.images
        gltf['textures'] = G.textures
        gltf['samplers'] = [{'magFilter': 9729, 'minFilter': 9987,
                             'wrapS': 10497, 'wrapT': 10497}]

    if glb:
        out_path, embedded = write_glb(gltf, G.buf, outdir, name)
        # Every byte those files held is now inside the .glb, so the loose
        # copies go: someone who asked for a single file did not ask for a
        # single file and sixty PNGs beside it. Only the images this run
        # embedded are removed, never anything else in the directory.
        for stale in embedded:
            os.remove(stale)
    else:
        out_path = os.path.join(outdir, name + '.gltf')
        with open(os.path.join(outdir, binname), 'wb') as f:
            f.write(G.buf.data)
        with open(out_path, 'w', encoding='utf-8') as f:
            # allow_nan=False is the backstop: Python's default emits a bare NaN
            # token that is not valid JSON, and the file then fails in the loader
            # rather than here. Better to fail here.
            json.dump(gltf, f, separators=(',', ':'), allow_nan=False)

    print('nodes  : %d  (%d transforms, %d meshes, %d empty, %d variants dropped)'
          % (len(G.nodes), G.stats['dummy'], G.stats['mesh'], G.stats['empty'],
             G.stats['skipped']))
    print('tris   : %d' % G.stats['tris'])
    print('images : %d   materials: %d' % (len(G.images), len(G.materials)))
    if G.n_generated:
        print('normals: %d materials given a normal map derived from their '
              'albedo (strength %.2f)' % (G.n_generated, gen_normals))
    if G.stats['folded']:
        print('folded : %d texture names that differed only in case'
              % G.stats['folded'])
    if G.stats['nan'] or G.stats['nanmat']:
        print('scrubbed: %d non-finite vertex attributes, %d NaN node matrices'
              % (G.stats['nan'], G.stats['nanmat']))
    print('%-7s: %.1f MB' % ('glb' if glb else 'bin',
                             os.path.getsize(out_path) / 1048576
                             if glb else len(G.buf.data) / 1048576))

    # ---- Physics surfaces, as a sidecar -------------------------------------
    # Not baked into the glTF: glTF has no concept of a surface, and an extras
    # blob on every one of a few thousand nodes would bloat the file for the
    # consumers that do not want it. A sidecar keyed by node name is what a
    # collider can read directly, and it is readable by eye.
    if surfaces_ini:
        keys = read_surfaces_ini(surfaces_ini)
        nodes, walls, default = {}, [], {}
        for nm in G.mesh_names:
            kind, detail = classify_surface(nm, keys)
            if kind == 'surface':
                nodes[nm] = detail
            elif kind == 'wall':
                walls.append(nm)
            elif kind == 'default':
                default[nm] = detail
        with open(os.path.join(outdir, name + '.surfaces.json'), 'w',
                  encoding='utf-8') as f:
            json.dump({'source': os.path.basename(surfaces_ini),
                       'surfaces': keys, 'nodes': nodes,
                       'walls': sorted(walls), 'unkeyed': default},
                      f, indent=1, sort_keys=True)
        used = sorted(set(nodes.values()))
        unk = sorted(set(default.values()))
        print('surfaces: %d meshes matched a key, %d walls, %d physics-on but '
              'unkeyed, %d visual  (of %d)'
              % (len(nodes), len(walls), len(default),
                 len(G.mesh_names) - len(nodes) - len(walls) - len(default),
                 len(G.mesh_names)))
        print('          keys used : %s' % (', '.join(used) or '(none)'))
        if unk:
            print('          unkeyed   : %s' % ', '.join(unk))
    print('wrote  : %s' % out_path)


def main():
    ap = argparse.ArgumentParser(prog='kn5-to-gltf')
    ap.add_argument('kn5', nargs='?', help='a single .kn5 (a car)')
    ap.add_argument('outdir', nargs='?',
                    help='where to write the glTF. Optional only for '
                         '--list-skins, which writes nothing')
    ap.add_argument('--models', help='a track models_*.ini instead of one kn5')
    ap.add_argument('--surfaces', help='a track data/surfaces.ini; writes '
                                       '<name>.surfaces.json beside the glTF')
    ap.add_argument('--name', default=None, help='basename for .gltf/.bin')
    ap.add_argument('--flip-uv', action='store_true',
                    help='negate V. glTF and DirectX agree on a top-left UV '
                         'origin, so this should NOT be needed — it is here '
                         'because a mod authored through Blender can arrive '
                         'either way, and the texture tells you in one look.')
    ap.add_argument('--gen-normals', nargs='?', type=float, const=1.0, default=0.0,
                    metavar='STRENGTH',
                    help='fabricate a normal map from the albedo for every '
                         'material that has none — see gen_normal. Off by '
                         'default; 1.0 is a sane starting point, 2 is strong. '
                         'It infers shape from colour, so it flatters asphalt '
                         'and brick and embosses painted lane lines.')
    ap.add_argument('--glb', action='store_true',
                    help='write one self-contained <name>.glb instead of the '
                         '.gltf/.bin/PNG set — the geometry and every texture '
                         'in a single file, which is what a viewer or an asset '
                         'pipeline wants. The loose files this run produced are '
                         'removed once they are inside it.')
    ap.add_argument('--skin', default=None, metavar='NAME',
                    help='take textures from the car\'s skins/NAME folder, '
                         'which is where AC keeps the actual paint. Defaults '
                         'to the first skin; pass `none` to keep the textures '
                         'embedded in the kn5, which on most cars is the blank '
                         'white template and is why an import comes out white.')
    ap.add_argument('--list-skins', action='store_true',
                    help="write nothing; print the car's liveries and the "
                         "colour each one paints it, as tab-separated lines, "
                         "ordered so that the first line of a livery is its "
                         "bodywork. What a skin picker reads.")
    ap.add_argument('--materials', action='store_true',
                    help='print what every material resolved to: its diffuse, '
                         'its paint slot and the base-colour factor that came '
                         'out, with a * on each texture the chosen skin '
                         'overrides. The answer to "the body did not change '
                         'colour" and to "the car came out black".')
    ap.add_argument('--keep-variants', action='store_true',
                    help='keep the runtime variants: *_BLUR, *_DAMAGE, and the '
                         'low-res *_LR halves of AC in-file LOD pairs, which '
                         'are dropped by default because they z-fight with the '
                         'meshes they exist to replace')
    ap.add_argument('--version', action='version',
                    version='%(prog)s ' + __version__)
    a = ap.parse_args()

    # Both positionals are optional now, so argparse hands a lone one to `kn5`.
    # For the track form there is no kn5 and that lone argument is the outdir.
    if a.models and a.outdir is None and a.kn5 is not None:
        a.kn5, a.outdir = None, a.kn5

    if a.list_skins:
        if not a.kn5:
            sys.exit('--list-skins needs a .kn5')
        return print_skins(skin_report(a.kn5))

    if not a.outdir:
        sys.exit('give an output directory')

    if a.models:
        sources = read_models_ini(a.models)
        if not sources:
            sys.exit('no [MODEL_n] entries in %s' % a.models)
        missing = [s['file'] for s in sources if not os.path.exists(s['file'])]
        if missing:
            sys.exit('models.ini names files that are not there:\n  ' +
                     '\n  '.join(missing))
        default = os.path.splitext(os.path.basename(a.models))[0]
        print('%d models from %s' % (len(sources), os.path.basename(a.models)))
    elif a.kn5:
        sources = [{'file': a.kn5, 'pos': [0.0] * 3, 'rot': [0.0] * 3}]
        default = os.path.splitext(os.path.basename(a.kn5))[0]
    else:
        sys.exit('give a .kn5 or --models <models_*.ini>')

    convert(sources, a.outdir, a.name or default, a.flip_uv, a.keep_variants,
            a.surfaces, a.gen_normals,
            skin=skin_dir(a.kn5, a.skin) if a.kn5 else None,
            materials_report=a.materials, glb=a.glb)


if __name__ == '__main__':
    sys.exit(main() or 0)
