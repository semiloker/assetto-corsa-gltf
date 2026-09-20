# assetto-corsa-gltf

**Convert Assetto Corsa `.kn5` cars and tracks to glTF 2.0 or a single GLB - with the node hierarchy, liveries and PBR materials intact.**

[![CI](https://github.com/semiloker/assetto-corsa-gltf/actions/workflows/ci.yml/badge.svg)](https://github.com/semiloker/assetto-corsa-gltf/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/assetto-corsa-gltf.svg)](https://pypi.org/project/assetto-corsa-gltf/)
[![Python](https://img.shields.io/pypi/pyversions/assetto-corsa-gltf.svg)](https://pypi.org/project/assetto-corsa-gltf/)
[![Licence](https://img.shields.io/badge/licence-MIT-blue.svg)](LICENSE)

**[Documentation](https://semiloker.github.io/assetto-corsa-gltf/)** ·
**[Quick start](https://semiloker.github.io/assetto-corsa-gltf/docs/quick-start/)** ·
**[CLI reference](https://semiloker.github.io/assetto-corsa-gltf/docs/cli/)**

---

```console
$ pip install assetto-corsa-gltf
$ kn5-to-gltf ks_mazda_mx5_nd/mazda_mx5_lod_a.kn5 out --name mx5 --glb
skin   : 00_soul_red_metallic (3 textures)
nodes  : 323  (153 transforms, 169 meshes, 0 empty, 12 variants dropped)
tris   : 168283
images : 61   materials: 55
glb    : 12.0 MB
wrote  : out/mx5.glb
```

`out/mx5.glb` is the whole car - geometry, hierarchy and all 61 textures in one
file. Drop it into Blender, three.js, Unity, Godot or any glTF viewer.

<img src="assets/kn5-studio.png" width="820"
     alt="kn5-studio in a browser: a converted Mazda MX-5 ND in Soul Red on a dark grid, with the car's seven liveries listed down the left and a header reading 169 meshes, 168,283 triangles, 1.89 x 1.26 x 3.91 m.">

<sub>`kn5-studio` - look at a car and click through its liveries before importing
it. Model: `ks_mazda_mx5_nd`, © Kunos Simulazioni. Shown to illustrate the tool;
**no Assetto Corsa content is distributed with this project.**</sub>

## Why this one

The point is the **node hierarchy**. A car's `.kn5` carries around 250 nodes with
no geometry on them - wheel centres, suspension pickups, the steering column,
door hinges - already named and already positioned. A track's mesh names carry
its physics surfaces in a prefix. A converter that flattens the tree throws all
of that away and leaves a lump of triangles.

This one writes a glTF whose hierarchy matches the source one for one, so
`SUSP_LF`, `WHEEL_RF` and `STEER_HR` arrive as nodes you can find by name.

It also gets the things that are easy to get quietly wrong:

- **Liveries.** An Assetto Corsa livery lives *outside* the model, and on most
  Kunos road cars the body colour is not even in the diffuse - it is a flat
  detail map the shader multiplies over a shared grey sheet. That is why naive
  imports arrive white. `--skin` resolves the paint the game would actually use.
- **Runtime variants.** `*_BLUR`, `*_DAMAGE` and the low-resolution half of an
  in-file LOD pair are things the game swaps at runtime. Exported alongside the
  originals they z-fight and put opaque discs over the spokes, so they are
  dropped - but `_LR` means *Left Rear* far more often than low-res, so the rule
  tests for an `_HR` twin instead of matching the suffix.
- **Materials.** Specular exponent *and intensity* become roughness;
  `fresnelMaxLevel` becomes `KHR_materials_specular`; car paint's second, much
  tighter sun lobe becomes `KHR_materials_clearcoat`, which is what makes paint
  read as paint rather than as moulded plastic.
- **Encrypted models are refused**, not half-converted. The plain section of a
  CSP-encrypted `.kn5` is decoys - 1×1 textures and 6 cm cubes.

Of the 219 entries in a stock `content/cars`, **215 convert, 2 are encrypted and
refused, and none fail**.

## Install

```console
pip install assetto-corsa-gltf
```

Python 3.9+. [Pillow](https://pypi.org/project/Pillow/) is the only dependency;
everything else is the standard library. Windows, macOS and Linux.

Three commands land on your `PATH`:

| Command | Does |
|---|---|
| `kn5-to-gltf` | the conversion - cars and tracks |
| `kn5-studio` | preview a car in a browser, and click through its liveries |
| `kn5-survey` | scan a car library for modelled suspension geometry |

## Usage

**A car**, with a chosen livery, as one self-contained file:

```console
kn5-to-gltf ".../content/cars/ks_mazda_mx5_nd/mazda_mx5_lod_a.kn5" out \
    --name mx5 --skin 02_artic_white --glb
```

**List the liveries a car ships**, and the colour each one paints it:

```console
$ kn5-to-gltf ".../mazda_mx5_lod_a.kn5" --list-skins
# car	mazda_mx5_lod_a
skin	00_soul_red_metallic	EXT_Carpaint	7E0100	23554	skin
skin	01_jet_black_mica	EXT_Carpaint	0F0E0E	23554	skin
skin	02_artic_white	EXT_Carpaint	D5D2D0	23554	skin
```

The first line of each livery is its bodywork.

**A track** - several `.kn5` placed by a `models_*.ini` - plus its physics
surfaces as a JSON sidecar:

```console
$ kn5-to-gltf --models models.ini out --name magione --surfaces data/surfaces.ini
2 models from models.ini
nodes  : 1153  (189 transforms, 963 meshes, 0 empty, 0 variants dropped)
tris   : 2380940
surfaces: 174 meshes matched a key, 80 walls, 38 physics-on but unkeyed, 671 visual
wrote  : out/magione.gltf
```

**Preview before importing:**

```console
kn5-studio ".../content/cars"        # a folder gives you a car picker
```

Every flag is in the **[CLI reference](https://semiloker.github.io/assetto-corsa-gltf/docs/cli/)**.

## What it reads and writes

| Input | | Read |
|---|---|---|
| `.kn5` | the model container, cars and tracks, versions 5 and 6 | yes |
| `skins/<name>/` | liveries - DDS overriding the model's own textures | yes |
| `models_*.ini` | track layout: which models, where | yes |
| `data/surfaces.ini` | physics surfaces, friction and grip | yes, as a sidecar |
| `data.acd` | the encrypted physics archive | no |
| `.ksanim` | door, wing and wiper animations | no |
| CSP-encrypted `.kn5` | models with the Custom Shaders Patch trailer | refused, on purpose |

| Output | Contains |
|---|---|
| `.gltf` + `.bin` + `.png` | glTF 2.0, textures as separate files you can edit |
| `.glb` | the same model, geometry and every texture in one file |
| `.surfaces.json` | track meshes mapped to physics surfaces and walls |

## Limitations

No animation and no skinning - skinned meshes arrive as static geometry in bind
pose. No physics data beyond track surfaces. Track output is large: Magione is a
165 MB buffer, with no decimation and no Draco. Materials are an approximation,
because Assetto Corsa is a Blinn-Phong-era renderer; the conversions that exist
are arithmetic, and the ones that do not are left out rather than faked.

Full list: **[Limitations](https://semiloker.github.io/assetto-corsa-gltf/docs/limitations/)**.
Something wrong? **[Troubleshooting](https://semiloker.github.io/assetto-corsa-gltf/docs/troubleshooting/)**
covers white cars, black cars, eight boxes, and models that arrive inside out.

## Documentation

| | |
|---|---|
| [Installation](https://semiloker.github.io/assetto-corsa-gltf/docs/installation/) | pip, from source, where Assetto Corsa keeps its content |
| [Quick start](https://semiloker.github.io/assetto-corsa-gltf/docs/quick-start/) | one car, one file out, in five minutes |
| [Converting cars](https://semiloker.github.io/assetto-corsa-gltf/docs/cars/) | which `.kn5`, liveries, LOD twins and runtime variants |
| [Converting tracks](https://semiloker.github.io/assetto-corsa-gltf/docs/tracks/) | `models_*.ini` and the physics surfaces sidecar |
| [kn5-studio](https://semiloker.github.io/assetto-corsa-gltf/docs/preview/) | the preview viewer |
| [CLI reference](https://semiloker.github.io/assetto-corsa-gltf/docs/cli/) | every flag of all three commands |
| [The glTF output](https://semiloker.github.io/assetto-corsa-gltf/docs/output/) | hierarchy, axes, materials, textures, GLB packing |
| [Blender, three.js and Unity](https://semiloker.github.io/assetto-corsa-gltf/docs/workflow/) | opening the result |
| [FAQ](https://semiloker.github.io/assetto-corsa-gltf/docs/faq/) | formats, encryption, licensing |
| [Development](https://semiloker.github.io/assetto-corsa-gltf/docs/development/) | layout, tests, building the site |

There are runnable [`examples/`](examples/) too - batch conversion, reading the
hierarchy back, and a minimal three.js page.

## Development

```console
git clone https://github.com/semiloker/assetto-corsa-gltf.git
cd assetto-corsa-gltf
pip install -e ".[docs]"

python tests/test_convert.py     # and test_lod, test_paint, test_studio
python -m flake8 src tests
python scripts/build_site.py && python tests/test_site.py && node tests/test_search.js
```

No Assetto Corsa install is needed - [`tests/test_convert.py`](tests/test_convert.py)
writes its own `.kn5` rather than checking someone else's car into the
repository. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT - see [LICENSE](LICENSE).

three.js r160 (MIT) is vendored under `src/acgltf/viewer/three/` as a browser
dependency of `kn5-studio`; nothing else in the package loads it.

**This project is not affiliated with Kunos Simulazioni.** It ships no Assetto
Corsa content and grants no rights to any. Converting a file does not change who
owns it: stock content is Kunos', mod content belongs to whoever made it. Check
before redistributing anything.
