# DMD mask optimizer: design

- Date: 2026-11-12
- Status: design approved section by section in brainstorming; this document is the written record
- Deliverable: one Python file, `dmd_optimizer.py`

## 1. Purpose

`dmd_optimizer.py` reads VPinMAME dot-matrix display (DMD) dumps and writes a new
ColorizingDMD project in the Serum format. In that project, frames that show the same
screen are already merged:

- comparison masks cover the areas that vary (scores, timers, credits, small animations);
- shape mode covers frames that differ only in brightness.

The colourist opens the project in ColorizingDMD and has fewer frames to colour. The
tool does not colour anything.

## 2. Background

### 2.1 How Serum identifies a frame

This describes `Identify_Frame` in libserum (the copy bundled with ColorizingDMD
v3.17.3 and libserum 2.8.2 behave the same way).

Each project frame stores:

- its original pixels (one byte per pixel, values 0–3 or 0–15);
- a comparison mask number (0–63, or 255 for no mask);
- a shape-mode flag;
- a CRC32 hash.

The hash is CRC-32 as computed by `zlib.crc32` (polynomial 0xEDB88320, initial value
0xFFFFFFFF, final complement). It runs over the pixel bytes in row-major order and
skips every pixel whose mask byte is non-zero. With shape mode on, every pixel value
above 1 is replaced by 1 before hashing, so only lit versus unlit counts.

For an incoming frame, libserum walks the project frames starting from the frame it
identified last. For each (mask, shape flag) pair it meets, it hashes the incoming
frame once with that pair and returns the first project frame of that pair with the
same hash.

Consequences that shape this design:

1. Masks live in one pool shared by all frames. The editor allows 64 masks
   (`MAX_MASKS`). A frame uses one mask or none.
2. A dump frame that matches several project frames is identified unpredictably,
   because the answer depends on which frame was identified before it.
3. Two project frames with the same mask, shape flag and hash cannot be told apart.

### 2.2 Files involved

| File | Role |
|---|---|
| `<rom>.txt` | VPinMAME dump: timestamped frames as text |
| `<rom>.cROM` | Project data used at runtime: hashes, masks, shape flags, colourised frames, sprites, backgrounds |
| `<rom>.cRP` | Editor-only project data: original frames, frame durations, names, palettes |

ColorizingDMD opens a project by reading the `.cROM` and then the `.cRP` with the same
base name in the same folder.

### 2.3 Reference data: Twister (`twst_405`)

The user supplied a dump and a hand-made project for the same ROM.

| Item | Value |
|---|---|
| Dump `twst_405.txt` | 60,285,082 bytes, CRLF line endings, 14,443 frames over about 28 minutes |
| Dump frame format | 128x32, 4 shades |
| Distinct frames in the dump | 10,301 |
| Distinct lit/unlit shapes in the dump | 6,906 |
| Reference project frames | 5,093 (5,064 distinct) |
| Reference project masks | 64 defined, 52 in use; 1,058 frames use shape mode |
| Reference project extras | 31 sprites, 2 backgrounds, 194 extra-resolution frames |
| Reference file sizes | `.crom` 431,971,016 bytes, `.cRP` 21,004,003 bytes, header length field 80 |

The reference project was built mostly from other captures: only 644 of its distinct
frames occur in this dump. It still identifies 10,275 of the 10,301 distinct dump
frames, using 1,234 of its own frames. 142 dump frames match more than one reference
frame. Its masks ignore between 38% and 99% of the display, most of them 85–99%.

The reference project is used in two ways: as a file the editor itself saved (format
check) and as a record of how a colourist grouped these frames (benchmark, section
12.2).

## 3. Decisions taken with the user

| Topic | Decision |
|---|---|
| Output | A new project pair, `.cROM` + `.cRP`, for ColorizingDMD v3.17.3 |
| Masking style | Mask what varies; everything else identifies the frame |
| Shape mode | Used for groups where it merges frames; `--no-shape-mode` turns it off |
| Colouring data | Identification only. No dynamic masks are written |
| Dependency | numpy only |
| Method | Candidate regions found in the dump, scored on the whole dump, chosen greedily into the 64-mask pool |
| Limit | One limit on the area that may vary inside a merged group, default 25% of the display |
| Review | An HTML report shows what was merged |

## 4. Scope

In scope:

- Reading one or more dumps of the same ROM at 128x32 or 192x64, in 4 or 16 shades.
- Finding masks and shape-mode groups under the rules in section 7.
- Writing `.cROM`, `.cRP` and an HTML report.
- Reading existing `.cROM` and `.cRP` files, as far as the tests in section 12 need it.

