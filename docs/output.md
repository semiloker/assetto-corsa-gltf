---
title: The glTF output
description: What the converter writes - glTF 2.0 node hierarchy, PBR materials from Assetto Corsa shader parameters, texture handling, coordinate axes, and GLB packing.
---

# The glTF output

Everything here is **glTF 2.0**. Two layouts, chosen with
[`--glb`](cli.md#glb):

| | Files | Use it when |
|---|---|---|
| default | `<name>.gltf`, `<name>.bin`, one `.png` per texture | you want to edit or replace textures |
| `--glb` | `<name>.glb` | you want one file to hand over, drop into a viewer, or ship |

Both describe the same model: same nodes, same meshes, same materials. Only the
container differs.

## The node hierarchy

The hierarchy **matches the source one for one**, and it is the reason to use
this converter rather than flattening the file into triangles.

A car's `.kn5` carries around 250 nodes with no geometry on them. They are
wheel centres, suspension pickups, the steering column, door hinges and the
driver position - named and positioned by whoever built the car. The MX-5
converts to 323 nodes, of which 153 are transforms only:

```
mx5                       ← the axis-change root (see below)
└─ BODY
   ├─ GEO_Body
   ├─ SUSP_LF
   │  ├─ WHEEL_LF
   │  ├─ RIM_LF
   │  └─ DISC_LF
   ├─ SUSP_RF …
   └─ COCKPIT_HR …
```

`node.name` is the `.kn5` node name verbatim, so anything that keys off those
names - a rig, a physics setup, a shader assignment - keeps working.

A `DUMMY` node's matrix is copied straight across. `.kn5` stores a DirectX
row-major matrix and glTF wants column-major; those two layouts hold the *same
bytes* for the same transform, so this is a copy and not a transpose.

## Coordinate axes

`.kn5` is **+X left, +Z forward**, right-handed, counter-clockwise winding.
glTF is **+X right, −Z forward**, also right-handed and counter-clockwise.

The two differ by a **half turn about Y**, which is applied as a matrix on a
single root node:

```json
{ "name": "mx5", "matrix": [-1,0,0,0, 0,1,0,0, 0,0,-1,0, 0,0,0,1], "children": [ … ] }
```

Its determinant is +1 - a rotation, not a mirror - so the winding stays valid
and **no normal, tangent or index is touched**. A converter that mirrors an
axis instead flips the winding on every triangle in the car, and the model
renders inside out under backface culling.

The handedness of the source was measured rather than assumed: the signed
volume of the closed body shells and of all four tyres comes out positive.

## Meshes and vertex attributes

Every mesh primitive carries `POSITION`, `NORMAL`, `TEXCOORD_0` and `TANGENT`,
all `FLOAT`. Indices are `UNSIGNED_SHORT`, or `UNSIGNED_INT` where a mesh needs
more than 65 535 vertices.

`.kn5` tangents are `vec3` and glTF wants handedness in `w`. The source does
not record it, so `w` is 1.

**Non-finite values are scrubbed.** Real cars carry NaN: the Honda's dash-light
meshes have NaN tangents and three of its dummies have an all-NaN matrix. Left
alone they reach the JSON, where Python writes a bare `NaN` token - which is
not valid JSON and is rejected by every glTF loader even though the file parses
in Python. Positions fall back to the origin, normals to +Y, tangents to a
perpendicular of the normal, and a NaN matrix is dropped. The run reports how
many.

## Materials

Assetto Corsa's shader parameters are mapped onto metallic-roughness as closely
as the two models get.

| Assetto Corsa | glTF |
|---|---|
| `txDiffuse` | `baseColorTexture` |
| `txDetail` (when `useDetail` is on) | `baseColorFactor` - see [where the colour comes from](cars.md#where-the-colour-actually-comes-from) |
| `ksSpecularEXP` × `ksSpecular` | `roughnessFactor` |
| `txMaps` R channel | `metallicRoughnessTexture` (green channel), `roughnessFactor` → 1 |
| `txNormal` | `normalTexture` |
| `fresnelMaxLevel` | `KHR_materials_specular.specularFactor` |
| `sunSpecular` / `sunSpecularEXP` | `KHR_materials_clearcoat` |
| `ksEmissive` | `emissiveFactor` |
| alpha-blended / alpha-tested | `alphaMode` `BLEND` / `MASK` |
| `ksAlphaRef` | `alphaCutoff` |

Everything is `metallicFactor: 0` - dielectric. Assetto Corsa has no metallic
workflow to carry over.

### Specular intensity is not optional

`ksSpecular` is an *intensity*, and ignoring it is why trees and grass came out
wet-looking: 56 of Mulholland's 61 materials set it to 0.000 - no specular at
all in the game - and every one of them was being handed a full dielectric
highlight at roughness 0.4. It folds into the exponent the same way the `txMaps`
red channel does, because an intensity multiplier scales the peak of the Blinn
lobe, which is exactly what the exponent does.

Multilayer shaders park their specular elsewhere: they set `ksSpecular` to 0 and
drive the sheen from `tarmacSpecularMultiplier` instead. Taken at face value the
*road* comes out as matte as the grass beside it. `fresnelMaxLevel` is the
author's own switch for "a reflection was asked for here", so the multiplier
only applies where it is set.

### Car paint gets a second lobe

A carpaint material in Assetto Corsa carries **two** highlights. `ksSpecularEXP`
is the base coat - the wide sheen off the aluminium flake in the pigment.
`sunSpecular` / `sunSpecularEXP` is the clear lacquer over it: a separate, much
brighter, much tighter lobe fed by the sun alone. Averaged into one GGX the
needle-sharp glint that reads as *paint* comes out a soft blob, and the car
reads as moulded plastic.

So `sunSpecular` becomes `KHR_materials_clearcoat`. Only paint sets it - the
MX-5's leather, stitching, carpet and glass all leave it out - which makes the
parameter's presence the author's own marker for "this panel is painted", and a
better classifier than any name match.

### Extensions used

- **`KHR_materials_specular`** - from `fresnelMaxLevel`, Assetto Corsa's cap on
  how much a surface may reflect. glTF's dielectric Fresnel has no such knob; it
  runs 0.04 head-on to 1.0 at the silhouette. Black trim and window glass carry
  a near-black diffuse, so the reflection *is* their appearance, and uncapped a
  curved moulding renders as nothing but sky.
- **`KHR_materials_clearcoat`** - the lacquer, above. Carries a non-standard
  `flakeFactor` key inside it when the paint's detail map is a metal-flake
  sheet; a loader that does not know the key ignores it.

Both are declared in `extensionsUsed` and neither is required, so a loader
without them still renders the model.

## Textures

DDS blobs are decoded to PNG. Only textures a material actually asks for are
written.

**Alpha is dropped unless the material reads it** - which in Assetto Corsa means
the material is alpha-blended or alpha-tested. Two reasons, and the second is
not an optimisation: most of these maps carry a fully white alpha that costs a
third of the file for nothing, and *some carry a fully black one*. Assetto
Corsa's shader never samples alpha on an opaque material, so nothing in the game
noticed that the Lancer's `carpaint_evo`, `seatsao`, `dashao` and nine others
decode to a completely transparent image. A PBR renderer does sample it, and the
car arrived with no paint and no interior - the texture was there, and invisible.

`txNormal` is **not** always a normal map. On the damage shaders the slot holds
the dent map, which the game blends in proportion to accumulated damage - zero
on an undamaged car. Bound unconditionally it renders every panel permanently
caved in, so it is skipped.

Texture names that differ only in case are folded to one. Assetto Corsa is a
Windows game and matches names case-insensitively, so a car can list
`INT_DEcals.dds` and ask a material for `INT_Decals.dds` and still render -
`ks_mazda_mx5_nd` does. Written out literally the glTF names a file that exists
only under a different capitalisation, which loads on Windows by accident and
arrives untextured on Linux, on macOS, and from any case-sensitive web server.

## Inside a .glb

`--glb` puts the JSON and the binary in two chunks of one file. The images stop
being `uri` references and become `bufferView`s in the same binary chunk as the
vertices, which is the only shape GLB allows. Each keeps its filename in
`image.name`, so an extractor gives the textures back under the names the car
used rather than `image0`…`image61`.

The JSON chunk is padded with spaces and the binary chunk with zeros. That is
what the specification asks for and not an arbitrary choice: a parser is allowed
to hand the JSON chunk straight to a string reader, and trailing NULs there are
not valid JSON.

## What is written

| File | When |
|---|---|
| `<name>.gltf` | default |
| `<name>.bin` | default |
| `*.png` | default, one per texture used |
| `<name>.glb` | `--glb` |
| `<name>.surfaces.json` | `--surfaces` with `--models` - see [the sidecar](tracks.md#the-surfaces-sidecar) |

`asset.generator` records the tool and version that wrote the file, so a
converted model can be traced back to a build.
