---
name: comic-story-builder
description: Turn a folder of comic-strip / picture-book screenshots into a self-contained kid-friendly storytelling website (cropped panels, chapter sidebar, dual progress bar, auto pinyin, watermark backgrounds, touch + keyboard nav). Runs end-to-end with the user's inputs (screenshots path + title) and produces a deployable HTML site without any further interaction. Use whenever the user provides a directory of comic / picture-book / cartoon-strip screenshots — Snipaste files, page scans, anything — and wants them packaged for kid storytelling, including bilingual (CN/EN) annotated viewers with pinyin. Trigger phrases include "做成网页给孩子讲", "comic 转 网页", "漫画整理成 HTML", "绘本网页", "讲故事的网页", "拼音双语阅读器", or any path under `~/Documents/family/...` containing screenshot files. Trigger even when the user doesn't say "skill" — the combination of "screenshot folder + want a viewer / reader / story site for a child" is the right signal.
---

# Comic Story Builder

Convert a folder of comic-page / picture-book screenshots into a
self-contained HTML storytelling site. The output is static (one HTML file
+ comics + bg images + JSON) and can be served by any host.

This skill runs **end-to-end with no follow-up questions**. The user gives
you a path and a title; you produce the site.

## Required inputs (capture from the user's request)

| Field | Notes |
|---|---|
| `screenshots_dir` | **Required.** Absolute path to a folder of screenshot images |
| `title` | **Required.** What the kid (and the URL) calls this collection. Whatever the user wants — doesn't have to match any book's official title |

## Optional inputs (use sensible defaults if absent)

| Field | Default |
|---|---|
| `subtitle` | empty (no English subtitle on cover) |
| `id` | derived from the directory name (used as `localStorage` key for last-page memory) |
| `chapters` | auto-detected: extract visible chapter titles from screenshots; if none visible, fall back to one chapter named "故事 / Story" containing all panels |
| `output_dir` | the screenshots dir itself (the site is built in place; the user's screenshots stay alongside) |

If the user doesn't supply title, ask **once** and then proceed. Don't ask
about anything else — guess and tell them.

## The toolkit (bundled with this skill)

Four assets sit next to this `SKILL.md` in the skill's base directory (the
"Base directory for this skill: ..." path you receive when this skill loads).

| File | Role |
|---|---|
| `crop_panels.py` | Auto-detects comic frames in each screenshot (handles dark and light backgrounds), crops to `comics/comic_NN.png`, generates `captions_template.json`, syncs `background/`, and bakes everything into a single self-contained `index.html`. Produces a true single-file deliverable that opens via `file://` (no HTTP server needed) |
| `viewer.html` | Reader template. Reads data from inline `window.STORY_DATA` / `PANEL_IMAGES` / `BG_IMAGES` globals; the build step injects these into the placeholder `<!-- INLINE_DATA -->`. Computes pinyin client-side via `pinyin-pro` from a CDN |
| `background/` | Pool of watermark photos. Ships with placeholder gradients — the user is expected to swap in family photos later |
| `build_ppt.py` | Optional alternate output: a `.pptx` instead of HTML (only if the user explicitly asks for PPT) |

When invoking `crop_panels.py`, give it the absolute path
`<skill-base-dir>/crop_panels.py`. The script self-resolves `viewer.html`
template and `background/` via `Path(__file__).parent`, so as long as the
skill's files stay together it works without any config.

Required Python deps — install if missing:
```
pip install Pillow numpy scipy pypinyin
```

## End-to-end workflow

### 1. Crop panels and prep assets

```
python "<skill-base-dir>/crop_panels.py" "<screenshots_dir>"
```

After this runs, `<screenshots_dir>` contains: `comics/comic_NN.png`
(cropped sources), `captions_template.json`, `background/` (watermark
sources synced from kit), and a first-pass `index.html`. The HTML at this
point has only the cropper-generated empty captions — you'll rebuild it
in step 4 once you've written real ones. Note the per-file panel count
the cropper printed.

### 2. Survey the panels and decide the chapter structure

`Read` each screenshot to understand what's drawn — characters, actions,
where each story starts. Match each `comic_NN.png` to its source via the
`_source` field in `captions_template.json`.

**Chapter detection:**
- If a screenshot shows a clearly displayed chapter title (one centered
  heading separate from any caption — often "中文标题 English Title"),
  that's the start of a new chapter
- Single-story collections without explicit chapter dividers → wrap
  everything in one chapter named after the user-supplied `title`
- Sometimes a story spans non-adjacent screenshot files (e.g., a
  supplementary screenshot taken later has a later filename timestamp but
  covers the start of an earlier story). The chapter `panels` list is
  free-form — assemble panels from any source files in the right reading
  order

Don't be confused by circled panel numbers. Chapters often re-number from ①
inside, but it's also common for panels labeled ⑤ ⑥ to appear right under
a chapter title (the original print page numbered things differently). The
**heading text** is the boundary marker, not the circled numbers.

### 3. Write the captions

For each panel, write **a brief original Chinese sentence + a brief
original English sentence** in your own words, describing what's
**visually drawn** in that panel — characters, postures, actions, setting.

These are NOT transcriptions:

