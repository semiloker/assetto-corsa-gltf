#!/usr/bin/env python3
"""End to end: build a kn5, convert it, and read the result back.

    python tests/test_convert.py

The other suites pin one decision each -- which meshes are LOD twins, where the
paint comes from, what the studio's routes answer. This one runs the whole
converter, and it needs a car to do it. Rather than check a licensed model into
the repository it WRITES one: `make_kn5` below is a minimal encoder for the same
container `acgltf.kn5` decodes, so the test owns both ends and CI needs no
Assetto Corsa install.

What that buys is the things only the full pipeline can be wrong about: that the
node tree survives one for one, that the axis change is a rotation and not a
mirror, that a NaN never reaches the JSON, that a .glb is a .glb, and that two
texture names differing only in case do not leave the glTF pointing at a file
that is not there.
"""
import io
import json
import math
import os
import struct
import sys
import tempfile

from acgltf import convert as K
from acgltf import kn5
from PIL import Image


# --- a kn5 encoder, the inverse of acgltf.kn5 -------------------------------
def s(txt):
    b = txt.encode('utf-8')
    return struct.pack('<I', len(b)) + b


def png_bytes(size=(64, 64), rgb=(200, 30, 20)):
    """A PNG of at least 128 bytes -- save_textures treats anything smaller as
    the stub an encrypted or placeholder entry leaves behind, so a tidy 8x8
    solid colour would be skipped and the test would be checking nothing. The
    per-pixel jitter is there to defeat PNG's compression, not for looks."""
    im = Image.new('RGB', size)
    im.putdata([((rgb[0] + i * 37) % 256, (rgb[1] + i * 91) % 256,
                 (rgb[2] + i * 173) % 256)
                for i in range(size[0] * size[1])])
    b = io.BytesIO()
    im.save(b, 'PNG')
    blob = b.getvalue()
    assert len(blob) >= 128, len(blob)
    return blob


def mesh_node(name, verts, tris, material=0, children=()):
    """A MESH node. `verts` are (pos3, nrm3, uv2, tan3) tuples."""
    out = struct.pack('<i', kn5.MESH) + s(name) + struct.pack('<i', len(children))
    out += bytes([1])                       # active
    out += bytes([1, 1, 0])                 # castShadows, visible, transparent
    out += struct.pack('<I', len(verts))
    for p, n, uv, t in verts:
        out += struct.pack('<11f', *(list(p) + list(n) + list(uv) + list(t)))
    idx = [i for tri in tris for i in tri]
    out += struct.pack('<I', len(idx)) + struct.pack('<%dH' % len(idx), *idx)
    out += struct.pack('<II', material, 0)          # material, layer
    out += struct.pack('<ff', 0.0, 0.0)             # lodIn, lodOut
    out += struct.pack('<4f', 0.0, 0.0, 0.0, 1.0)   # bounding sphere
    out += bytes([1])                               # isRenderable
    return out + b''.join(children)


