# Examples

Three runnable things. Each is small enough to read in one sitting and is
commented where the obvious version would be wrong.

None of them ships Assetto Corsa content — point them at your own install.

## `batch_convert.py` — a whole car folder to GLB

```console
python examples/batch_convert.py "…/content/cars" out
python examples/batch_convert.py "…/content/cars" out --limit 5 --skin none
python examples/batch_convert.py "…/content/cars" out --gltf     # loose files
```

One `.glb` per car. It is an example rather than a shell loop because of two
things a loop gets wrong:

- **Picking the file.** Every `.kn5` in a car folder is valid and every one of
  them converts, so choosing wrongly fails *silently* — `collider.kn5` gives you
  eight boxes and `*_lod_d.kn5` a silhouette, and both read as a broken
  converter. `top_model()` is the same rule `kn5-studio` uses.
- **Carrying on.** Two cars in a stock install are CSP-encrypted and the
  converter refuses them, as it should. A batch that stops on the first refusal
  converts nothing.

It finishes with a summary: converted, encrypted, no model found, failed.

## `read_hierarchy.py` — find the wheels in a converted car

```console
python examples/read_hierarchy.py out/mx5.glb
python examples/read_hierarchy.py out/mx5.gltf --tree
```

```
mx5.glb
generator : assetto-corsa-gltf 1.0.0
nodes     : 323   meshes: 169   materials: 55
transforms: 154 nodes carry no geometry -- the useful part
extensions: KHR_materials_clearcoat, KHR_materials_specular

role           node               position (x, y, z) in metres
--------------------------------------------------------------------
wheel centre   WHEEL_LF             -0.748    0.298   -1.186
               WHEEL_RF              0.748    0.298   -1.186
               WHEEL_LR             -0.751    0.298    1.123
               WHEEL_RR              0.751    0.298    1.123
suspension     SUSP_LF              -0.751    0.298   -1.186
…
```

This is what keeping the hierarchy buys: the nodes a rig needs are already named
and already positioned, so finding them is a dictionary lookup rather than a
guess at which lump of triangles is a wheel.

Reads both containers with nothing but the standard library — a glTF is JSON,
and a GLB is that JSON in the first chunk of a two-chunk file.

The one subtlety, and the reason the code is longer than it looks like it should
be: the parent chain has to be **multiplied**, not summed. The converter puts
the axis change on the root as a half turn about Y, so a node's own translation
is still in Assetto Corsa's frame (+X left, +Z forward) until that matrix is
applied. Adding translations up skips the rotation and reports every position
mirrored in X and Z — which looks plausible, and is wrong by the width of the
car.

## `viewer.html` — a converted car in three.js

```console
kn5-to-gltf "…/mazda_mx5_lod_a.kn5" out --name mx5 --glb
python -m http.server 8000
```

then open
`http://localhost:8000/examples/viewer.html?model=../out/mx5.glb`.

The smallest page that renders a car *correctly*. Three settings are the usual
reason a converted model looks wrong, and all three are in there with a comment:

- `outputColorSpace = SRGBColorSpace`, or everything renders washed out;
- a tone mapping other than `None`, or the specular highlights clip to white;
- an **environment map** — a PBR material with nothing to reflect is lit by the
  key light alone, and metal and glass come out black. This one is generated
  in-process from `RoomEnvironment`, so the page needs no assets of its own.

It frames whatever it loads, so it works for a 4 m car and a 2 km track, and it
prints which car nodes it found by name.

three.js comes from a CDN here because this is an example;
[`kn5-studio`](https://semiloker.github.io/assetto-corsa-gltf/docs/preview/)
vendors its own copy so it works offline.

## See also

- [Quick start](https://semiloker.github.io/assetto-corsa-gltf/docs/quick-start/)
- [CLI reference](https://semiloker.github.io/assetto-corsa-gltf/docs/cli/)
- [Blender, three.js and Unity](https://semiloker.github.io/assetto-corsa-gltf/docs/workflow/)
