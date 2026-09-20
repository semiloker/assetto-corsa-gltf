---
title: Assetto Corsa to glTF — documentation
description: How to convert Assetto Corsa .kn5 cars and tracks to glTF 2.0 or GLB, keeping the node hierarchy, liveries and PBR materials.
---

# Assetto Corsa → glTF documentation

`assetto-corsa-gltf` reads the `.kn5` files Assetto Corsa ships its cars and
tracks in and writes **glTF 2.0** — either a `.gltf` with a `.bin` and loose
PNG textures, or a single self-contained `.glb`.

It is a command-line tool and a Python package. Pillow is its only dependency.

```console
$ pip install assetto-corsa-gltf
$ kn5-to-gltf "…/content/cars/ks_mazda_mx5_nd/mazda_mx5_lod_a.kn5" out --glb
skin   : 00_soul_red_metallic (3 textures)
nodes  : 323  (153 transforms, 169 meshes, 0 empty, 12 variants dropped)
tris   : 168283
images : 61   materials: 55
glb    : 12.0 MB
wrote  : out/mazda_mx5_lod_a.glb
```

## Where to start

| If you want to | Read |
|---|---|
| Get it running | [Installation](installation.md), then [Quick start](quick-start.md) |
| Convert a car | [Converting cars](cars.md) |
| Convert a track | [Converting tracks](tracks.md) |
| Look before you convert | [Previewing with kn5-studio](preview.md) |
| Know every flag | [Command-line reference](cli.md) |
| Know what comes out | [The glTF output](output.md) |
| Open the result somewhere | [Blender, three.js and Unity](workflow.md) |
| Fix something | [Troubleshooting](troubleshooting.md) · [FAQ](faq.md) |
| Know what it will not do | [Limitations](limitations.md) |
| Work on the tool | [Development](development.md) |

## What it is for

The point of the converter is the **node hierarchy**. A car's `.kn5` carries
around 250 empty nodes alongside its meshes — wheel centres, suspension
pickups, the steering column, door hinges — already named and already
positioned. A track's mesh names carry its physics surfaces in a prefix.

A converter that flattens the tree throws all of that away and leaves a lump of
triangles. This one writes a glTF whose hierarchy matches the source one for
one, so `SUSP_LF`, `WHEEL_RF` and `STEER_HR` arrive as nodes you can find by
name and hang something off.

## What it reads

- **Cars** — one `.kn5`, plus the `skins/` folder beside it for liveries.
- **Tracks** — several `.kn5` placed by a `models_*.ini`, plus an optional
  `data/surfaces.ini` for the physics surface table.

See [Supported Assetto Corsa files](supported-files.md) for the details, and
[Limitations](limitations.md) for what it deliberately refuses — chiefly
CSP-encrypted models, where the plain section of the file is decoys.
