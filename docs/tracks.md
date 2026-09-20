---
title: Converting tracks
description: Convert an Assetto Corsa track to glTF using its models_*.ini, and export the physics surfaces from surfaces.ini as a JSON sidecar.
---

# Converting tracks

A track is not one model. It is several `.kn5` placed in the world by a
`models_*.ini`, so you point the converter at the ini:

```console
kn5-to-gltf --models <models_*.ini> <outdir> [--name NAME] [--surfaces data/surfaces.ini]
```

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
          keys used : CONCRETE, CURB, CUT, KERB, OUT, PEN-GRS-A, PEN-GRS-B, PITLANE, TARMACA, TARMACB, TARMACC, TARMACD, TARMACE
          unkeyed   : GRASS, ROAD, SAND
wrote  : out/magione.gltf
```

## Which ini?

A track with one layout has `models.ini`. A track with several has one per
layout - `ks_brands_hatch` ships `models_gp.ini` and `models_indy.ini` - and
each names a different set of `.kn5`. Convert the layout you want.

Each `[MODEL_n]` section gives a `FILE`, a `POSITION` and a `ROTATION`, and all
of them are honoured: a model that is not at the origin gets its own transform
node in the output. Files are resolved relative to the ini.

If the ini names a file that is not there, the tool stops and lists the missing
ones rather than writing half a track.

## Expect it to be large

Tracks are an order of magnitude bigger than cars. Magione is 2.38 million
triangles and a 165 MB `.bin`; a modern laser-scanned circuit is more.

`--glb` works on tracks, but think before using it: it produces one file of
that size, and you cannot open a texture inside it. For track work the default
`.gltf` + `.bin` + PNG layout is usually the one you want.

`--gen-normals` is aimed squarely at tracks - see
[the flag's notes](cli.md#gen-normals). Over a hundred of Magione's
materials carry a diffuse and nothing else.

## The surfaces sidecar

`--surfaces data/surfaces.ini` reads the track's physics surface table and
writes `<name>.surfaces.json` beside the glTF.

It is a sidecar rather than glTF `extras` for two reasons: glTF has no concept
of a surface, and an extras blob on each of a few thousand nodes would bloat
the file for every consumer that does not want one. Keyed by node name, it is
readable by eye and a collider can read it directly.

```json
{
  "source": "surfaces.ini",
  "surfaces": {
    "CONCRETE": { "friction": 0.9, "damping": 0.0, "dirtAdditive": 0.0,
                  "validTrack": true, "pitlane": false, "vibrationGain": 0.1 },
    "CURB":     { "friction": 0.92, "damping": 0.0, "dirtAdditive": 0.0,
                  "validTrack": true, "pitlane": false, "vibrationGain": 1.0 }
  },
  "nodes":   { "01CONCRETE": "CONCRETE", "01CURB": "CURB", "01CURB001": "CURB" },
  "walls":   [ "01WALL", "01WALL001", "01WALL002" ],
  "unkeyed": { "01GRASS": "GRASS", "01GRASS004": "GRASS" }
}
```

| Field | What it holds |
|---|---|
| `surfaces` | the table from `surfaces.ini`, cut down to the fields a collider or grip model can act on |
| `nodes` | mesh name → surface key, for every mesh that matched one |
| `walls` | meshes prefixed `WALL` |
| `unkeyed` | mesh name → prefix, for meshes with physics on whose prefix names no key |

### How a mesh is classified

Assetto Corsa encodes physics in the **mesh name**: a leading digit means the
solver sees this mesh, and the text after it names the surface.

- **No leading digit** → scenery. The solver never sees it. 671 of Magione's
  963 meshes.
- **`WALL…`** → a barrier. `WALL` is deliberately absent from `surfaces.ini`:
  it has no friction, it is something you hit.
- **Matches a key** → that surface. The **longest** matching key wins, because
  the keys overlap: a track defining both `ROAD` and `RDOLD`, or `ASPH` and
  `ASPHNEW`, would have every mesh of the longer one swallowed by a
  shortest-match rule. Magione defines `TARMACA` through `TARMACE`.
- **Physics on, prefix names no key** → reported in `unkeyed` rather than
  dropped. Assetto Corsa falls back to the track default for these and there
  are a lot of them - Magione has meshes prefixed `GRASS`, `ROAD` and `SAND`
  with none of those keys defined. A caller may well want to give `GRASS` its
  own friction, and cannot if the tool silently discards it.

## What is not exported

The `.acd` data archive - the car and track physics data files - is not read at
all. Neither are AI lines, camera definitions, audio sources or the track map.
See [Limitations](limitations.md).