def dummy_node(name, children=(), matrix=None):
    m = matrix or [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    out = struct.pack('<i', kn5.DUMMY) + s(name) + struct.pack('<i', len(children))
    out += bytes([1]) + struct.pack('<16f', *m)
    return out + b''.join(children)


def make_kn5(path, textures, materials, root, version=5):
    """Write a kn5. `version=6` exercises the extra header word v6 files carry."""
    out = b'sc6969' + struct.pack('<I', version)
    if version > 5:
        out += struct.pack('<I', 0)
    out += struct.pack('<I', len(textures))
    for name, blob in textures:
        out += struct.pack('<I', 1) + s(name) + struct.pack('<I', len(blob)) + blob
    out += struct.pack('<I', len(materials))
    for m in materials:
        out += s(m['name']) + s(m.get('shader', 'ksPerPixel'))
        out += bytes([1 if m.get('alpha_blend') else 0,
                      1 if m.get('alpha_tested') else 0])
        out += struct.pack('<i', 0)                 # depthMode, an int32
        props = m.get('props', {})
        out += struct.pack('<I', len(props))
        for pn, pv in props.items():
            out += s(pn) + struct.pack('<f', pv) + b'\0' * 36
        texs = m.get('textures', {})
        out += struct.pack('<I', len(texs))
        for slot, tname in texs.items():
            out += s(slot) + struct.pack('<I', 0) + s(tname)
    with open(path, 'wb') as f:
        f.write(out + root)
    return path


# One triangle, corners spread so the axis change is measurable on every axis.
QUAD = [((1.0, 2.0, 3.0), (0.0, 1.0, 0.0), (0.0, 0.0), (1.0, 0.0, 0.0)),
        ((4.0, 5.0, 6.0), (0.0, 1.0, 0.0), (1.0, 0.0), (1.0, 0.0, 0.0)),
        ((7.0, 8.0, 9.0), (0.0, 1.0, 0.0), (1.0, 1.0), (1.0, 0.0, 0.0))]


def car(tmp, name='car.kn5', version=5, extra_nodes=(), textures=None,
        materials=None):
    textures = textures if textures is not None else [('body.dds', png_bytes())]
    materials = materials if materials is not None else [
        {'name': 'EXT_Carpaint', 'textures': {'txDiffuse': 'body.dds'}}]
    root = dummy_node('BODY', children=[
        mesh_node('GEO_Body', QUAD, [(0, 1, 2)]),
        dummy_node('SUSP_LR', children=[mesh_node('WHEEL_LR', QUAD, [(0, 1, 2)])]),
    ] + list(extra_nodes))
    return make_kn5(os.path.join(tmp, name), textures, materials, root, version)


def run(path, outdir, **kw):
    kw.setdefault('flip_uv', False)
    kw.setdefault('keep_variants', False)
    kw.setdefault('surfaces_ini', None)
    K.convert([{'file': path, 'pos': [0.0] * 3, 'rot': [0.0] * 3}],
              outdir, kw.pop('name', 'out'), **kw)
    return outdir


def read_gltf(outdir, name='out'):
    with open(os.path.join(outdir, name + '.gltf'), encoding='utf-8') as f:
        return json.load(f)


def read_glb(path):
    """Parse a GLB the way a loader does, and assert the container is legal."""
    with open(path, 'rb') as f:
        b = f.read()
    magic, ver, total = struct.unpack_from('<III', b, 0)
    assert magic == 0x46546C67, 'not a glb'
    assert ver == 2, ver
    assert total == len(b), (total, len(b))
    o, chunks = 12, []
    while o < len(b):
        ln, ty = struct.unpack_from('<II', b, o)
        o += 8
        assert ln % 4 == 0, 'chunk length must be 4-byte aligned'
        chunks.append((ty, b[o:o + ln]))
        o += ln
    assert [t for t, _ in chunks] == [0x4E4F534A, 0x004E4942], \
        'a GLB is a JSON chunk then a BIN chunk, in that order'
    return json.loads(chunks[0][1].decode('utf-8')), chunks[1][1]


# --- the tests --------------------------------------------------------------
def test_the_node_tree_survives_one_for_one():
    tmp = tempfile.mkdtemp()
    g = read_gltf(run(car(tmp), os.path.join(tmp, 'out')))
    names = [n.get('name') for n in g['nodes']]
    for want in ('BODY', 'GEO_Body', 'SUSP_LR', 'WHEEL_LR'):
        assert want in names, (want, names)

    # ...including the parent links, which are the reason for keeping it.
    by_name = {n['name']: n for n in g['nodes'] if 'name' in n}
    kids = [g['nodes'][i]['name'] for i in by_name['SUSP_LR'].get('children', [])]
    assert kids == ['WHEEL_LR'], kids
    print('ok  hierarchy   BODY > SUSP_LR > WHEEL_LR, parents intact')


def test_wheel_lr_is_left_rear_and_stays():
    """The trap the LOD rule has to avoid, checked through the whole converter
    rather than against lowres_twins alone: no _HR twin, so nothing is dropped."""
    tmp = tempfile.mkdtemp()
    g = read_gltf(run(car(tmp), os.path.join(tmp, 'out')))
    assert 'WHEEL_LR' in [n.get('name') for n in g['nodes']]
    print('ok  lod         WHEEL_LR kept -- _LR here is Left Rear')


def test_lod_twins_and_variants_are_dropped_by_default():
    tmp = tempfile.mkdtemp()
    extra = [mesh_node('COCKPIT_HR', QUAD, [(0, 1, 2)]),
             mesh_node('COCKPIT_LR', QUAD, [(0, 1, 2)]),
             mesh_node('WHEEL_BLUR_LF', QUAD, [(0, 1, 2)]),
             mesh_node('DAMAGE_GLASS', QUAD, [(0, 1, 2)])]
    path = car(tmp, extra_nodes=extra)

    plain = read_gltf(run(path, os.path.join(tmp, 'a')))
    names = [n.get('name') for n in plain['nodes']]
    assert 'COCKPIT_HR' in names
    for gone in ('COCKPIT_LR', 'WHEEL_BLUR_LF', 'DAMAGE_GLASS'):
        assert gone not in names, gone

    kept = read_gltf(run(path, os.path.join(tmp, 'b'), keep_variants=True))
    for back in ('COCKPIT_LR', 'WHEEL_BLUR_LF', 'DAMAGE_GLASS'):
        assert back in [n.get('name') for n in kept['nodes']], back
    print('ok  variants    _LR twin, _BLUR and _DAMAGE dropped; '
          '--keep-variants restores them')


def test_the_axis_change_is_a_rotation_not_a_mirror():
    """A half turn about Y has determinant +1, so the winding stays valid. A
    mirror would flip it, and every triangle in the car would face inwards."""
    tmp = tempfile.mkdtemp()
    g = read_gltf(run(car(tmp), os.path.join(tmp, 'out')))
    root = g['nodes'][g['scenes'][0]['nodes'][0]]
    m = root['matrix']
    assert m == [-1, 0, 0, 0, 0, 1, 0, 0, 0, 0, -1, 0, 0, 0, 0, 1], m
    det = (m[0] * (m[5] * m[10] - m[6] * m[9])
           - m[4] * (m[1] * m[10] - m[2] * m[9])
           + m[8] * (m[1] * m[6] - m[2] * m[5]))
    assert abs(det - 1.0) < 1e-9, det
    print('ok  axes        root is a half turn about Y, determinant +1')


def test_positions_and_indices_round_trip():
    tmp = tempfile.mkdtemp()
    out = run(car(tmp), os.path.join(tmp, 'out'))
    g = read_gltf(out)
    with open(os.path.join(out, g['buffers'][0]['uri']), 'rb') as f:
        blob = f.read()
    assert len(blob) == g['buffers'][0]['byteLength']

    mesh = next(m for m in g['meshes'] if m['name'] == 'GEO_Body')
    acc = g['accessors'][mesh['primitives'][0]['attributes']['POSITION']]
    view = g['bufferViews'][acc['bufferView']]
    raw = blob[view['byteOffset']:view['byteOffset'] + view['byteLength']]
    pos = [list(struct.unpack_from('<3f', raw, i * 12)) for i in range(acc['count'])]
    assert pos == [list(v[0]) for v in QUAD], pos
    assert acc['min'] == [1.0, 2.0, 3.0] and acc['max'] == [7.0, 8.0, 9.0], acc

    idx = g['accessors'][mesh['primitives'][0]['indices']]
    iview = g['bufferViews'][idx['bufferView']]
    iraw = blob[iview['byteOffset']:iview['byteOffset'] + iview['byteLength']]
    assert list(struct.unpack_from('<3H', iraw, 0)) == [0, 1, 2]
    print('ok  geometry    positions, bounds and indices survive the buffer')


def test_a_v6_header_reads_too():
    tmp = tempfile.mkdtemp()
    g = read_gltf(run(car(tmp, version=6), os.path.join(tmp, 'out')))
    assert 'GEO_Body' in [n.get('name') for n in g['nodes']]
    print('ok  header      a v6 file has one extra word, and it is skipped')


def test_nan_never_reaches_the_json():
    """Real cars carry NaN tangents and all-NaN dummy matrices. Python will
    happily write a bare `NaN` token, which no glTF loader accepts."""
    tmp = tempfile.mkdtemp()
    nan = float('nan')
    bad = [(QUAD[0][0], QUAD[0][1], QUAD[0][2], (nan, nan, nan)),
           ((nan, 2.0, 3.0), QUAD[1][1], QUAD[1][2], QUAD[1][3]),
           QUAD[2]]
    extra = [mesh_node('GEO_Nan', bad, [(0, 1, 2)]),
             dummy_node('NAN_DUMMY', matrix=[nan] * 16)]
    out = run(car(tmp, extra_nodes=extra), os.path.join(tmp, 'out'))
    with open(os.path.join(out, 'out.gltf'), encoding='utf-8') as f:
        text = f.read()
    assert 'NaN' not in text and 'Infinity' not in text
    g = json.loads(text)                     # and it is valid JSON to a parser
    dm = next(n for n in g['nodes'] if n.get('name') == 'NAN_DUMMY')
    assert all(math.isfinite(v) for v in dm.get('matrix', [0])), dm
    print('ok  scrub       NaN vertices and NaN matrices never reach the file')


def test_texture_names_that_differ_only_in_case_resolve_to_one_file():
    """ks_mazda_mx5_nd ships `INT_DEcals.dds` and asks for `INT_Decals.dds`.
    AC does not care. A glTF that repeats the mistake names an image that is
    not on disk -- invisibly on Windows, visibly everywhere else."""
    tmp = tempfile.mkdtemp()
    path = car(tmp,
               textures=[('INT_DEcals.dds', png_bytes(rgb=(10, 20, 30))),
                         ('INT_Decals.dds', png_bytes(rgb=(9, 9, 9)))],
               materials=[{'name': 'EXT_Carpaint',
                           'textures': {'txDiffuse': 'INT_Decals.dds'}}])
    out = run(path, os.path.join(tmp, 'out'))
    g = read_gltf(out)
    on_disk = set(os.listdir(out))
    missing = [i['uri'] for i in g.get('images', []) if i['uri'] not in on_disk]
    assert not missing, missing
    assert len(g['images']) == 1, g['images']
    print('ok  case        one image, and the name in the glTF is the name on disk')


def test_glb_is_one_self_contained_file():
    tmp = tempfile.mkdtemp()
    out = os.path.join(tmp, 'out')
    run(car(tmp), out, glb=True)

    assert os.listdir(out) == ['out.glb'], os.listdir(out)
    g, blob = read_glb(os.path.join(out, 'out.glb'))

    assert 'uri' not in g['buffers'][0], 'the GLB buffer is the BIN chunk'
    assert g['buffers'][0]['byteLength'] <= len(blob)
    assert g['images'], 'the car had a texture'
    for img in g['images']:
        assert 'uri' not in img, img
        assert img['mimeType'] == 'image/png', img
        v = g['bufferViews'][img['bufferView']]
        assert v['byteOffset'] + v['byteLength'] <= len(blob)
        assert blob[v['byteOffset']:v['byteOffset'] + 8] == b'\x89PNG\r\n\x1a\n', \
            'the embedded bytes are the PNG'

    for a in g['accessors']:
        v = g['bufferViews'][a['bufferView']]
        size = {5126: 4, 5123: 2, 5125: 4}[a['componentType']]
        n = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[a['type']]
        assert a['count'] * size * n <= v['byteLength'], a
    print('ok  glb         one file, images as bufferViews, every view in range')


def test_glb_and_gltf_describe_the_same_model():
    tmp = tempfile.mkdtemp()
    a = read_gltf(run(car(tmp), os.path.join(tmp, 'a')))
    b, _ = read_glb(os.path.join(run(car(tmp), os.path.join(tmp, 'b'), glb=True),
                                'out.glb'))
    assert a['nodes'] == b['nodes'], 'the hierarchy must not depend on the container'
    assert a['meshes'] == b['meshes']
    assert len(a['materials']) == len(b['materials'])
    print('ok  parity      .glb and .gltf carry the same nodes and meshes')


def test_the_generator_is_recorded():
    tmp = tempfile.mkdtemp()
    g = read_gltf(run(car(tmp), os.path.join(tmp, 'out')))
    assert g['asset']['version'] == '2.0'
    assert g['asset']['generator'].startswith('assetto-corsa-gltf '), g['asset']
    print('ok  asset       the file says which tool and which version wrote it')


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
    print('')
    print('all good')


if __name__ == '__main__':
    sys.exit(main() or 0)
