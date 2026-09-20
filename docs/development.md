---
title: Development
description: Work on the Assetto Corsa glTF converter — repository layout, running the tests, building the documentation site, and how to contribute.
---

# Development

```console
git clone https://github.com/semiloker/assetto-corsa-gltf.git
cd assetto-corsa-gltf
pip install -e .
python -m pytest                # or: python tests/test_convert.py
```

No Assetto Corsa install is needed to work on the tool. The tests write their
own `.kn5`.

## Layout

```
src/acgltf/
  kn5.py          the container reader — node tree, geometry, materials, textures
  convert.py      the converter, the CLI, and the glTF/GLB writer
  studio.py       the local preview server
  survey.py       the suspension-geometry scan
  viewer/         the preview page, with three.js r160 vendored beside it
tests/            four suites, no framework required
docs/             the Markdown these pages are built from
scripts/          build_site.py — Markdown + templates → the website
site/             generated; not committed
```

`kn5.py` knows nothing about glTF and `convert.py` knows nothing about HTTP.
That separation is what lets `studio.py` call the converter as a function
rather than shelling out to it.

## The tests

Four suites. Each runs both as a plain script and under `pytest`, and none
needs a framework, a fixture or a network.

| Suite | Pins |
|---|---|
| `tests/test_convert.py` | the whole pipeline: hierarchy, axes, geometry round-trip, NaN scrubbing, case folding, GLB structure |
| `tests/test_lod.py` | the LOD-twin rule — specifically that `_LR` stays Left Rear |
| `tests/test_paint.py` | where a car's paint comes from: skin override, flat-detail tint, paint-slot ordering |
| `tests/test_studio.py` | the preview server's routes, its JSON error path, and that it refuses directory traversal |

```console
python tests/test_convert.py
python tests/test_lod.py
python tests/test_paint.py
python tests/test_studio.py
```

`test_convert.py` contains `make_kn5`, a minimal encoder for the same container
`kn5.py` decodes. Checking a real car into the repository would mean
redistributing someone else's model, so the suite owns both ends instead.

## Linting

```console
python -m flake8 src tests
```

`.flake8` sets a 100-column limit and ignores `E702`. That is deliberate:
`kn5.py`'s reader is a column of one-line primitives
(`v = struct.unpack_from(…); self.o += 4; return v`), and spread over three
lines each it becomes forty lines of noise around the same idea.

## Building the website

```console
pip install -e ".[docs]"
python scripts/build_site.py
python -m http.server -d site 8000
```

The generator reads `docs/*.md`, applies one template, and writes
`site/`: a landing page, one directory per document, `search-index.json`,
`sitemap.xml` and `robots.txt`. Every page's title, description and canonical
URL come from the Markdown front matter, so adding a page is adding a file.

The search index is built from the same pass that renders the pages, section by
section, so it cannot drift from what is on them. See
[the site generator](#the-site-generator) below.

`--base-url` overrides the canonical host for a preview build. CI runs the
generator and publishes `site/` to GitHub Pages on every push to `main`.

### The site generator

`scripts/build_site.py` is about 400 lines and has one job: turn Markdown into
a static site that a search engine and a reader can both follow.

- Front matter (`title`, `description`) drives `<title>`, the meta description,
  Open Graph, Twitter cards and the canonical link.
- Headings are collected into an on-page table of contents and into the search
  index as individually addressable sections.
- Internal `*.md` links are rewritten to the site's clean URLs, and the
  generator **fails the build** if one points at a document that does not exist.
- `sitemap.xml` and `robots.txt` are written from the same page list.

The search itself is `site/search.js`: a small inverted index built in the
browser from `search-index.json`, no dependency.

## Adding a documentation page

1. Write `docs/<name>.md` with `title` and `description` front matter.
2. Link to it from `docs/index.md` and from wherever it belongs.
3. Run `python scripts/build_site.py`.

It appears in the navigation, the sitemap and the search index without any
other edit.

## Contributing

Issues and pull requests: <https://github.com/semiloker/assetto-corsa-gltf>.

A few things that make a change easy to accept:

- **Say which car or track it was measured on.** Nearly every rule in this
  converter exists because a specific model broke a simpler one, and the
  comments name it. A change that says *"the Lancer's dash was invisible and
  here is why"* is reviewable; *"improve alpha handling"* is not.
- **Leave a test behind** for anything with a branch in it. The suites are
  plain asserts; adding one is adding a function.
- **`python -m flake8 src tests` clean.**
- Commit messages describe the change and carry no trailers.

See also [CONTRIBUTING.md](https://github.com/semiloker/assetto-corsa-gltf/blob/main/CONTRIBUTING.md).

## Releasing

1. Bump `__version__` in `src/acgltf/__init__.py` and `version` in
   `pyproject.toml`.
2. Add a `CHANGELOG.md` entry.
3. Tag `vX.Y.Z` and push the tag.

`asset.generator` in every converted file records the version, so a file can be
traced back to the build that wrote it.
