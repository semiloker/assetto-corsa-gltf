#!/usr/bin/env python3
"""The import viewer's server, checked without an Assetto Corsa install.

    python tests/test_studio.py

Three things are worth pinning here and nothing else is:

  * the routes the page depends on answer at all, and answer JSON;
  * a conversion failure arrives as {"error": ...} rather than as a traceback
    into a socket, because the page has nowhere to show a 500;
  * and the server does NOT serve the repository. SimpleHTTPRequestHandler
    maps URLs onto the working directory by default, which here is the whole
    checkout - so `translate_path` is replaced, and a replacement that is
    subtly wrong is a local web server handing out source files.

The car is a stub: Studio's real work is kn5_to_gltf's, which has its own tests.
"""
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from acgltf import studio as S


class FakeStudio:
    """Everything Handler touches, and nothing that needs a .kn5."""

    def __init__(self, outdir):
        self.outdir = outdir
        self.name = 'fake'
        self.version = 0
        self.fail = False
        self.converted = []

    def skins_json(self):
        return {'car': 'ks_fake', 'current': None, 'skins': [
            {'name': '00_red', 'hex': '7E0100', 'material': 'CARPAINT', 'source': 'skin'},
            {'name': 'none', 'hex': None, 'material': None, 'source': None}]}

    def paint_line(self, skin):
        return 'CARPAINT #7E0100 (48120 tris, from the livery)'

    def convert(self, skin):
        if self.fail:
            raise RuntimeError('boom')
        self.converted.append(skin)
        self.version += 1
        return '/model/%s/%s.gltf?v=%d' % ('ks_fake', self.name, self.version), ''


def get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, r.read()


SENTINEL = 'this file must never be reachable over http'


def main():
    tmp = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmp, 'ks_fake'))
    with open(os.path.join(tmp, 'ks_fake', 'fake.gltf'), 'w', encoding='utf-8') as f:
        f.write('{"asset":{"version":"2.0"}}')

    cwd = os.getcwd()
    os.chdir(tempfile.mkdtemp())

    studio = FakeStudio(tmp)
    S.Handler.studio = studio
    srv = ThreadingHTTPServer(('127.0.0.1', 0), S.Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = 'http://127.0.0.1:%d' % port
    try:
        # The page itself, from the vendored viewer folder.
        code, body = get(base + '/')
        assert code == 200 and b'importmap' in body, code
        print('ok  /            serves the viewer page')

        # three.js is beside it and reachable, or the page is a black rectangle.
        code, body = get(base + '/viewer/three/build/three.module.min.js')
        assert code == 200 and len(body) > 100000, len(body)
        print('ok  /viewer/...  serves the vendored three.js')

        code, body = get(base + '/api/skins')
        j = json.loads(body)
        assert j['car'] == 'ks_fake' and len(j['skins']) == 2, j
        print('ok  /api/skins   lists the liveries')

        code, body = get(base + '/api/select?skin=00_red')
        j = json.loads(body)
        assert studio.converted == ['00_red'], studio.converted
        assert j['url'] == '/model/ks_fake/fake.gltf?v=1', j
        assert j['paint'].startswith('CARPAINT'), j
        print('ok  /api/select  converts and versions the URL')

        # The version is a QUERY, so the path is stable and the glTF's own
        # relative references (.bin, the images) keep working. A version in the
        # path would change theirs too and re-fetch the geometry for a colour.
        for v in (1, 7):
            code, body = get('%s/model/ks_fake/fake.gltf?v=%d' % (base, v))
            assert code == 200 and b'"2.0"' in body, (v, code)
        code, body = get(base + '/model/ks_fake/fake.gltf')
        assert code == 200, code
        print('ok  /model/...    stable path, version only in the query')

        # A conversion that throws must become JSON, not a 500 with a traceback.
        studio.fail = True
        code, body = get(base + '/api/select?skin=00_red')
        j = json.loads(body)
        assert j.get('error', '').startswith('RuntimeError'), j
        studio.fail = False
        print('ok  /api/select  reports a failure as JSON')

        # ---- and it must not serve the repository ---------------------------
        # A traversal that resolves is a local web server handing out source.
        # A sentinel in the working directory rather than a file of this
        # repository's, so the check does not depend on where it is run from
        # and cannot quietly pass because the file it looked for was renamed.
        with open('SENTINEL.txt', 'w', encoding='utf-8') as f:
            f.write(SENTINEL)
        for bad in ['/SENTINEL.txt',
                    '/../SENTINEL.txt',
                    '/viewer/../../../SENTINEL.txt',
                    '/model/ks_fake/../../../SENTINEL.txt',
                    '/%2e%2e/SENTINEL.txt']:
            try:
                code, body = get(base + bad)
                served = (code == 200 and SENTINEL.encode() in body)
            except urllib.error.HTTPError:
                served = False
            assert not served, 'served the working directory through %s' % bad
        print('ok  traversal    refused for every shape tried')
    finally:
        srv.shutdown()
        srv.server_close()
        os.chdir(cwd)

    print('')
    print('all good')
    return 0


def test_studio_server():
    """So `pytest` collects it too; `python tests/test_studio.py` still works."""
    main()


if __name__ == '__main__':
    sys.exit(main() or 0)
