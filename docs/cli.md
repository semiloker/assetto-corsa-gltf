---
title: Command-line reference
description: Every flag of kn5-to-gltf, kn5-studio and kn5-survey - skins, variants, normal generation, surfaces, GLB output.
---

# Command-line reference

Three commands are installed: [`kn5-to-gltf`](#kn5-to-gltf) converts,
[`kn5-studio`](#kn5-studio) previews, [`kn5-survey`](#kn5-survey) scans a
library. Each also runs as a module (`python -m acgltf.convert`, `.studio`,
`.survey`) if the scripts are not on your `PATH`.

## kn5-to-gltf

```
kn5-to-gltf <car.kn5> <outdir> [options]
kn5-to-gltf --models <models_*.ini> <outdir> [options]
kn5-to-gltf <car.kn5> --list-skins
```

### Positional arguments

| Argument | Meaning |
|---|---|
| `kn5` | a single `.kn5` - a car. Omitted when `--models` is used. |
| `outdir` | where to write. Created if missing. Optional only for `--list-skins`, which writes nothing. |

### Options

#### `--models <models_*.ini>` { #models }

Convert a **track** instead of a car: read the `[MODEL_n]` sections of an
Assetto Corsa `models_*.ini` and place each `.kn5` it names at the `POSITION`
and `ROTATION` given. All of them go into one glTF. See
[Converting tracks](tracks.md).

If the ini names a file that is not there, the tool stops and lists the missing
ones rather than writing a partial track.

#### `--surfaces <data/surfaces.ini>` { #surfaces }

Read the track's physics surface table and write `<name>.surfaces.json` beside
the glTF: which mesh is which surface, which meshes are walls, and the
friction, damping and dirt values for each key. Only meaningful with
`--models`. See [The surfaces sidecar](tracks.md#the-surfaces-sidecar).

#### `--name <NAME>` { #name }

Basename for the output. Defaults to the `.kn5`'s filename, or the ini's, which
means a car converted straight out of its folder is called
`mazda_mx5_lod_a` unless you say otherwise.

#### `--glb` { #glb }

Write one self-contained `<name>.glb` instead of the `.gltf` / `.bin` / PNG
set. The geometry and every texture end up in a single file, which is what a
viewer, a web page or an asset pipeline wants. The loose files produced along
the way are removed once their bytes are inside it.

Use the default (no `--glb`) when you want to edit or replace textures - in a
`.glb` they are bytes inside a binary chunk, not files you can open.

#### `--skin <NAME>` / `--skin none` { #skin }

Take textures from the car's `skins/<NAME>/` folder. Defaults to the first
skin, which is what Assetto Corsa itself picks when nothing says otherwise.

`--skin none` keeps the textures embedded in the `.kn5`. On most cars those are
the export-time template - usually grey primer - which is
[why an import comes out white](troubleshooting.md#the-car-came-out-white).

An unknown name is an error, and the message lists the skins the car has.

#### `--list-skins` { #list-skins }

Write nothing; print every livery the car ships and the colour each one paints
it, as tab-separated lines:

```
# car	mazda_mx5_lod_a
skin	00_soul_red_metallic	EXT_Carpaint	7E0100	23554	skin
```

The columns are `skin`, livery name, material, `RRGGBB`, triangle count, and
whether the colour came from the livery folder (`skin`) or from the `.kn5`
itself (`kn5`). Materials are ordered so the **first line of each livery is its
bodywork** - a tool that wants one swatch per livery takes exactly that line.
Anything else on stdout starts with `#`.

A livery whose paint is a pattern rather than a flat colour is still listed,
with `-` for the swatch.

#### `--materials` { #materials }

Print what every material resolved to: its diffuse, its paint slot, and the
base-colour factor that came out, with a `*` on each texture the chosen skin
overrides. This is the answer to "the body did not change colour" and to "the
car came out black". See [Troubleshooting](troubleshooting.md).

#### `--keep-variants` { #keep-variants }

Keep the runtime variants that are dropped by default: `*_BLUR`, `*_DAMAGE`,
and the low-resolution `*_LR` half of an in-file LOD pair.

Assetto Corsa swaps these in and out at runtime and a static glTF cannot.
Exported alongside the originals they do not read as extra detail, they read as
a broken model: the damage shells sit a fraction of a millimetre off the clean
panels and z-fight with them, and the blurred wheels are opaque discs over the
spokes. See [LOD twins and runtime variants](cars.md#lod-twins-and-runtime-variants).

#### `--gen-normals [STRENGTH]` { #gen-normals }

Fabricate a tangent-space normal map from the albedo for every material that
has none. Off by default; `--gen-normals` alone means 1.0, and 2 is strong.

This exists for tracks. Magione and Mulholland have well over a hundred
materials carrying a diffuse and nothing else - the surfaces are flat by
construction, and Assetto Corsa hides it with its own shading. Under a PBR
renderer that flatness is all you see.

It infers shape from colour, so it flatters asphalt, gravel and brick, and
embosses painted lane lines that should be flush. Never applied to a material
that already has a normal map, and never to a cutout.

#### `--flip-uv` { #flip-uv }

Negate V. glTF and DirectX agree on a top-left UV origin, so this should **not**
be needed. It is here because a mod authored through Blender can arrive either
way, and the texture tells you in one look.

#### `--version`, `-h` / `--help` { #version }

Print the version, or the built-in help.

### Exit status

`0` on success. Non-zero with a message on stderr for: a file that is not a
`.kn5`, a `models_*.ini` naming files that are missing, an unknown `--skin`, or
a model carrying the CSP encryption trailer
([why it refuses](limitations.md#csp-encrypted-models-are-refused)).

---

## kn5-studio

```
kn5-studio <CAR-OR-FOLDER> [--out DIR] [--name NAME] [--port 8731] [--no-open]
```

Converts a car, serves it to a local page and opens it. The page turns the
model round; clicking a livery re-converts and reloads. Ctrl-C stops it.

| Option | Meaning |
|---|---|
| `CAR-OR-FOLDER` | one `.kn5`, or a whole `content/cars` folder - in which case the page gets a car picker and nothing is converted until you choose one. |
| `--out DIR` | keep the converted glTF here. **Without it nothing is kept**: the conversion goes to a temporary folder deleted when the tool stops. |
| `--name NAME` | basename for the `.gltf`. |
| `--port N` | default `8731`. |
| `--no-open` | do not launch a browser; just print the URL. |

The server binds `127.0.0.1` and serves only the viewer and the converted
model - never the directory you started it from. See
[Previewing with kn5-studio](preview.md).

---

## kn5-survey

```
kn5-survey <content/cars> [--top N]
```

Scan a car library and rank cars by how much **suspension geometry** is
actually modelled - wishbones, dampers, pushrods, anti-roll bars - as opposed
to merely present as empty nodes.

Every Assetto Corsa car has `SUSP_LF/RF/LR/RR` dummies, because that is how the
game hangs the wheels; they exist even when nothing is drawn there. What this
counts is real geometry parented under them, excluding the rim/tyre/disc/caliper
cluster that every car carries regardless.

```console
$ kn5-survey "…/content/cars" --top 5
scanned 215 cars   (2 encrypted, skipped   0 failed)

car                                       kinds  parts     tris  car tris  named linkage
--------------------------------------------------------------------------------------
ks_lotus_72d                                 36     36    25027    171239  -
ks_ferrari_f138                              32     32    52418    113226  -
ks_lamborghini_aventador_sv                  28     28     5238    262261  -
```

`kinds` is how many distinct named parts hang off the suspension roots, `parts`
how many meshes, `tris` their triangles, `car tris` the whole car's. Ranking is
on the pair, because either number alone lies: triangles alone favour one dense
blob, part count alone favours four token cubes.

Geometry is skipped while parsing, so a 200-car library takes seconds rather
than an hour.
