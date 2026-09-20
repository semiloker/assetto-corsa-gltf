---
title: Troubleshooting
description: Fixes for the common failures converting Assetto Corsa to glTF - a white car, a black car, missing textures, a model inside out, eight boxes instead of a car.
---

# Troubleshooting

Most of these have the same shape: the conversion succeeded and the result is
wrong. `--materials` is the flag that answers nearly all of them - it prints
what every material resolved to, which texture it took, and what base-colour
factor came out, with a `*` on each texture the chosen livery overrides.

```console
kn5-to-gltf <car.kn5> out --materials
```

## The car came out white

The `.kn5` carries whichever livery was loaded when it was exported, and on
most Kunos road cars that is the **blank template** - on `ks_mazda_mx5_nd` a
grey averaging (174, 174, 174). The real paint is in `skins/`, outside the
model.

```console
kn5-to-gltf <car.kn5> --list-skins          # what the car ships
kn5-to-gltf <car.kn5> out --skin 02_artic_white
```

Without `--skin` the first skin folder is used, which is what the game picks.
`--skin none` is what keeps the template. See
[Liveries and paint](cars.md#liveries-and-paint).

## The car came out black, or a material is invisible

Assetto Corsa's shader does not sample alpha on an opaque material, so nothing
in the game ever noticed that some textures decode to a **fully transparent
image** - the Lancer's `carpaint_evo`, `seatsao`, `dashao`, `carpet_ao` and
eight more do. A PBR renderer does sample it.

The converter drops alpha unless the material is actually alpha-blended or
alpha-tested, so this should not happen. If it does, `--materials` will show the
material and which texture it took, and that is the one to look at.

## The body did not change colour when I changed livery

Check whether that livery overrides the body's **detail** map at all:

```console
kn5-to-gltf <car.kn5> out --skin <name> --materials
```

A `*` next to the detail texture means the livery replaced it. No `*` means the
livery ships only an albedo, and on a car whose colour comes from `txDetail`
there is nothing for it to change. See
[where the colour comes from](cars.md#where-the-colour-actually-comes-from).

If the *wheels* changed and the body did not, you are looking at the wrong
material - rims are painted too, and on the MX-5 they carry more triangles than
the bodywork.

## The car is eight boxes

You converted `collider.kn5`. That is the physics hull. See
[Which .kn5 is the car?](cars.md#which-kn5-is-the-car).

## The car has no interior, or is very coarse

You converted `*_lod_b.kn5` or lower. The **top** detail model is
`<car_id>.kn5` or `*_lod_a.kn5` - Assetto Corsa's best LOD is `lod_A`, which
catches people out.

## The model is inside out

Not from this converter: the axis change is a rotation with determinant +1 and
no winding is touched ([why](output.md#coordinate-axes)). Look at the importer.
Unity's glTF importers mirror an axis to reach a left-handed space; a viewer
with backface culling off will confirm the geometry is fine.

## Textures are missing on Linux, macOS or a web server - but fine on Windows

This was a real bug, fixed in 1.0. Assetto Corsa matches texture names
case-insensitively, so a car can list `INT_DEcals.dds` and ask a material for
`INT_Decals.dds`; written out literally, the glTF named a file that existed only
under a different capitalisation.

The run now reports it:

```
folded : 1 texture names that differed only in case
```

If you are seeing this with files converted by an older build, re-convert.

## "refusing: … carries the CSP kn5 encryption trailer"

The model is encrypted by Custom Shaders Patch. Its textures and several of its
meshes are decoys in the plain section - 1×1 PNGs and 6 cm cubes - so a
"successful" conversion would silently produce a car with boxes for wheels. The
tool refuses instead of producing that.
[More](limitations.md#csp-encrypted-models-are-refused).

## Duplicated dashboards, wheels that are solid discs, dented panels

You passed `--keep-variants`. Those are Assetto Corsa's runtime swaps -
`*_BLUR`, `*_DAMAGE` and the low-res half of an in-file LOD pair - and a static
glTF cannot swap them.
[Why they are dropped](cars.md#lod-twins-and-runtime-variants).

## A corner of the suspension is missing

It should not be: the LOD rule only drops an `*_LR` mesh when an `*_HR` twin
exists, precisely because `_LR` usually means Left Rear. If you are seeing it,
that is a bug worth
[reporting](https://github.com/semiloker/assetto-corsa-gltf/issues) - include
the node names.

## The texture is upside down

Try `--flip-uv`. It should not be needed - glTF and DirectX agree on a top-left
UV origin - but a mod authored through Blender can arrive either way, and the
texture tells you in one look.

## A track is flat and lifeless

There is nothing to shade. Over a hundred of a typical track's materials carry
a diffuse and no normal map; Assetto Corsa hides that with its own shading and a
PBR renderer cannot. Try:

```console
kn5-to-gltf --models models.ini out --gen-normals 1.0
```

It infers shape from colour, so it flatters asphalt and brick and embosses
painted lane lines. Start at 1.0.

## "no kn5" / "unknown node type N at offset M"

The first means the file does not start with `sc6969` - it is not a `.kn5`.
The second means the parse desynced, which is worth
[reporting](https://github.com/semiloker/assetto-corsa-gltf/issues) with the
car it came from.

## The conversion is slow

Roughly seven seconds for a car and forty for a large track, most of it
decoding textures and baking roughness maps. That is expected. `kn5-studio`
re-uses decoded textures between liveries of the same car, which is why the
first colour takes six seconds and the rest take one.

---

Still stuck? Open an issue with the command you ran, the tool's output, and the
car or track it came from:
<https://github.com/semiloker/assetto-corsa-gltf/issues>