Out of scope for this version:

- Dynamic masks, sprites, backgrounds, colour rotations, triggers and sections.
- Updating or merging into an existing project.
- 128x16 and 256x64 dumps (rejected with an error).
- Writing `.cRZ` or `.cROMc` player files. The editor writes the `.cRZ` when it saves.
- ColorizingDMD versions whose file layout differs from v3.17.3.

## 5. Command line

```
uv run dmd_optimizer.py DUMP [DUMP ...] [options]
```

The file starts with inline script metadata so `uv run` installs numpy:

```python
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=2.0"]
# ///
```

| Option | Default | Meaning |
|---|---|---|
| `--out-dir DIR` | `<rom>-optimized` in the current folder | Where the three output files go |
| `--rom-name NAME` | First dump's file name without extension | Name stored in the project and used for file names: 1 to 63 ASCII characters, without path or wildcard characters |
| `--max-vary PCT` | 25 | Percent of the display that may vary inside a merged group |
| `--max-masks N` | 64 | Mask slots the tool may use (0–64) |
| `--min-gain N` | 5 | Frames a candidate must save to be applied |
| `--min-lit PIXELS` | display pixels / 128 (32 at 128x32, 96 at 192x64) | Lit pixels that must remain outside a mask |
| `--no-shape-mode` | off | Compare exact pixel values only |
| `--force` | off | Overwrite existing output files |

`--max-masks 0 --no-shape-mode` merges nothing beyond exact duplicates. That mode is
used for the fresh-import comparison in section 12.4.

While it works, the tool prints progress lines and warnings to standard error. On
success it prints the summary numbers of the report and the paths written to standard
output and exits with status 0. On any error in section 11 it prints one error
message as the last line on standard error, prints nothing to standard output, and
exits with status 1.

The ROM name is limited to ASCII because the project stores it in a single-byte
field whose meaning for other characters depends on the Windows code page. It is
also a file name, so it may not contain any of `/ \ : * ? " < > |` and may not be
`.` or `..`.

## 6. Reading dumps

The reader follows ColorizingDMD's `Parse_TXT` for the supported sizes.

- A frame record starts with a timestamp line: `0x` followed by 8 hexadecimal digits,
  in milliseconds.
- H lines of W characters follow. `0`–`9` map to 0–9; `a`–`f` and `A`–`F` map to 10–15.
- Records are separated by blank lines. Line endings may be CRLF or LF.
- W and H come from the first record of the first file. They must be 128x32 or
  192x64. Every record in every file must have the same size.
- The project has 16 shades if any pixel value in any file exceeds 3, otherwise 4.
- Blank lines are ignored everywhere, including between the rows of a record. The
  editor ignores them too.
- If a record has a short row, a missing row or any other character, reading of that
  file stops there with a warning and the earlier records are kept.
- If other text follows the H rows of a complete record before the next timestamp
  line, that record is kept and reading of the file stops after it, with a warning.
- This is stricter than the editor in one respect. The editor also stops at a short
  row, a missing row and a non-alphanumeric character, but it accepts the letters
  `g`–`z` and turns them into pixel values above 15. No valid dump contains those
  letters, so this tool treats them as invalid.

Frame durations use the editor's rule. The duration of record `i` is
`t[i+1] - t[i]`. It is 30 ms instead when the record is the last one in its file,
when `t[i+1] < t[i]`, or when the difference exceeds 4000 ms.

Distinct frames are found by exact pixel equality and numbered by first appearance,
taking the files in the order given on the command line.

## 7. Analysis

### 7.1 Terms

- **P**: the number of pixels, W x H.
- **Value view** of a frame: its pixel values.
- **Shape view** of a frame: 1 where the pixel value is above 0, otherwise 0.
- **Setting**: a mask (or no mask) together with a view. The value view is tighter
  than the shape view, and a mask contained in another mask is tighter than it. These
  two comparisons are used in step B. They do not rank every pair of settings; where
  one ranking is needed (rule R5), it is the order listed in step D.
- **Match**: two frames match under a setting when their views are equal at every
  pixel outside the mask.
- **Class** of a frame under a setting: all distinct dump frames that match it.
- **Group**: a set of distinct frames merged into one kept frame, with one setting.
- **Kept frame**: the earliest member of a group. It is the only member written to
  the project.
- **Mask area**: the number of masked pixels.
- **Varying area** of a group: its mask area plus the number of unmasked pixels at
  which its members differ in value.