- Do **not** type out the text inside any speech bubbles, signs, papers, or
  printed labels visible in the source image
- Do **not** copy any printed bilingual caption that the screenshot includes
  below the panel — that text is the publisher's translation work and is
  separately copyrighted even when the original artwork isn't
- Do write your own functional narration: "爸爸 stares at the messy
  homework on the table" / "Father stares at the messy homework on the
  table." Short. Plain. Describes the picture, not the dialogue.

This is the central guardrail. The skill's promise is "auto-generate a
working site"; the IP-safe way to deliver that is to narrate the visuals
in original words rather than reproduce the publisher's text.

If the user explicitly says something like "I wrote the dialogue myself,
just OCR my own writing" or "use this caption table I'm pasting", then
honor that — those are theirs to use. Otherwise, default to original
visual descriptions.

Pinyin: never put pinyin in the JSON. The viewer's JS computes it at
runtime from each `cn` string.

### 4. Compose `captions.json`

```jsonc
{
  "id":       "<from input or derived>",
  "title":    "<user-supplied title>",
  "subtitle": "<user-supplied subtitle or empty>",
  "chapters": [
    {
      "name":     "<chapter name from your detection>",
      "subtitle": "<English chapter title if visible, else empty>",
      "panels":   ["comic_NN.png", ...]   // reading order
    }
  ],
  "captions": {
    "comic_NN.png": { "cn": "<your visual description in CN>",
                       "en": "<your visual description in EN>",
                       "_source": "<keep what was already there>" }
  }
}
```

Save as `<screenshots_dir>/captions.json`. Delete `captions_template.json`
once `captions.json` is written.

### 5. Rebuild the single-file `index.html`

Now that `captions.json` has real text, rebuild `index.html` so it embeds
the new captions (the cropper's earlier pass produced an `index.html` with
only empty placeholders):

```
python "<skill-base-dir>/crop_panels.py" "<screenshots_dir>" --rebuild
```

`--rebuild` skips cropping and just bakes `captions.json` + `comics/*` +
`background/*` into `<screenshots_dir>/index.html`. The output is one
self-contained file — every comic and background image is encoded as a
data URI inside the HTML.

### 6. Verify by opening the file directly (no server)

```
"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" \
  --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
  --window-size=1366,800 --virtual-time-budget=4000 \
  --screenshot=<screenshots_dir>/_preview_cover.png \
  "file:///<screenshots_dir>/index.html"
```

(Repeat with `?p=1` appended to the URL for the first panel page.)

`Read` both screenshots. The cover should show the title with chapter
sidebar; the panel page should show the comic image filling the upper area
with captions below, sidebar on left, double-row progress bar at bottom.

Delete the `_preview_*.png` files when done. There's no server to stop.

### 7. Report and stop

Tell the user, briefly:

- The deliverable is `<screenshots_dir>/index.html` — single self-contained
  file (~2-3 MB depending on image count). Just double-click it. No server
  needed.
- The folder also contains `comics/`, `captions.json`, and `background/` as
  the editable sources. The user can change anything in those, then re-run
  `python <skill-base-dir>/crop_panels.py "<screenshots_dir>" --rebuild`
  to regenerate `index.html`.
- Deployment: upload `index.html` alone (everything is inlined). The
  `comics/` and `background/` folders only need to travel along if the
  user wants to keep editing.
- Two common edits the user might want:
  - Swap your auto-narration for the book's exact text (or anything else)
    by editing `captions.json` then `--rebuild`.
  - Drop their own family photos into `background/` then `--rebuild` (or
    use `--refresh-bg` to also re-sync from the kit's defaults).
- Then stop. Do not ask follow-up questions.

## Troubleshooting

- **Cropper undercount on white-bg screenshots**: lower `min_fill` in
  `_detect_panels_components` (`crop_panels.py`).
- **Cropper undercount on dark-bg screenshots**: lower `row_threshold` or
  raise `merge_gap` in `find_panels_in_column`.
- **Wrong panel count vs your visual count**: before re-tuning, view the
  actual cropped `comics/comic_NN.png` files. Sometimes the cropper is
  right and your initial count was off (e.g., one wide panel that looked
  like two).
- **Image too small in viewer**: the layout needs `flex: 1 1 0` +
  `min-height: 0` on `.image-wrap` and `width:100%; height:100%; object-fit: contain`
  on the img. If `.panel-page` accidentally has `justify-items: center`,
  children won't stretch — remove that.
- **Captions overflow on mobile**: captions have `overflow-wrap: anywhere`.
  If text still overflows, the `.page-frame` mobile padding may be too
  tight — bump it.
- **Background watermark missing**: check `<screenshots_dir>/background/`
  has actual image files. Re-run with `--refresh-bg` to re-sync from kit
  defaults and rebuild.
- **`index.html` looks empty / "missing STORY_DATA" error**: the file was
  served but the inline script didn't execute. Make sure it was opened via
  `file://` (or any HTTP path), and that the build step actually ran (you
  should see "Single-file HTML: ..." in the cropper output). Re-run with
  `--rebuild`.
- **`captions.json` parse error**: re-validate as JSON; the build step
  fails fast on bad JSON.
