---
title: Quick start
description: Convert your first Assetto Corsa car to GLB in one command, pick a livery, and open the result in Blender or a glTF viewer.
---

# Quick start

Five minutes, one car, one file out.

## 1. Convert a car

Point `kn5-to-gltf` at the car's top-detail `.kn5` and give it an output
directory. `--glb` asks for a single self-contained file:

```console
$ cd "C:\Program Files (x86)\Steam\steamapps\common\assettocorsa\content\cars"
$ kn5-to-gltf ks_mazda_mx5_nd/mazda_mx5_lod_a.kn5 out --name mx5 --glb
skin   : 00_soul_red_metallic (3 textures)
nodes  : 323  (153 transforms, 169 meshes, 0 empty, 12 variants dropped)
tris   : 168283
images : 61   materials: 55
folded : 1 texture names that differed only in case
glb    : 12.0 MB
wrote  : out/mx5.glb
```

`out/mx5.glb` is the whole car — geometry, hierarchy and all 61 textures.
Drag it into <https://gltf-viewer.donmccurdy.com/>, Blender, or three.js.

Leave `--glb` off and you get `mx5.gltf`, `mx5.bin` and the PNGs beside them
instead, which is what you want if you intend to edit the textures. See
[The glTF output](output.md).

## 2. Pick a different livery

An Assetto Corsa livery lives **outside** the model, in `skins/`. The textures
inside the `.kn5` are whatever was loaded at export time, which on most Kunos
road cars is the blank template — that is why a naive import arrives white.

List what the car ships:

```console
$ kn5-to-gltf ks_mazda_mx5_nd/mazda_mx5_lod_a.kn5 --list-skins
# car	mazda_mx5_lod_a
skin	00_soul_red_metallic	EXT_Carpaint	7E0100	23554	skin
skin	01_jet_black_mica	EXT_Carpaint	0F0E0E	23554	skin
skin	02_artic_white	EXT_Carpaint	D5D2D0	23554	skin
…
```

The first line of each livery is its bodywork, with the colour it paints it.
Convert with one:

```console
$ kn5-to-gltf ks_mazda_mx5_nd/mazda_mx5_lod_a.kn5 out --skin 02_artic_white --glb
```

Without `--skin` the first livery is used, which is what the game itself picks.
[More on liveries and paint](cars.md#liveries-and-paint).

## 3. Look before you convert

If you would rather see the car first:

```console
$ kn5-studio ks_mazda_mx5_nd/mazda_mx5_lod_a.kn5
```

That converts it, serves it to a local page and opens your browser. Clicking a
livery re-converts and reloads. Nothing is written outside a temporary folder
unless you pass `--out`. [More on kn5-studio](preview.md).

You can also hand it a whole `content/cars` folder and get a car picker:

```console
$ kn5-studio "C:\Program Files (x86)\Steam\steamapps\common\assettocorsa\content\cars"
```

## 4. Convert a track

A track is several `.kn5` placed by a `models_*.ini`, so you point at the ini
rather than at a model:

```console
$ cd "…/content/tracks/magione"
$ kn5-to-gltf --models models.ini out --name magione --surfaces data/surfaces.ini
2 models from models.ini
  + magione.kn5                           2380876 tris
  + 100.kn5                                    64 tris
nodes  : 1153  (189 transforms, 963 meshes, 0 empty, 0 variants dropped)
tris   : 2380940
images : 61   materials: 48
bin    : 165.5 MB
surfaces: 174 meshes matched a key, 80 walls, 38 physics-on but unkeyed, 671 visual  (of 963)
wrote  : out/magione.gltf
```

`--surfaces` additionally writes `magione.surfaces.json`, a sidecar that says
which mesh is tarmac, which is kerb and which is a wall, with the friction
values from the game. [More on tracks](tracks.md).

## Next

- [Command-line reference](cli.md) — every flag
- [The glTF output](output.md) — what the file actually contains
- [Blender, three.js and Unity](workflow.md) — opening the result
- [Troubleshooting](troubleshooting.md) — when it comes out white, black or inside out