- **Limit**: `floor(max_vary / 100 * P)` pixels.

### 7.2 Rules every result must satisfy

- **R1, unique identification.** For every group, the class of its kept frame under
  the group's setting is exactly the group's members. It follows that every distinct
  dump frame matches exactly one kept frame.
- **R2, varying area.** The varying area of every group is at most the limit.
- **R3, lit pixels.** For every group that uses a mask, the kept frame has at least
  `min_lit` lit pixels outside the mask.
- **R4, pool size.** At most `max_masks` masks are used, and never more than 64.
- **R5, tightest setting.** Each group has the first setting, in the order given in
  step D below, that produces the same group and passes R2 and R3. In particular the
  shape view is used only when members differ in value outside the mask.
- **R6, order.** Kept frames appear in the project in order of first appearance in
  the dump.
- **R7, determinism.** The same inputs and options produce byte-identical output
  files.

### 7.3 Procedure

The procedure below is the one prototyped on the Twister dump. An implementation may
organise the computation differently as long as it produces the same decisions and
the rules above hold.

**Padding a set of pixels into a region, `pad(V)`**

1. Grow V by one pixel up, down, left and right.
2. Snap to 2x2-pixel cells: a cell is selected when any of its pixels is selected.
3. Split the selected cells into blocks. Take the bounding box of the selection and
   cut it wherever two or more consecutive cell columns are empty. If there is no such
   cut, cut wherever two or more consecutive cell rows are empty. Repeat inside each
   piece until no cut applies.
4. Replace each block by its bounding rectangle.

The result is a mask aligned to the 2-pixel grid.

**Step A: candidate regions.** Done once per enabled view. The value view is always
enabled. The shape view is enabled unless `--no-shape-mode` is given.

1. Build links: every unordered pair of distinct frames that appear one directly
   after the other in a dump file. The difference of a link is the number of pixels
   at which the two frames differ in the view. Drop links whose difference exceeds
   the limit. Sort links by difference, then by the two frame numbers.
2. Process the links in that order with a union-find structure. Each set remembers
   V, the pixels at which its members differ in the view, and its earliest frame.
3. For a link between two different sets, let `Vn` be the union of both sets' V and
   the pixels at which the two earliest frames differ.
   - If `Vn` is empty, join the sets.
   - If `Vn` or `pad(Vn)` has more pixels than the limit, leave the sets apart.
   - Otherwise join the sets and record `pad(Vn)` as a candidate region.

   Whenever two sets are joined, the joined set's V is `Vn` and its earliest frame is
   the lower-numbered of the two earliest frames. A link whose two frames are already
   in the same set is skipped.

The candidate regions from both views are pooled and duplicates are removed, keeping
discovery order.

**Step B: scoring a candidate.** A candidate is a setting: a candidate region with an
enabled view, or no mask with the shape view. Under a candidate, a class is
*mergeable* when all of these hold:

1. It contains frames from at least two current groups.
2. Every current group with a frame in the class has a setting whose mask is
   contained in the candidate's mask (no mask is contained in every mask) and whose
   view is not looser than the candidate's view. Such groups lie entirely inside the
   class.
3. Treated as one group with the candidate's setting, the class passes R2 and R3.

The gain of a candidate is the sum, over its mergeable classes, of the number of
current groups in the class minus one.

**Step C: choosing masks.**

1. Start with every distinct frame as its own group with no mask and the value view.
2. If the shape view is enabled, apply the candidate "no mask, shape view": merge the
   groups of each mergeable class. This uses no mask slot and ignores `min_gain`.
3. Repeat:
   - Score every remaining candidate as
     `gain * (1 - 0.5 * mask_area / limit)`.
   - Take the highest score. Ties go to the smaller mask area, then to the earlier
     discovered region, then to the value view.
   - Stop when no candidate has a gain of at least `min_gain`.
   - A candidate whose region is not yet in the pool cannot be applied once the pool
     holds `max_masks` regions; skip it.
   - Apply the chosen candidate: merge the groups of each mergeable class into one
     group with the candidate's setting, and add its region to the pool if it is not
     there yet.

Gains may be cached between rounds to save time, but nothing cached may be applied.
Immediately before a candidate is applied, its mergeable classes (all three
conditions of step B) and its gain must be derived afresh from the current groups. If
the fresh gain no longer wins the round, the candidate goes back into the comparison
with its fresh score.

When the limit is 0 pixels there are no candidate regions and nothing is merged.

**Step D: tightest setting per group.** For each group with more than one member, in
kept-frame order, try settings in this order:

