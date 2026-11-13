# DMD mask optimizer

`dmd_optimizer.py` reads VPinMAME DMD dumps and writes a new ColorizingDMD project
(Serum format) in which frames that show the same screen are already merged.
Comparison masks cover the areas that vary, such as scores and small animations.
Shape mode covers frames that differ only in brightness. The tool colours nothing.

The design is in `docs/superpowers/specs/2026-11-12-dmd-mask-optimizer-design.md`.

## Running the tool

The tool needs Python 3.10 or later and numpy 2.0 or later. With `uv`, numpy is
installed automatically:

```
uv run dmd_optimizer.py twst_405.txt
```

Without `uv`, install numpy and run `python3 dmd_optimizer.py twst_405.txt`.

Several dumps of the same ROM can be given at once. The output goes to
`<rom>-optimized/`:

| File | Content |
|---|---|
| `<rom>.cROM` | Open this with "Open project" in ColorizingDMD |
| `<rom>.cRP` | Loaded by the editor together with the `.cROM` |
| `<rom>-report.html` | Shows every merged group; open it in a browser |

## Memory and time

The tool keeps every distinct frame in memory several times over. Allow about 60 KB
per distinct 128x32 frame and about 180 KB per distinct 192x64 frame. The Twister
dump used for testing has 14,443 frames, 10,301 of them distinct: it needs about
0.6 GB and one minute. Several dumps given at once are read one after the other, so
only their distinct frames add up.

## Options

| Option | Default | Meaning |
|---|---|---|
| `--out-dir DIR` | `<rom>-optimized` | Output folder |
| `--rom-name NAME` | first dump's file name | ROM name stored in the project |
| `--max-vary PCT` | 25 | Percent of the display that may vary inside a merged group |
| `--max-masks N` | 64 | Mask slots the tool may use |
| `--min-gain N` | 5 | Frames a mask must save to be used |
| `--min-lit PIXELS` | display pixels / 128 | Lit pixels that must remain outside a mask |
| `--no-shape-mode` | off | Compare exact pixel values only |
| `--force` | off | Overwrite existing output files |

A higher `--max-vary` merges more frames and raises the chance of merging screens
that should stay apart. The report lists the groups closest to the limit first.

## Running the tests

```
uv run --with pytest --with numpy pytest -q
```

Two groups of tests are opt-in because they need downloads:

```
python3 tools/fetch_fixtures.py                              # Twister dump and reference project
uv run --with pytest --with numpy pytest -q -s -m twister

tools/build_libserum.sh                                      # needs git, cmake and a C++ compiler
uv run --with pytest --with numpy pytest -q -s -m libserum
```

## Comparing two projects

```
uv run --with numpy python tools/compare_projects.py A.cROM A.cRP B.cROM B.cRP
```

This prints every header value and field that differs between two projects.
