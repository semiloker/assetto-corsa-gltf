---
title: Blender, three.js and Unity
description: Open a converted Assetto Corsa car or track in Blender, three.js, Unity or Godot - scale, axes, materials and what survives each importer.
---

# Opening the result

The output is ordinary glTF 2.0, so anything that reads glTF reads it. What
follows is what to expect in each, and the two or three things worth knowing
before you import.

## Common ground

- **Units are metres.** Assetto Corsa models in metres and so does glTF, so a
  car arrives roughly 4 m long and a track kilometres across, with no scaling
  step.
- **Up is +Y, forward is −Z** - glTF's convention. The half-turn that gets there
  from Assetto Corsa's axes sits on the root node; see
  [Coordinate axes](output.md#coordinate-axes).
- **Empty nodes are the point.** Do not let an importer discard them. They are
  the wheel centres, suspension pickups and hinges.
- Prefer **`--glb`** for a quick look, and the default `.gltf` + `.bin` + PNG
  layout when you intend to work on the textures.

## Blender

`File ▸ Import ▸ glTF 2.0 (.glb/.gltf)`.

- The node hierarchy comes in as objects and **Empties**. A car brings a few
  hundred; that is correct, not a runaway import.
- Blender is Z-up, and its glTF importer applies the conversion for you. Leave
  *Y Up* enabled in the import options unless you know you want otherwise.
- Materials arrive as Principled BSDF. Base colour, roughness, normal, emission
  and alpha mode all map across.
  `KHR_materials_clearcoat` becomes the Principled coat, which is what makes
  car paint read as paint.
- A track is millions of triangles. Import it once, then work from a `.blend`.

To separate the shell from the running gear, filter the outliner by name:
`GEO_`, `SUSP_`, `WHEEL_`, `RIM_`, `DISC_`, `COCKPIT_`, `STEER_`.

## three.js

`GLTFLoader` reads the file directly. A `.glb` needs no extra plumbing; a
`.gltf` needs its `.bin` and PNGs served from the same directory.

```js
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

new GLTFLoader().load('mx5.glb', (gltf) => {
  scene.add(gltf.scene);
  const wheel = gltf.scene.getObjectByName('WHEEL_LF');   // names survive
});
```

Use `sRGBEncoding` / `SRGBColorSpace` on colour textures and a tone-mapped
renderer, or the paint reads flat. `KHR_materials_clearcoat` and
`KHR_materials_specular` are both supported by three.js; a loader that ignores
them still renders the model, just without the lacquer highlight.

[`kn5-studio`](preview.md) is exactly this, set up correctly, if you want a
reference.

## Unity

Unity has no built-in glTF importer. Use
[glTFast](https://github.com/atteneder/glTFast) or
[UnityGLTF](https://github.com/KhronosGroup/UnityGLTF); both read the file and
keep the hierarchy.

Unity is left-handed and Y-up, so the importer mirrors an axis on the way in.
That is the importer's business and it handles winding accordingly - but if you
find the car inside out, that is the place to look, not the converter.

## Godot

Godot 4 imports glTF natively: drop the `.glb` in the project folder. The node
tree arrives as a `Node3D` hierarchy with the Assetto Corsa names intact, which
makes wheel nodes straightforward to find from a script.

## Checking a file before you trust it

Drag it into the [Khronos glTF sample viewer](https://github.khronos.org/glTF-Sample-Viewer-Release/)
or [gltf-viewer](https://gltf-viewer.donmccurdy.com/). Both report what a file
declares and both flag structural problems, which is a faster answer than an
application's importer log.

## Licensing, before you publish anything

Converting a car does not make it yours. Assetto Corsa's stock content is
Kunos Simulazioni's, and mod content belongs to whoever made it. This tool is
for working with content you already have - [see the FAQ](faq.md#can-i-publish-a-converted-car).