1. no mask with the value view;
2. no mask with the shape view, if enabled;
3. each pool mask in order of increasing area (ties in pool order), with the value
   view and then, if enabled, the shape view.

The first setting under which the class of the kept frame equals the group's members,
and under which the group passes R2 and R3, becomes the group's setting. The setting
the group already has always qualifies, so the search ends there at the latest.

**Step E: numbering and verification.**

1. Drop pool masks that no group uses.
2. Number the masks from 0 by frames saved, most first. Frames saved by a mask is the
   number of frames in the groups that use it minus the number of those groups. Ties
   go to the smaller area, then to pool order.
3. Compute the CRC32 hash of every kept frame under its setting (section 2.1).
4. Verify R1 independently of the bookkeeping above, the way libserum identifies
   frames: for every distinct dump frame and every (mask, shape flag) pair in use,
   compute the frame's hash under that pair and look up the kept frames with that
   pair and hash. For each one found, compare the pixels outside the mask in the
   pair's view.
   - A pixel-exact match counts as a match. Every dump frame must have exactly one,
     and it must be the kept frame of its group. Otherwise the tool stops with an
     error (section 11).
   - A hash match that is not a pixel-exact match is a CRC32 collision. It is
     reported as a warning (section 9), because libserum would confuse the two.

### 7.4 Results expected on the Twister dump

The prototype used shape-view candidates only. The implementation adds value-view
candidates and step D, so its numbers will differ somewhat.

| Run | Kept frames | Masks | Grouped differently by hand |
|---|---|---|---|
| Defaults (limit 25%) | 4,275 | 47 | 2.4% |
| Limit 40% | 3,505 | 38 | 5.5% |
| Limit 15% | 5,419 | 53 | 2.0% |
| `--no-shape-mode`, limit 25% | 4,995 | 41 | 2.9% |

"Grouped differently by hand" is defined in section 12.2. The prototype ran in about
one minute on the Twister dump.

Evidence for counting brightness-only changes in the limit: among groups merged by
shape mode alone, those whose brightness changed over less than 25% of the display
held 3,788 frames, of which the hand-made project kept 9 apart (0.2%). Those above
25% held 407 frames, of which it kept 108 apart (26.5%).

## 8. Output project files

### 8.1 Conventions

- All values are little-endian. There is no padding or alignment between fields.
- Arrays are written in row-major order, frame after frame.
- `BOOL` is a 4-byte integer. `wchar_t` is 2 bytes.
- nF is the number of kept frames, nM the number of masks, nS the number of sprites,
  nB the number of backgrounds. P is W x H. PX is the pixel count of the
  extra-resolution frame.
- Files are named `<rom>.cROM` and `<rom>.cRP`.

### 8.2 Layout of the `.cROM` file

This is the order in which ColorizingDMD v3.17.3 writes the file (`Save_cRom`). The
last column is what this tool writes for a new project; "empty" means the count is
zero because nS or nB is zero.

