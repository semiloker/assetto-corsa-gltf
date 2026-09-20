---
title: Converting cars
description: Convert an Assetto Corsa car .kn5 to glTF or GLB - picking the right model file, liveries and paint, LOD twins, damage and blur variants.
---

# Converting cars

```console
kn5-to-gltf <car.kn5> <outdir> [--name NAME] [--skin NAME] [--glb]
```

## Which .kn5 is the car?

A car folder holds several `.kn5` and **every one of them is valid and every
one of them converts**, so picking the wrong file fails silently: the result is
a car with no interior, or a car that is eight boxes, and it reads as a broken
converter rather than as the wrong input.

Three shapes, in this order:

1. **`<car_id>.kn5`** - the older Kunos layout, and most mods.
2. **`*_lod_a.kn5`** - the current one, and the trap. Assetto Corsa's *top*
   LOD is `lod_A`, so a rule that skips everything with `_lod_` in the name
   skips the actual car. On `ks_mazda_mx5_nd` there is no file named after the
   folder at all; it is `mazda_mx5_lod_a.kn5`.
3. **`collider.kn5`** - never this. It is the physics collision hull: eight
   boxes.

`ks_mazda_mx5_nd` in full:

```
mazda_mx5_lod_a.kn5    ← the car
mazda_mx5_lod_b.kn5    ← reduced
mazda_mx5_lod_c.kn5    ← reduced further
mazda_mx5_lod_d.kn5    ← a silhouette
collider.kn5           ← eight boxes
skins/                 ← the liveries
```

[`kn5-studio`](preview.md) picks the right one for you when you hand it a
folder.

## Liveries and paint

A livery in Assetto Corsa lives **outside** the model. The `.kn5` carries
whichever skin happened to be loaded when it was exported - on
`ks_mazda_mx5_nd` that is the untouched grey template, averaging (174, 174, 174)
- and at load time the game replaces it, by filename, with the contents of
`skins/<chosen>/`.

So a converter that reads only the container gets the template every time, and
the car arrives in primer no matter what colour the folder next door holds.
That is what `--skin` is for:

```console
kn5-to-gltf mazda_mx5_lod_a.kn5 out --skin 02_artic_white
kn5-to-gltf mazda_mx5_lod_a.kn5 out --skin none     # keep the kn5's own textures
```

Without the flag the **first** skin folder is used, which is what the game
picks when nothing says otherwise.

### Where the colour actually comes from

On a Kunos road car the body colour is not in the diffuse at all. The diffuse
is a shared grey panel-and-ambient-occlusion sheet used by every livery; the
colour is the flat `txDetail` texture the shader multiplies over it, and the
converter turns that into a glTF `baseColorFactor`.

Two consequences:

- Changing livery **changes the glTF**, not just a texture. There is nothing a
  viewer could swap at runtime, which is why [`kn5-studio`](preview.md)
  re-converts when you click a colour.
- A material only has a paint slot if Assetto Corsa's own `useDetail` switch is
  on. Without it the shader never samples `txDetail`, so whatever is in that
  slot is not on screen and is not offered as a colour of anything.

### Listing liveries

```console
$ kn5-to-gltf mazda_mx5_lod_a.kn5 --list-skins
# car	mazda_mx5_lod_a
skin	00_soul_red_metallic	EXT_Carpaint	7E0100	23554	skin
skin	00_soul_red_metallic	INT_OCC_Carpaint	7E0100	5398	skin
skin	00_soul_red_metallic	EXT_Rim	898889	33024	kn5
skin	01_jet_black_mica	EXT_Carpaint	0F0E0E	23554	skin
…
```

Materials are ordered **bodywork first**, and that order is a contract: the
first line of a livery is the car's colour.

It is not simply the biggest painted material, and that matters. On the MX-5
the rims carry 33 024 triangles against the bodywork's 23 554, so sorting by
size alone picks the *wheels* - whose grey comes out of the `.kn5` rather than
the skin and is therefore identical for all seven liveries. Every colour in the
picker would look the same. The name is consulted first, then size inside a
band.

## LOD twins and runtime variants

Three kinds of mesh are dropped by default, subtree and all, because Assetto
Corsa swaps them at runtime and a static glTF cannot:

| Pattern | What it is | Why it is dropped |
|---|---|---|
| `*_BLUR` | spinning-wheel stand-ins | opaque discs over the spokes |
| `*_DAMAGE` | crumpled panel shells | sit a fraction of a millimetre off the clean panels and z-fight |
| `*_LR` **with** an `*_HR` twin | in-file LOD pairs | two dashboards and two steering wheels in the same place |

The third needs the twin test, and it is the whole trick. `_LR` is **Left Rear**
far more often than it is low-res - `WHEEL_LR`, `SUSP_LR`, `RIM_LR`, `DISC_LR`,
`SPRING_LR`, `ROLL_BAR_LR` - so a rule matching the suffix alone would take a
corner of the suspension off every car in the game. None of those has an `_HR`
partner; every genuine LOD name does.

Separate `lod_a/b/c` files are not the whole story: Assetto Corsa also ships two
versions of the cockpit and the steering wheel *inside* the top LOD
(`COCKPIT_HR`/`COCKPIT_LR`, `STEER_HR`/`STEER_LR`) and swaps them by camera.
192 of 215 readable stock cars do it.

Pass [`--keep-variants`](cli.md#keep-variants) to keep all three.

## What you get

For the MX-5, with the default settings:

```
nodes  : 323  (153 transforms, 169 meshes, 0 empty, 12 variants dropped)
tris   : 168283
images : 61   materials: 55
```

153 of those nodes carry no geometry at all. They are the useful part: wheel
centres, suspension pickups, the steering column, door hinges, driver position
- named and positioned by the people who built the car. See
[The glTF output](output.md#the-node-hierarchy).

## Next

- [The glTF output](output.md) - materials, axes, textures
- [Blender, three.js and Unity](workflow.md)
- [Troubleshooting](troubleshooting.md) - white, black, or inside out
