---
title: Supported Assetto Corsa files
description: Which Assetto Corsa files the converter reads — .kn5 model versions, skins folders, models_*.ini, surfaces.ini — and which it does not.
---

# Supported Assetto Corsa files

## `.kn5` — the model container

The format Assetto Corsa ships both cars and tracks in. It is a plain container:
a texture table, a material table, and a node tree carrying the geometry.

| | |
|---|---|
| **Versions read** | 5 and 6. A v6 file carries one extra header word before the texture count; anything above 5 is handled the same way. |
| **Node types** | `DUMMY` (transform), `MESH`, `SKINNED`. |
| **Per mesh** | positions, normals, UVs, tangents, indices, material index. |
| **Per material** | name, shader name, scalar properties, texture slots, alpha-blend and alpha-test flags. |
| **Textures** | DDS blobs, decoded to PNG. |

Skinned meshes are read for their geometry. Their bone matrices are parsed and
skipped — see [Limitations](limitations.md#no-skinning-and-no-animation).

The layout is community-reverse-engineered. Two details are easy to get wrong
and each costs an afternoon: a material's `depthMode` is an `int32` and not a
byte, and a `SKINNED` node ends at `lodOut` where a `MESH` continues with a
bounding sphere and an `isRenderable` byte. Reading that byte anyway desyncs the
rest of the tree, which is why a third of a car library can appear to "fail to
parse" — every car with a skinned gear lever or steering column.

**Encrypted files are refused.** A `.kn5` carrying the CSP
`__AC_SHADERS_PATCH_KN5ENC_v1__` trailer keeps its textures and shader
parameters encrypted, and the meshes left in the plain section are decoys. See
[why it refuses rather than trying](limitations.md#csp-encrypted-models-are-refused).

Of the 219 entries in a stock `content/cars`, 215 parse, 2 are encrypted and
refused, and none fail.

## `skins/<name>/` — liveries

A car folder's `skins/` directory. Each subfolder is one livery: DDS files that
override same-named textures inside the `.kn5` at load time.

Read for `--skin` and `--list-skins`. Matched case-insensitively, as the game
does. A livery's `*_MAP.dds` and its plate and badge sheets are picked up too,
not only the albedo. See [Liveries and paint](cars.md#liveries-and-paint).

## `models_*.ini` — track layout

```ini
[MODEL_0]
FILE=magione.kn5
POSITION=0,0,0
ROTATION=0,0,0
```

Every `[MODEL_n]` section with a `FILE` is read; `POSITION` and `ROTATION` are
honoured, defaulting to zero and tolerating malformed values. Paths resolve
relative to the ini. See [Converting tracks](tracks.md).

## `data/surfaces.ini` — physics surfaces

```ini
[SURFACE_0]
KEY=TARMACA
FRICTION=0.99
DAMPING=0
IS_VALID_TRACK=1
```

Every `[SURFACE_n]` with a `KEY` is read. Six fields are kept — `friction`,
`damping`, `dirtAdditive`, `validTrack`, `pitlane`, `vibrationGain` — which are
the ones a collider or a grip model can act on. The rest of the block is sound
and force feedback.

Written out as [a JSON sidecar](tracks.md#the-surfaces-sidecar), not into the
glTF.

## What is not read

| | |
|---|---|
| `data.acd` | the encrypted physics archive — tyres, suspension rates, gearing, aero |
| `.knh` | driver position and hierarchy files |
| `ai/*.ai` | racing lines |
| `cameras*.ini`, `audio_sources.ini` | track furniture |
| `ui/*.json`, `ui/*.png` | car and track metadata, badges, preview images |
| `animations/*.ksanim` | door, wing and wiper animations |
| `sfx/` | audio banks |

This is a geometry and material converter. See [Limitations](limitations.md).