| # | Field | Type | Count | Written by the tool |
|---|---|---|---|---|
| 1 | name | char | 64 | ROM name, zero padded |
| 2 | header length | uint32 | 1 | 80 |
| 3 | fWidth | uint32 | 1 | W |
| 4 | fHeight | uint32 | 1 | H |
| 5 | fWidthX | uint32 | 1 | 2W when H is 32, W/2 when H is 64 |
| 6 | fHeightX | uint32 | 1 | 64 when H is 32, 32 when H is 64 |
| 7 | nFrames | uint32 | 1 | nF |
| 8 | noColors | uint32 | 1 | 4 or 16 |
| 9 | nCompMasks | uint32 | 1 | nM |
| 10 | nSprites | uint32 | 1 | 0 |
| 11 | nBackgrounds | uint16 | 1 | 0 |
| 12 | is256x64 | BOOL | 1 | 0 |
| 13 | HashCode | uint32 | nF | CRC32 per section 2.1 |
| 14 | ShapeCompMode | uint8 | nF | 1 for the shape view, else 0 |
| 15 | CompMaskID | uint8 | nF | mask number, or 255 for no mask |
| 16 | CompMasks | uint8 | nM x P | 1 where the pixel is ignored, else 0 |
| 17 | isExtraFrame | uint8 | nF | 0 |
| 18 | cFrames | uint16 | nF x P | default colour of each original pixel value (section 8.4) |
| 19 | cFramesX | uint16 | nF x PX | 0 |
| 20 | DynaMasks | uint8 | nF x P | 255 |
| 21 | DynaMasksX | uint8 | nF x PX | 255 |
| 22 | Dyna4Cols | uint16 | nF x 32 x noColors | 0 |
| 23 | Dyna4ColsX | uint16 | nF x 32 x noColors | 0 |
| 24 | isExtraSprite | uint8 | nS | empty |
| 25 | FrameSprites | uint8 | nF x 32 | 255 |
| 26 | SpriteOriginal | uint8 | nS x 256 x 64 | empty |
| 27 | SpriteColored | uint16 | nS x 256 x 64 | empty |
| 28 | SpriteMaskX | uint8 | nS x 256 x 64 | empty |
| 29 | SpriteColoredX | uint16 | nS x 256 x 64 | empty |
| 30 | active frames | uint8 | nF | 1 when the frame duration is at least 15 ms, else 0 |
| 31 | ColorRotations | uint16 | nF x 4 x 64 | 0 |
| 32 | ColorRotationsX | uint16 | nF x 4 x 64 | 0 |
| 33 | SpriteDetDwords | uint32 | nS x 4 | empty |
| 34 | SpriteDetDwordPos | uint16 | nS x 4 | empty |
| 35 | SpriteDetAreas | uint16 | nS x 4 x 4 | empty |
| 36 | TriggerID | uint32 | nF | 0xFFFFFFFF |
| 37 | FrameSpriteBB | uint16 | nF x 32 x 4 | (0, 0, W-1, H-1) for each of the 32 slots |
| 38 | isExtraBackground | uint8 | nB | empty |
| 39 | BackgroundFrames | uint16 | nB x P | empty |
| 40 | BackgroundFramesX | uint16 | nB x PX | empty |
| 41 | BackgroundID | uint16 | nF | 0xFFFF |
| 42 | BackgroundMask | uint8 | nF x P | 1 |
| 43 | BackgroundMaskX | uint8 | nF x PX | 1 |
| 44 | DynaShadowsDirO | uint8 | nF x 32 | 0 |
| 45 | DynaShadowsColO | uint16 | nF x 32 | 0 |
| 46 | DynaShadowsDirX | uint8 | nF x 32 | 0 |
| 47 | DynaShadowsColX | uint16 | nF x 32 | 0 |
| 48 | DynaSprite4Cols | uint16 | nS x 9 x noColors | empty |
| 49 | DynaSprite4ColsX | uint16 | nS x 9 x noColors | empty |
| 50 | DynaSpriteMasks | uint8 | nS x 256 x 64 | empty |
| 51 | DynaSpriteMasksX | uint8 | nS x 256 x 64 | empty |
| 52 | SpriteShapeMode | uint8 | nS | empty |

Notes:

- The header length field is a format version marker written as `20 * 4`. It is not
  the byte length of the header, which is 106 bytes (fields 1–12).
- The editor writes field 30 as 1 when the duration is at least 15 ms or the frame
  has been colourised. A new project has no colourised frames.
- This layout reproduces the size of the reference `.crom` exactly (431,971,016
  bytes) with the counts stored in its header: nF 5,093, nM 64, nS 31, nB 2. The hash
  rule reproduces all 5,093 stored hashes.
- At 128x32 with 4 shades the file takes 83,950 bytes per frame plus 4,096 bytes per
  mask: about 360 MB for 4,300 frames.

### 8.3 Layout of the `.cRP` file

This is the order in which ColorizingDMD v3.17.3 writes the file (`Save_cRP`).

