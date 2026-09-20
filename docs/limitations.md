---
title: Limitations
description: What the Assetto Corsa to glTF converter deliberately does not do — CSP encryption, animations, skinning, physics data, and where the material mapping is approximate.
---

# Limitations

Written down rather than discovered.

## CSP-encrypted models are refused

A `.kn5` carrying the Custom Shaders Patch trailer
`__AC_SHADERS_PATCH_KN5ENC_v1__` keeps its textures and shader parameters
encrypted. What is left in the plain section is **decoys**: 1×1 PNGs where the
textures should be, and 6 cm cubes where several meshes should be.

So a converter that ignored the trailer would not fail — it would succeed, and
hand back a car with boxes for wheels and no paint, and the failure would look
like a bug in the converter. The tool stops with a message instead:

```
refusing: <file> carries the CSP kn5 encryption trailer.
Its textures and several meshes are decoys in the plain section, so the output
would be wrong without looking it.
```

Decryption is not implemented and will not be. In a stock install this affects
2 cars out of 219; in a heavily modded one it affects more.

## No skinning and no animation

Skinned meshes are read for their **geometry** — their bone matrices are parsed
and discarded, and the mesh arrives in bind pose as static geometry. `.ksanim`
files (doors, wings, wipers, the driver) are not read at all.

The node hierarchy *is* exported, so the pivots those animations act on are
present and positioned. Rebuilding the motion is left to whoever wants it.

## No physics data

`data.acd` — tyre models, suspension rates, gearing, aero, setup ranges — is
Assetto Corsa's encrypted physics archive and is not touched.

The exception is a track's surface table, which lives in a plain
`data/surfaces.ini` and is exported as
[a sidecar](tracks.md#the-surfaces-sidecar) when you ask for it.

## The material mapping is an approximation

Assetto Corsa is a Blinn-Phong-era renderer with per-material controls glTF has
no slot for. Every conversion that exists is arithmetic with a stated
derivation — see [Materials](output.md#materials) — but some things simply do
not carry:

- **`txMaps` green channel.** Documented as glossiness; on every map measured it
  is a flat 255. There is no variation to carry over, so only the red channel
  (specular intensity) is used.
- **Everything is dielectric.** `metallicFactor` is 0 everywhere. Assetto Corsa
  has no metallic workflow to map from, and inferring one from material names
  would be guessing.
- **`ksAlphaRef` is often unusable.** 14 of Mulholland's materials set it to
  0.0, and a glTF `MASK` at cutoff 0 passes every fragment — the whole texture
  card renders opaque, fringe and all. Anything below 0.02 falls back to glTF's
  default 0.5.
- **Multi-layer terrain shaders** are approximated by their base layer plus the
  `tarmacSpecularMultiplier` correction. Their blend masks are not reconstructed.
- **`flakeFactor`** on car paint is a non-standard key inside
  `KHR_materials_clearcoat`. Nothing standard reads it; loaders ignore what they
  do not know.

## Runtime variants are dropped by default

`*_BLUR`, `*_DAMAGE` and the low-resolution half of an in-file LOD pair are
removed unless you pass `--keep-variants`, because a static glTF cannot swap
them in and out the way the game does.
[The reasoning](cars.md#lod-twins-and-runtime-variants).

## One LOD per run

Each `.kn5` is a separate LOD, so converting `lod_a` and `lod_b` means two runs
and two outputs. There is no `MSFT_lod` packing.

## Track output is large

Magione is 2.38 million triangles and a 165 MB `.bin`, and it is a small
circuit. No decimation, no Draco compression, no texture recompression: the
converter writes what the source holds. Run the result through
[gltf-transform](https://gltf-transform.dev/) or
[gltfpack](https://meshoptimizer.org/gltf/) if you need it smaller.

## Textures are written as PNG

Uncompressed on the GPU and larger on disk than the source DDS. PNG is the
format every glTF loader accepts without an extension; KTX2 / Basis would be
smaller and is not implemented.

## Not read at all

`.knh` driver hierarchies, AI lines, camera definitions, audio sources, track
maps, `ui/` metadata and badges, and `sfx/` banks. See
[Supported files](supported-files.md#what-is-not-read).

## Licensing is your problem

The tool converts; it does not grant rights. Assetto Corsa's content belongs to
Kunos Simulazioni and its mod content to the people who made it. See
[the FAQ](faq.md#can-i-publish-a-converted-car).
