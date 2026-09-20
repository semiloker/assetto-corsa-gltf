#!/usr/bin/env python3
"""Survey a folder of Assetto Corsa cars for MODELLED suspension.

    kn5-survey "<...>/content/cars" [--top 25]

Every AC car has SUSP_LF/RF/LR/RR dummies - they are how the game hangs the
wheels, and they exist even when nothing is drawn there. So their presence says
nothing. What matters for seeing a suspension work is whether real geometry is
parented under them: wishbones, dampers, pushrods, anti-roll bars. That is what
this counts.

Two numbers, because either alone lies. Triangles alone favours one dense blob;
part count alone favours four token cubes. A car worth looking at has both.

Geometry is skipped while parsing (kn5.load(geometry=False)) - this only needs
the tree and the counts, and unpacking every vertex of 200 cars would take an
hour to answer a question that takes seconds.
"""
import argparse
import glob
import os
import re
import sys

from . import kn5
from . import __version__

SUSP_ROOT = re.compile(r'^SUSP_(LF|RF|LR|RR)$', re.I)
# Parts that are suspension proper, as opposed to the hub/disc/caliper cluster
# every car carries whether or not its arms are modelled.
# The WHEEL CLUSTER. Most cars parent the rim, tyre, disc and caliper under
# SUSP_* as well, and counting those made a car with four detailed wheels and no
# arms outrank one with modelled wishbones - the first ranking this produced put
# an F1 car on top for having 9000-triangle rims. They are excluded so the score
# measures the linkage and nothing else.
WHEEL = re.compile(r'RIM|TYRE|TIRE|BLUR|DISC|DISK|CALIPER|BRAKE', re.I)
LINKAGE = re.compile(
    r'ARM|WISHBONE|WBONE|DAMPER|SHOCK|SPRING|COIL|PUSHROD|PUSH_ROD|PULLROD|'
    r'LINK|STRUT|TRAILING|KNUCKLE|SWAY|ANTIROLL|ANTI_ROLL|\bARB\b|TIEROD|'
    r'TIE_ROD|TRACKROD|ROCKER|BELLCRANK|HALFSHAFT|DRIVESHAFT', re.I)


def survey_car(path):
    m = kn5.load(path, geometry=False)
    meshes = tris = 0
    linkage = set()
    have_susp = False

    def under(n, inside):
        nonlocal meshes, tris, have_susp
        if SUSP_ROOT.match(n.name):
            have_susp = True
            inside = True
        if inside and n.type == kn5.MESH and n.ntris and not WHEEL.search(n.name):
            meshes += 1
            tris += n.ntris
            if LINKAGE.search(n.name):
                linkage.add(n.name)
        for c in n.children:
            under(c, inside)

    under(m.root, False)
    total = sum(n.ntris for n, _ in m.walk() if n.type == kn5.MESH)
    # Distinct part TYPES, corner suffix folded away: a car with one arm design
    # repeated at four corners has one type, not four. This is what separates a
    # modelled linkage from a wheel hub cloned about.
    kinds = set()

    def kinds_walk(n, inside):
        if SUSP_ROOT.match(n.name):
            inside = True
        if inside and n.type == kn5.MESH and n.ntris and not WHEEL.search(n.name):
            kinds.add(re.sub(r'(LF|RF|LR|RR|_L|_R)(?=$|_)', '*', n.name, flags=re.I))
        for c in n.children:
            kinds_walk(c, inside)

    kinds_walk(m.root, False)
    return {'susp': have_susp, 'meshes': meshes, 'tris': tris, 'kinds': len(kinds),
            'linkage': sorted(linkage), 'total_tris': total,
            'encrypted': m.encrypted}


def main():
    ap = argparse.ArgumentParser(prog='kn5-survey')
    ap.add_argument('cars')
    ap.add_argument('--top', type=int, default=25)
    ap.add_argument('--version', action='version',
                    version='%(prog)s ' + __version__)
    a = ap.parse_args()

    rows, failed, enc = [], [], []
    names = sorted(os.listdir(a.cars))
    for i, car in enumerate(names):
        d = os.path.join(a.cars, car)
        if not os.path.isdir(d):
            continue
        k5 = [f for f in glob.glob(os.path.join(d, '*.kn5'))
              if 'collider' not in os.path.basename(f).lower()
              and not re.search(r'_lod_[b-z]\.kn5$', f, re.I)]
        if not k5:
            continue
        big = max(k5, key=os.path.getsize)
        try:
            r = survey_car(big)
        except Exception as e:                     # noqa: BLE001
            failed.append((car, str(e)[:60]))
            continue
        if r['encrypted']:
            enc.append(car)
            continue
        r['car'] = car
        rows.append(r)
        if (i + 1) % 40 == 0:
            print('  ... %d/%d' % (i + 1, len(names)), file=sys.stderr)

    # Rank on the pair: parts carry the weight, triangles break ties. A car with
    # 20 separate arms beats one with a single dense moulded lump.
    rows.sort(key=lambda r: (r['kinds'], r['tris']), reverse=True)

    print('scanned %d cars   (%d encrypted, skipped   %d failed)'
          % (len(rows), len(enc), len(failed)))
    print()
    print('%-40s %6s %6s %8s %9s  %s' %
          ('car', 'kinds', 'parts', 'tris', 'car tris', 'named linkage'))
    print('-' * 118)
    for r in rows[:a.top]:
        print('%-40s %6d %6d %8d %9d  %s' %
              (r['car'][:40], r['kinds'], r['meshes'], r['tris'],
               r['total_tris'], ', '.join(r['linkage'][:2]) or '-'))
    if failed:
        print('\nfailed to parse:')
        for c, e in failed[:10]:
            print('  %-46s %s' % (c, e))


if __name__ == '__main__':
    main()
