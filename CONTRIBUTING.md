# Contributing

Issues and pull requests are welcome.

## Getting set up

```console
git clone https://github.com/semiloker/assetto-corsa-gltf.git
cd assetto-corsa-gltf
pip install -e ".[docs]"
```

You do **not** need Assetto Corsa installed to work on this. The test suite
writes its own `.kn5`.

## Before you open a pull request

```console
python tests/test_convert.py
python tests/test_lod.py
python tests/test_paint.py
python tests/test_studio.py
python -m flake8 src tests

python scripts/build_site.py     # only if you touched docs/ or scripts/
python tests/test_site.py
node tests/test_search.js
```

CI runs all of it on Python 3.9 through 3.13.

## Reporting a conversion bug

The useful report names the model. Almost every rule in this converter exists
because one specific car or track broke a simpler rule, and the comments say
which. So please include:

- the exact command you ran and everything it printed;
- the car or track - its folder name, whether it is stock or a mod, and where it
  came from;
- what you expected and what you got, ideally with a screenshot.

Do **not** attach the `.kn5`. It is not yours to redistribute and it is not
needed: the folder name and the output are enough to reproduce it against a
local copy, and where they are not, a node list from `--materials` usually is.

## Changes that are easy to accept

**Say which model it was measured on.** A change that says *"the Lancer's dash
came out invisible because its `dashao` decodes to a fully transparent image,
and AC's shader never samples alpha on an opaque material"* is reviewable.
*"Improve alpha handling"* is not, because there is no way to tell whether it
fixes one car and breaks forty.

**Leave a test behind** for anything with a branch in it. The suites are plain
`assert`s in plain functions - adding one is adding a function, and there is no
framework to learn. If the behaviour needs a car to demonstrate, build one with
`make_kn5` in `tests/test_convert.py` rather than checking a real one in.

**Keep the comments.** This codebase explains *why*, at length, in the places
where the obvious implementation is wrong. If you change one of those decisions,
change the comment with it; if a comment turns out to be wrong, that is worth a
pull request on its own.

**One thing per commit**, with a message that says what changed and why. No
trailers, no attribution lines, no `Co-authored-by` unless a person genuinely
co-authored it.

## Style

- `python -m flake8 src tests` clean. 100 columns.
- `E702` is ignored on purpose: `kn5.py`'s reader is a column of one-line
  primitives, and spread over three lines each it becomes forty lines of noise.
- Standard library first. The converter has exactly one dependency (Pillow) and
  adding a second needs a reason bigger than convenience.

## Documentation

`docs/*.md` builds the website. Add a page by writing the file with `title` and
`description` front matter, then listing it in `NAV` in
`scripts/build_site.py` - the build fails if you do one without the other, and
fails again if any internal link or anchor does not resolve.

## Scope

This is a one-way geometry and material converter. Things that are deliberately
out of scope: writing `.kn5`, decrypting CSP-protected models, and reading
`data.acd`. See [Limitations](https://semiloker.github.io/assetto-corsa-gltf/docs/limitations/).

## Licence

By contributing you agree that your work is published under the
[MIT licence](LICENSE).
