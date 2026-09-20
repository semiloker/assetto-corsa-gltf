---
title: Installation
description: Install the Assetto Corsa to glTF converter with pip on Windows, Linux or macOS. Python 3.9 or newer, Pillow the only dependency.
---

# Installation

## Requirements

- **Python 3.9 or newer.**
- **[Pillow](https://pypi.org/project/Pillow/) 9 or newer**, installed
  automatically. It decodes the DDS textures inside a `.kn5` and writes the
  PNGs. Nothing else is required - everything else the tool uses is in the
  standard library.
- An **Assetto Corsa installation** to read from. The tool never writes to it.

You do not need Assetto Corsa itself to run the test suite, and you do not need
Blender, Node.js, or a GPU.

## From PyPI

```console
pip install assetto-corsa-gltf
```

## From source

```console
git clone https://github.com/semiloker/assetto-corsa-gltf.git
cd assetto-corsa-gltf
pip install -e .
```

## Check it worked

```console
$ kn5-to-gltf --version
kn5-to-gltf 1.0.0
```

Three commands are installed:

| Command | Does |
|---|---|
| `kn5-to-gltf` | the conversion - [reference](cli.md) |
| `kn5-studio` | preview a car in a browser before importing it - [guide](preview.md) |
| `kn5-survey` | scan a car library for modelled suspension - [guide](cli.md#kn5-survey) |

If your shell cannot find them, Python's script directory is not on your
`PATH`. Either add it, or run the same code as modules:

```console
python -m acgltf.convert --version
python -m acgltf.studio --help
python -m acgltf.survey --help
```

## Where Assetto Corsa keeps its content

The paths below are what you point the tool at. They are the same on every
install; only the Steam library root changes.

| | Path |
|---|---|
| Windows (default Steam library) | `C:\Program Files (x86)\Steam\steamapps\common\assettocorsa` |
| Cars | `<install>\content\cars\<car_id>\` |
| Tracks | `<install>\content\tracks\<track_id>\` |

Inside a car folder you are looking for the **top-detail** model, which is
either `<car_id>.kn5` or `*_lod_a.kn5`. See
[Which .kn5 is the car?](cars.md#which-kn5-is-the-car) - picking the wrong one
is the most common way to get a result that looks like a broken converter.

## Upgrading and uninstalling

```console
pip install --upgrade assetto-corsa-gltf
pip uninstall assetto-corsa-gltf
```