| # | Field | Type | Count | Written by the tool |
|---|---|---|---|---|
| 1 | name | char | 64 | ROM name, zero padded |
| 2 | oFrames | uint8 | nF x P | original pixels of the kept frames |
| 3 | activeColSet | BOOL | 64 | 0 |
| 4 | ColSets | uint16 | 64 x 16 | 0 |
| 5 | acColSet | uint8 | 1 | 0 |
| 6 | preColSet | uint8 | 1 | 0 |
| 7 | nameColSet | char | 64 x 64 | 0 |
| 8 | DrawColMode | uint32 | 1 | 0 |
| 9 | Draw_Mode | uint8 | 1 | 0 |
| 10 | Mask_Sel_Mode | int32 | 1 | 0 |
| 11 | Fill_Mode | BOOL | 1 | 0 |
| 12 | Mask_Names | char | 64 x 32 | names of the masks used (section 8.4), rest 0 |
| 13 | nSections | uint32 | 1 | 0 |
| 14 | Section_Firsts | uint32 | 512 | 0 |
| 15 | Section_Names | char | 512 x 32 | 0 |
| 16 | Sprite_Names | char | 255 x 32 | 0 |
| 17 | Sprite_Col_From_Frame | uint32 | 255 | 0 |
| 18 | FrameDuration | uint32 | nF | milliseconds (section 8.4) |
| 19 | SpriteRect | uint16 | 255 x 4 | 0 |
| 20 | SpriteRectMirror | BOOL | 255 x 2 | 0 |
| 21 | Palette | uint16 | 256 x 64 | first noColors entries hold the default colours, rest 0 |
| 22 | acEditColorsS | uint16 | 16 | first noColors entries hold the default colours, rest 0 |
| 23 | nImagePosSaves | uint32 | 1 | 0 |
| 24 | ImagePosSaveName | char | 256 x 64 | 0 |
| 25 | ImagePosSave | int32 | 256 x 16 | 0 |
| 26 | PalNames | char | 256 x 64 | 0 |
| 27 | isImported | uint32 | 1 | 0 |
| 28 | importedPal | uint8 | isImported x 64 x 3 | absent |
| 29 | TimeElapsed | uint32 | 1 | 0 |
| 30 | isPupPack | BOOL | 1 | 0 |
| 31 | PupPack | wchar_t | 256 | 0 |

This layout reproduces the size of the reference `.cRP` exactly (21,004,003 bytes).

### 8.4 Values that need a rule

- **Default colours.** The editor colours a freshly imported frame with an orange
  ramp in RGB565: `colour[v] = (r << 11) | (r << 5)` with
  `r = floor(31 * v / (noColors - 1))`. For 4 shades this gives 0x0000, 0x5140,
  0xA280 and 0xFBE0, which are the first four palette entries of the reference
  `.cRP`.
- **Frame duration.** A kept frame's duration is the longest duration of any dump
  record whose frame belongs to its group. The editor would keep the duration of the
  first occurrence; the longest is used so that a merged screen is not marked
  inactive because one variant flashed by.
- **Mask names.** Mask `NN` is named `auto-NN AA% F frames`, where AA is the mask
  area as a whole percent of the display and F is the number of frames it saves, for
  example `auto-03 18% 212 frames`. Names are at most 30 bytes, the longest the
  editor accepts.
- **Mask count.** The editor sets nCompMasks to the highest mask number assigned to
  a frame plus one, and stores that many masks. This tool numbers its masks from 0
  without gaps and drops unused ones (step E), so in its output nCompMasks equals the
  number of masks in use. The reference project shows the difference: 52 masks are
  assigned to frames, the highest is number 63, and its nCompMasks is 64.

Every other field of a new project is written as ColorizingDMD's import code
(`CopyTXTFrames2Frame`) initialises it; those are the values in the tables above.

## 9. Review report

`<rom>-report.html` is one self-contained file. Images are embedded as PNG data at
native resolution and enlarged by the browser without smoothing. Frame numbers in the
report are the 0-based positions of kept frames in the project.

Content, in order:

1. **Summary.** Dump files read, frames read, distinct frames, frames kept, frames
   kept unmerged, masks used, frames merged by shape mode alone, and the analysis
   options of the run (`--max-vary`, `--max-masks`, `--min-gain`, `--min-lit` and
   whether shape mode is on). The ROM name is in the title.
2. **Warnings.**
   - Warnings from reading the dumps.
   - CRC32 collisions found in step E.
   - Kept frames whose duration is under 15 ms, which the editor marks inactive until
     they are coloured.
3. **Review-first list.** The 20 groups with the largest varying area, as a share of
   the limit.
4. **One section per mask, ordered by mask number.** A picture of the mask, its
   name, the share of the display it covers, and the number of groups and frames it
   merges. Then every group that uses the mask, largest first, with:
   - the kept frame and its project frame number;
   - the mask outline and the pixels at which the members actually differ,
     highlighted on the kept frame (the area to cover with dynamic colouring);
   - up to three other members with the timestamp of their first occurrence;
   - the number of members and whether shape mode is on.
5. **One section for groups merged by shape mode with no mask**, in the same layout.

Frames that stay unmerged are counted in the summary and not listed. Mask sections
are collapsible so that a report with thousands of groups stays usable.

## 10. Program structure

The deliverable is one file with five parts. Each part has one job and can be tested
without the others.

