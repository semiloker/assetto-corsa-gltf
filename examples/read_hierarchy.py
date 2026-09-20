#!/usr/bin/env python3
"""Read a converted car back and find its wheels, hubs and suspension pickups.

    python examples/read_hierarchy.py out/mx5.gltf
    python examples/read_hierarchy.py out/mx5.glb --tree

The hierarchy is the reason to use this converter rather than one that flattens
the model, and this is what having it buys: the nodes a rig needs are already
named and already positioned, so finding them is a dictionary lookup rather than
a guess at which lump of triangles is a wheel.

Reads .gltf and .glb with nothing but the standard library -- a glTF is JSON,
and a GLB is that JSON in the first chunk of a two-chunk file.
"""
import argparse
import json
import os
import re
import struct
import sys

CORNERS = ['LF', 'RF', 'LR', 'RR']
ROLES = [
    ('wheel centre', re.compile(r'^WHEEL_(LF|RF|LR|RR)$', re.I)),
    ('suspension',   re.compile(r'^SUSP_(LF|RF|LR|RR)$', re.I)),
    ('rim',          re.compile(r'^(GEO_)?RIM_(LF|RF|LR|RR)$', re.I)),
    ('brake disc',   re.compile(r'^(GEO_)?DISC_(LF|RF|LR|RR)$', re.I)),
]


def load(path):
    """The glTF document, from either container."""
    if path.lower().endswith('.glb'):
        with open(path, 'rb') as f:
            blob = f.read()
        magic, version, total = struct.unpack_from('<III', blob, 0)
        if magic != 0x46546C67:
            sys.exit('%s is not a glb' % path)
        if total != len(blob):
            sys.exit('%s is truncated: header says %d bytes, file is %d'
                     % (path, total, len(blob)))
        length, kind = struct.unpack_from('<II', blob, 12)
        if kind != 0x4E4F534A:
            sys.exit('%s does not start with a JSON chunk' % path)
        return json.loads(blob[20:20 + length].decode('utf-8'))
    with open(path, encoding='utf-8') as f:
        return json.load(f)


IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def local_matrix(node):
    """A node's own transform as a column-major 4x4 (glTF stores m[col*4+row])."""
    if 'matrix' in node:
        return list(node['matrix'])
    m = list(IDENTITY)
    s = node.get('scale', [1.0, 1.0, 1.0])
    m[0], m[5], m[10] = s[0], s[1], s[2]
    if 'rotation' in node:
        x, y, z, w = node['rotation']            # glTF quaternions are xyzw
        m = [
            (1 - 2 * (y * y + z * z)) * s[0], (2 * (x * y + z * w)) * s[0],
            (2 * (x * z - y * w)) * s[0], 0.0,
            (2 * (x * y - z * w)) * s[1], (1 - 2 * (x * x + z * z)) * s[1],
            (2 * (y * z + x * w)) * s[1], 0.0,
            (2 * (x * z + y * w)) * s[2], (2 * (y * z - x * w)) * s[2],
            (1 - 2 * (x * x + y * y)) * s[2], 0.0,
            0.0, 0.0, 0.0, 1.0,
        ]
    t = node.get('translation', [0.0, 0.0, 0.0])
    m[12], m[13], m[14] = t[0], t[1], t[2]
    return m


def mul(a, b):
    """a * b, both column-major: the transform that applies b, then a."""
    out = [0.0] * 16
    for col in range(4):
        for row in range(4):
            out[col * 4 + row] = sum(a[k * 4 + row] * b[col * 4 + k]
                                     for k in range(4))
    return out


def world_translation(gltf, index, parents):
    """Where a node ends up in the scene, in glTF axes.

    The parent chain has to be multiplied, not just added up. The converter puts
    the Assetto-Corsa-to-glTF axis change on the root as a half turn about Y, so
    a node's own translation is still in AC's frame -- +X left, +Z forward --
    until that matrix is applied. Summing translations skips the rotation and
    reports every position mirrored in X and Z, which looks plausible and is
    wrong by the width of the car.
    """
    chain = []
    while index is not None:
        chain.append(local_matrix(gltf['nodes'][index]))
        index = parents.get(index)
    m = list(IDENTITY)
    for local in reversed(chain):        # root first
        m = mul(m, local)
    return m[12], m[13], m[14]


def main():
    ap = argparse.ArgumentParser(prog='read_hierarchy.py')
    ap.add_argument('model', help='a .gltf or .glb written by kn5-to-gltf')
    ap.add_argument('--tree', action='store_true',
                    help='print the whole node tree instead of the summary')
    a = ap.parse_args()

    if not os.path.isfile(a.model):
        sys.exit('no such file: %s' % a.model)
    gltf = load(a.model)
    nodes = gltf.get('nodes', [])
    parents = {}
    for i, n in enumerate(nodes):
        for c in n.get('children', []):
            parents[c] = i

    by_name = {}
    for i, n in enumerate(nodes):
        if 'name' in n:
            by_name.setdefault(n['name'].upper(), i)

    print('%s' % os.path.basename(a.model))
    print('generator : %s' % gltf.get('asset', {}).get('generator', '?'))
    print('nodes     : %d   meshes: %d   materials: %d'
          % (len(nodes), len(gltf.get('meshes', [])),
             len(gltf.get('materials', []))))
    empties = sum(1 for n in nodes if 'mesh' not in n)
    print('transforms: %d nodes carry no geometry -- the useful part' % empties)
    if gltf.get('extensionsUsed'):
        print('extensions: %s' % ', '.join(gltf['extensionsUsed']))
    print('')

    if a.tree:
        roots = gltf['scenes'][gltf.get('scene', 0)]['nodes']

        def walk(i, depth):
            n = nodes[i]
            mark = '*' if 'mesh' in n else ' '
            print('%s%s %s' % ('  ' * depth, mark, n.get('name', '(unnamed)')))
            for c in n.get('children', []):
                walk(c, depth + 1)
        for r in roots:
            walk(r, 0)
        return 0

    print('%-14s %-18s %s' % ('role', 'node', 'position (x, y, z) in metres'))
    print('-' * 68)
    found = 0
    for role, pattern in ROLES:
        for corner in CORNERS:
            hit = [i for name, i in by_name.items() if pattern.match(name)
                   and name.upper().endswith('_' + corner)]
            if not hit:
                continue
            found += 1
            i = hit[0]
            x, y, z = world_translation(gltf, i, parents)
            print('%-14s %-18s %8.3f %8.3f %8.3f'
                  % (role if corner == 'LF' else '', nodes[i]['name'], x, y, z))
    if not found:
        print('(none -- is this a car? a track has no WHEEL_* or SUSP_* nodes)')
    else:
        print('')
        print('In glTF axes: +X right, +Y up, -Z forward. A car is about 4 m '
              'long,\nso a front wheel sits near -Z and a rear one near +Z.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
