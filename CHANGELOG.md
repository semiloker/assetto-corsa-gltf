# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-09-20

First release as a standalone project. The converter previously lived in the
`tools/` directory of a game engine; it is now a package of its own with a
command-line interface, a test suite and documentation.

### Added

- **`--glb`** - write one self-contained `.glb` instead of the
  `.gltf` / `.bin` / PNG set. The geometry and every texture end up in a single
  file; the loose files produced along the way are removed once their bytes are
  inside it.
- **Three commands**: `kn5-to-gltf`, `kn5-studio` and `kn5-survey`, installed by
  pip and each also runnable as `python -m acgltf.<module>`. All three take
  `--version`.
- **`asset.generator`** in every converted file now records the tool and version
  that wrote it, so a model can be traced back to a build.
- **An end-to-end test suite.** `tests/test_convert.py` writes its own `.kn5`
  with a minimal encoder, so the whole pipeline is covered without checking a
  licensed model into the repository: node hierarchy, the axis change, geometry
  round-trip, NaN scrubbing, a v6 header, case folding, and GLB structure.
- **A documentation site**, built from `docs/*.md` by `scripts/build_site.py`,
  with full-text search over the rendered pages.

### Fixed

- **Texture names that differ only in case.** Assetto Corsa matches texture
  names case-insensitively, so a car can list `INT_DEcals.dds` and ask a
  material for `INT_Decals.dds` and still render - `ks_mazda_mx5_nd` does.
  Written out literally, the glTF named an image that existed on disk only under
  a different capitalisation: it loaded on Windows by accident and arrived
  untextured on Linux, on macOS and from any case-sensitive web server. Two such
  entries also collided into one file on a case-insensitive disk, silently
  overwriting one another. Entries are now folded to a single canonical spelling
  before anything looks one up, and the run reports how many were folded.
- **`--list-skins` help text** claimed it printed JSON. It has always printed
  tab-separated lines.
- Four source lines had lost their continuations and were sitting at 120-odd
  characters with the operator stranded mid-line.

### Changed

- The package is `acgltf`; the modules are `kn5`, `convert`, `studio` and
  `survey`. Conversion behaviour is unchanged apart from the case fold above.
- `tests/test_studio.py` no longer asserts that it is being run from a directory
  containing a particular file. It writes its own sentinel into a scratch
  working directory, so the directory-traversal check is about the server rather
  than about where the test was started from.

[1.0.0]: https://github.com/semiloker/assetto-corsa-gltf/releases/tag/v1.0.0