| Part | Job | Depends on |
|---|---|---|
| Dump reader | Text files in; frames, timestamps, durations, shade count out | nothing |
| Analysis | Frames and options in; groups, settings, mask pool, hashes, warnings out | dump reader's output |
| Project model | Field layout tables for `.cROM` and `.cRP`; read a project; write a project; build a new project from an analysis | analysis output |
| Report | Analysis in; HTML out | analysis output |
| Command line | Arguments, file safety, calling the parts in order, terminal summary | all parts |

The reader and the writer of project files use the same layout tables, so a layout
is stated once.

Repository layout:

```
dmd_optimizer.py          the deliverable
tests/                    pytest tests (section 12)
tools/                    fixture download and libserum build scripts
fixtures/                 downloaded Twister files, not committed
docs/superpowers/specs/   this document
```

## 11. Errors

The tool stops with one error message, exit status 1, and no output files when:

- a dump file cannot be read or contains no complete frame;
- the frame size is not 128x32 or 192x64, or the dumps differ in size;
- an option value is out of range, or the ROM name is not usable (section 5);
- the output files cannot be written;
- an output file exists and `--force` was not given;
- the verification in step E fails. This means a defect in the tool, and the message
  says so.

A dump whose last record is incomplete is read up to that record, with a warning.

Output files are written under temporary names in the output folder and renamed
after all three are complete. A failed run removes its temporary files. If a rename
fails, every file that was already replaced is put back, so an existing project is
either replaced completely or left exactly as it was. If the run created the output
folder and nothing was written, the folder is removed.

## 12. Testing

### 12.1 Tests on made-up dumps

These are fast and run on every change.

- **Dump reading:** both sizes, both shade counts, CRLF and LF, a truncated last
  record, an unsupported size, mixed sizes, the duration rule.
- **Hashing:** CRC32 with and without a mask and shape mode against known values.
- **Padding:** `pad(V)` on hand-built pixel sets.
- **Analysis on small dumps with a known answer:**
  - one screen with a counting score: one kept frame, one mask over the score, value
    view;
  - one screen with a title that flickers in brightness: one kept frame, no mask,
    shape view;
  - a looping animation in a small corner over a fixed screen: one kept frame with a
    mask over the corner;
  - two screens that differ over more than the limit: both kept;
  - brightness changes over more than the limit: frames kept apart;
  - a screen that is blank outside the varying area: not merged (R3).
- **Rules:** R1–R7 checked on every analysis result the tests produce, including
  that two runs give byte-identical files.
- **Pool size (R4):** a dump with more useful candidate regions than `--max-masks`
  allows; the result uses exactly that many masks and the frames of the turned-away
  regions stay unmerged.
- **Project files:** a new project has the sizes and values of section 8; a project
  written and read back is unchanged.
- **Command line:** overwrite refusal, `--force`, `--rom-name`, error messages and
  exit status, no temporary files left after a failure.
- **Report:** the file is produced and contains the summary numbers, one section per
  mask and the warnings.

### 12.2 Tests on the Twister files

A script downloads the two archives into `fixtures/` and checks their SHA-256. The
tests are skipped when the files are absent.

| Archive | SHA-256 |
|---|---|
| `https://github.com/RenewedFire/Twister-Test/raw/main/twst_405.zip` | `0a946f9c6ffdd5a28676ae181e6520b0195dec141f6eccd4e4ebda7ca1b20b67` |
| `https://github.com/RenewedFire/Twister-Test/raw/main/twst_405_11_12_2026.zip` | `d4274254c12e6cf9e882abdc3db62804c74bfcb067e374e01397050830d7dfe6` |

- **Round trip.** Reading the reference `.crom` and `.cRP` and writing them back
  reproduces both files byte for byte.
- **Hashes.** Recomputing the hash of all 5,093 reference frames from the `.cRP`
  pixels and the `.crom` masks and shape flags gives the stored values.
- **Dump facts.** The reader finds 14,443 frames, 10,301 distinct, 128x32, 4 shades.
- **Benchmark at default options:**
  - at most 4,500 kept frames;
  - at most 64 masks;
  - at most 3.5% grouped differently by hand;
  - R1–R6 hold, checked by exact comparison in test code that shares nothing with
    the tool;
  - R7 holds: a second analysis gives the same result.

**Grouped differently by hand.** For each distinct dump frame, find the reference
frame with the lowest number that matches it under that reference frame's own mask
and shape flag; frames with no match share one "none" label. For each group of two
or more frames produced by the tool, count the members whose label differs from the
group's most common label. The measure is that count summed over those groups,
divided by the number of frames in those groups.

Run time is printed by the benchmark and not asserted. The aim is under five minutes
on the Twister dump.

### 12.3 Independent check with libserum

