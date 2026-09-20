#!/usr/bin/env python3
"""Convert a whole Assetto Corsa car folder to GLB, one file per car.

    python examples/batch_convert.py "<...>/content/cars" out
    python examples/batch_convert.py "<...>/content/cars" out --skin none --limit 5

Two things this has to get right, and both are the reason it is an example
rather than a one-line shell loop.

PICKING THE RIGHT FILE. Every .kn5 in a car folder is valid and every one of
them converts, so choosing wrongly fails silently -- `collider.kn5` produces
eight boxes and `*_lod_d.kn5` produces a silhouette, and both look like a broken
converter rather than like the wrong input. `top_model` below is the same rule
kn5-studio uses.

CARRYING ON. Two cars in a stock install carry the CSP encryption trailer and
the converter refuses them, as it should. A batch that stops on the first refusal
converts nothing; this one records it and moves to the next car.
"""
import argparse
import os
import re
import sys
import time

from acgltf import convert


def top_model(folder):
    """The car's top-detail .kn5 in `folder`, or None if there is no car in it.

    In order: a file named after the folder, then `*_lod_a.kn5` -- AC's best LOD
    is lod_A, which catches people out -- then the largest remaining file that is
    neither the collider nor a lower LOD.
    """
    car_id = os.path.basename(folder.rstrip(os.sep))
    named = os.path.join(folder, car_id + '.kn5')
    if os.path.isfile(named):
        return named

    files = [f for f in os.listdir(folder) if f.lower().endswith('.kn5')]
    lod_a = [f for f in files if f.lower().endswith('_lod_a.kn5')]
    if lod_a:
        return os.path.join(folder, lod_a[0])

    rest = [f for f in files
            if 'collider' not in f.lower()
            and not re.search(r'_lod_[b-z]\.kn5$', f, re.I)]
    if not rest:
        return None
    return os.path.join(folder, max(rest, key=lambda f: os.path.getsize(
        os.path.join(folder, f))))


def main():
    ap = argparse.ArgumentParser(prog='batch_convert.py')
    ap.add_argument('cars', help='an Assetto Corsa content/cars folder')
    ap.add_argument('outdir', help='where to write one <car_id>.glb per car')
    ap.add_argument('--skin', default=None,
                    help="livery to use; default is the car's first, "
                         "`none` keeps the kn5's own textures")
    ap.add_argument('--limit', type=int, default=0, help='stop after N cars')
    ap.add_argument('--gltf', action='store_true',
                    help='write .gltf + .bin + PNGs into a folder per car '
                         'instead of one .glb')
    a = ap.parse_args()

    folders = sorted(d for d in os.listdir(a.cars)
                     if os.path.isdir(os.path.join(a.cars, d)))
    if a.limit:
        folders = folders[:a.limit]

    done, refused, empty, failed = [], [], [], []
    started = time.time()

    for i, car_id in enumerate(folders, 1):
        folder = os.path.join(a.cars, car_id)
        kn5 = top_model(folder)
        if not kn5:
            empty.append(car_id)
            continue

        out = a.outdir if not a.gltf else os.path.join(a.outdir, car_id)
        print('[%d/%d] %s' % (i, len(folders), car_id))
        try:
            convert.convert(
                [{'file': kn5, 'pos': [0.0] * 3, 'rot': [0.0] * 3}],
                out, car_id, flip_uv=False, keep_variants=False,
                surfaces_ini=None, glb=not a.gltf,
                skin=convert.skin_dir(kn5, a.skin))
            done.append(car_id)
        except SystemExit as e:
            # How the converter refuses an encrypted model: a message, not a
            # traceback. Anything else that exits is a real failure.
            (refused if 'encryption trailer' in str(e) else failed).append(
                (car_id, str(e).splitlines()[0]))
        except Exception as e:                      # noqa: BLE001
            failed.append((car_id, '%s: %s' % (type(e).__name__, e)))
        print('')

    print('=' * 60)
    print('converted : %d of %d in %.0f s'
          % (len(done), len(folders), time.time() - started))
    if refused:
        print('encrypted : %d  (%s)'
              % (len(refused), ', '.join(c for c, _ in refused[:6])))
    if empty:
        print('no model  : %d  (%s)' % (len(empty), ', '.join(empty[:6])))
    if failed:
        print('failed    : %d' % len(failed))
        for car_id, why in failed[:10]:
            print('   %-40s %s' % (car_id, why[:70]))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
