---
title: FAQ
description: Frequently asked questions about converting Assetto Corsa .kn5 models to glTF and GLB - formats, encryption, licensing, Blender, tracks and physics data.
---

# FAQ

## Does it convert cars, or tracks, or both?

Both. Assetto Corsa ships both in the same `.kn5` container. A car is one file;
a track is several placed by a `models_*.ini`, so you point at the ini instead.
See [cars](cars.md) and [tracks](tracks.md).

## Can it write GLB?

Yes - pass [`--glb`](cli.md#glb). You get one self-contained file with the
geometry and every texture inside it. Without the flag you get `.gltf`, `.bin`
and loose PNGs, which is what you want if you plan to edit textures.

## Can it convert glTF back to `.kn5`?

No, and there is no plan to. This is a one-way reader. Writing `.kn5` means
getting a reverse-engineered format right well enough for the game to load it,
which is a different project with a different risk profile.

## Why does my car come out white?

Because the livery lives outside the model and the textures inside the `.kn5`
are the export-time template. Use `--skin`. This is the single most common
question - [the long answer](cars.md#liveries-and-paint).

## Why won't it convert this car?

Almost certainly Custom Shaders Patch encryption. The tool refuses those on
purpose: the plain section of an encrypted file contains decoys, so a
"successful" conversion produces a car with boxes for wheels.
[Why](limitations.md#csp-encrypted-models-are-refused).

## Does it decrypt CSP-encrypted models?

No, and it will not. See above.

## Do I need Assetto Corsa installed?

To convert, you need the content - which normally means an install. To run the
test suite or work on the tool, no: the tests write their own `.kn5`.

## Does it need Blender?

No. It is a standalone command-line tool; Pillow is its only dependency.
Blender is one of the things you can open the result *in* - see
[the workflow guide](workflow.md).

## Does it export physics, tyres or setups?

No. `data.acd` is Assetto Corsa's encrypted physics archive and is not read at
all. The one physics-adjacent thing exported is a track's **surface map** -
which mesh is tarmac, kerb or wall, with the friction values - as
[a JSON sidecar](tracks.md#the-surfaces-sidecar).

## Does it export animations, doors or wipers?

No. `.ksanim` files are not read, and skinned meshes come across as static
geometry. [Limitations](limitations.md#no-skinning-and-no-animation).

## What happens to the wheel and suspension nodes?

They survive, named and positioned. That is the main reason to use this rather
than a converter that flattens the tree - a car brings around 250 nodes with no
geometry on them, and they are the useful part.
[More](output.md#the-node-hierarchy).

## Why are some meshes missing from the output?

By design, three kinds: `*_BLUR`, `*_DAMAGE`, and the low-resolution half of an
in-file LOD pair. Assetto Corsa swaps those at runtime and a static glTF cannot,
so keeping them produces z-fighting and solid discs over the spokes. Pass
`--keep-variants` to keep them.
[More](cars.md#lod-twins-and-runtime-variants).

## Are the materials physically accurate?

They are as close as the two shading models get, and the mapping is documented
line by line in [The glTF output](output.md#materials). Assetto Corsa is a
Blinn-Phong-era renderer with per-material knobs glTF has no slot for; the
conversions that exist are arithmetic rather than guesswork, and the ones that
do not are left out rather than faked. Expect a good starting point, not a
match.

## Can I publish a converted car?

That is a licensing question, not a technical one, and the answer is usually
no. Assetto Corsa's stock content belongs to Kunos Simulazioni and mod content
to whoever made it; converting a file does not change who owns it. Use this for
content you already have, for your own projects, and check with the author
before redistributing anything.

This repository ships no Assetto Corsa content for exactly that reason - the
tests build their own model.

## How fast is it?

About seven seconds for a car, forty for a large track, on an ordinary desktop.
Most of it is decoding textures and baking roughness maps.

## Does it run on Linux and macOS?

Yes. Python 3.9+ and Pillow, nothing platform-specific. You need the Assetto
Corsa content, which does not have to be on the same machine as the game.

## Is it safe to point at my Steam install?

It only reads. Nothing is written outside the output directory you name.
`kn5-studio` without `--out` writes to a temporary folder and deletes it on
exit, and its server binds `127.0.0.1` and refuses to serve anything but the
viewer and the converted model.

## Something is wrong and it is not in here

[Troubleshooting](troubleshooting.md) covers the failure modes with known
causes. Beyond that, open an issue with the command, the output, and the car or
track: <https://github.com/semiloker/assetto-corsa-gltf/issues>.