libserum 2.8.2 was built from source during the design (branch `2.8.x`, commit
`198dc47a`, with `platforms/macos/arm64/external.sh` followed by a CMake build). It
loads the reference `.crom` placed at `<dir>/twst_405/twst_405.cROM`, and it agrees
with this document's identification model on all 14,443 dump frames:

| Outcome | Frames |
|---|---|
| Same frame chosen | 14,367 |
| An exact duplicate inside the reference project chosen | 28 |
| Reported as a repeat of the previous frame | 22 |
| Unidentified by both | 26 |

The check for the tool's output:

1. A script builds libserum 2.8.x into a cache folder that is not committed.
2. A harness loads the tool's `.cROM` through `Serum_Load(dir, rom, 1)` (flag 1
   requests 32-pixel-high frames; 64-pixel-high projects use flag 2) after calling
   `Serum_SetGenerateCRomC(false)`.
3. It passes every dump frame, in dump order, to `Serum_Colorize` and reads
   `frameID` from the returned structure.
4. For every frame, libserum must report the kept frame the tool predicted. A return
   value of 0xFFFFFFFE (same frame as before) is accepted. A return value of
   0xFFFFFFFF (no frame) is accepted only for kept frames marked inactive.

The test is skipped when the library has not been built.

### 12.4 Checks the user runs in ColorizingDMD on Windows

1. **Fresh-import comparison, early in the work.** The user imports a 500-frame dump
   (the first 500 records of `twst_405.txt`) with no filters, saves, and sends back
   the `.cROM` and `.cRP`. They are compared field by field with a tool run using
   `--max-masks 0 --no-shape-mode`. Expected differences are limited to
   `FrameDuration` and the active-frames field (section 8.4), `TimeElapsed`, and
   editor interface state such as the drawing mode. Any other difference is a defect
   in section 8.
2. **Final acceptance.** The user opens the tool's Twister output, confirms that it
   loads with the masks listed, saves, and sends back the `.cROM`. The editor
   recomputes hashes when it saves, so identical hash, mask and shape-flag fields
   confirm the masks end to end.

## 13. Risks and open points

- **Editor acceptance is unproven until the user runs the checks in section 12.4.**
  The layout matches a file the editor saved, and libserum loads that file, but only
  the editor can confirm that it opens a project this tool created.
- **The values of a new project come from reading the editor's source.** The
  fresh-import comparison is the only direct check of them.
- **Thresholds were tuned on one ROM.** The 25% limit, the 0.5 size preference, the
  2-pixel grid and the padding gaps come from the Twister dump. Other games may need
  different options.
- **Style of masking.** The hand-made project covers this dump with 1,234 frames by
  ignoring most of the display and using sprites. This design keeps identification
  strict and leaves about 4,300 frames. The user chose this trade-off.
- **CRC32 collisions cannot be prevented.** With about 10,000 dump frames and 4,000
  kept frames, the chance that some dump frame's hash collides with an unrelated kept
  frame is roughly 1% per run. The tool reports collisions; it cannot avoid them
  within the file format.
- **Size of dumps.** Time and memory were measured only on the Twister dump. Both
  grow with the number of distinct frames times the number of candidate regions.

## Appendix: sources used

| Source | Version |
|---|---|
| ColorizingDMD source (`github.com/zesinger/ColorizingDMD`, now `SerumColor/ColorizingDMD`) | v3.17.3, commit `37216912` |
| libserum source (`github.com/PPUC/libserum`) | branch `2.8.x`, commit `198dc47a` (version 2.8.2) |
| `twst_405.txt` | SHA-256 `f711aec5d42fdc423ca02bfd2c8f05c158afaee27a97acdbf59d532b81095b11` |
| `twst_405.crom` | SHA-256 `7f398d66bca5a5f37c479cff46014536b8557c334ed499208f8a40be5d3357d1` |
| `twst_405.cRP` | SHA-256 `9aca7f1dbafc9bc19f2761002e4fed9b1cbc01322f1f7b6b008546499be76d7b` |

Functions read in the ColorizingDMD source: `Save_cRom`, `Load_cRom`, `Save_cRP`,
`Load_cRP`, `Parse_TXT`, `CompareFrames`, `CopyTXTFrames2Frame`,
`Init_cFrame_Palette2`, and the CRC routines in `crc32.cpp`. In libserum:
`Identify_Frame`.

The numbers in sections 2.3, 7.4 and 12.3 come from throwaway measurement scripts
run during the design. They are targets and evidence, not code to reuse.
