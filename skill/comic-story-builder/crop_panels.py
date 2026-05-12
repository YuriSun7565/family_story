"""
Detect and crop comic panels from screenshots.

The image is assumed to have a dark/uniform background with one or more comic
panels (any colour) arranged in columns. The script:
  1. Auto-detects the vertical column bands containing panels.
  2. Within each column, finds horizontal bands of solid panel content.
  3. Tightens the bounding box and saves each panel as comic_NN.png.
  4. Writes a captions_template.json listing every panel for you to fill in.

Usage:
    python crop_panels.py <input_dir>
    python crop_panels.py <input_dir> --output <comics_dir>
    python crop_panels.py <input_dir> --pattern "Snipaste_*.png"

Outputs (default):
    <input_dir>/comics/comic_01.png ... comic_NN.png
    <input_dir>/captions_template.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image


# ---------- core detection -------------------------------------------------- #

def _runs(mask, *, min_length: int = 1, merge_gap: int = 0):
    """Return list of (start, end) for runs of True in a 1-D bool array."""
    runs = []
    in_run = False
    start = 0
    for i, v in enumerate(mask):
        if v and not in_run:
            in_run = True
            start = i
        elif not v and in_run:
            in_run = False
            runs.append((start, i - 1))
    if in_run:
        runs.append((start, len(mask) - 1))

    merged = []
    for r in runs:
        if merged and r[0] - merged[-1][1] - 1 <= merge_gap:
            merged[-1] = (merged[-1][0], r[1])
        else:
            merged.append(r)
    return [r for r in merged if r[1] - r[0] + 1 >= min_length]


def _detect_bg_kind(arr):
    """Sample image corners to decide whether the page background is dark or light.
    Returns 'dark' (typical PowerPoint dark slide) or 'light' (white reader page)."""
    H, W, _ = arr.shape
    samples = np.concatenate([
        arr[:8, :8].reshape(-1, 3),
        arr[:8, -8:].reshape(-1, 3),
        arr[-8:, :8].reshape(-1, 3),
        arr[-8:, -8:].reshape(-1, 3),
    ])
    avg = samples.mean(axis=0).sum()
    return 'dark' if avg < 300 else 'light'


def _panel_color_mask(arr, bg_kind=None):
    """A pixel counts as 'panel content' = colored material from a comic frame.

    On a dark page: panel pixels have mid-tone RGB sum (excludes dark bg AND
    any pure-light caption text).
    On a light page: panel pixels are anything that ISN'T near-white background.
    """
    if bg_kind is None:
        bg_kind = _detect_bg_kind(arr)
    R = arr[:, :, 0].astype(int)
    G = arr[:, :, 1].astype(int)
    B = arr[:, :, 2].astype(int)
    s = R + G + B
    if bg_kind == 'dark':
        return (s > 100) & (s < 600)
    # light bg: anything not near-white. White ≈ sum 720-765; allow a tolerance.
    return s < 700


def find_column_bands(panel_mask, *, min_width=120, merge_gap=40, threshold=0.08):
    """Find vertical bands (x-ranges) that contain comic-panel content."""
    H, _ = panel_mask.shape
    col_cov = panel_mask.sum(axis=0) / H
    is_active = col_cov > threshold
    return _runs(is_active, min_length=min_width, merge_gap=merge_gap)


def find_panels_in_column(panel_mask, col_x, *, min_height=80, merge_gap=20,
                          row_threshold=0.60, col_threshold=0.50):
    """Within a column band, find rectangular panels."""
    cx0, cx1 = col_x
    sub = panel_mask[:, cx0:cx1 + 1]
    rc = sub.sum(axis=1) / sub.shape[1]
    is_panel = rc > row_threshold
    runs = _runs(is_panel, min_length=min_height, merge_gap=merge_gap)
    panels = []
    for ry0, ry1 in runs:
        block = panel_mask[ry0:ry1 + 1, cx0:cx1 + 1]
        cc = block.sum(axis=0) / block.shape[0]
        active_cols = cc > col_threshold
        if not active_cols.any():
            continue
        idx = np.where(active_cols)[0]
        x0 = cx0 + int(idx.min())
        x1 = cx0 + int(idx.max())
        panels.append((x0, ry0, x1, ry1))
    return panels


def detect_panels(img_arr):
    """Detect all panels in an image; returns list of (x0, y0, x1, y1)."""
    bg = _detect_bg_kind(img_arr)
    if bg == 'light':
        return _sort_reading_order(_detect_panels_components(img_arr))
    # Original column-scan algorithm: works well for dark backgrounds where
    # caption text (light grey) and panels (mid-tone) are well separated.
    mask = _panel_color_mask(img_arr, bg_kind=bg)
    bands = find_column_bands(mask)
    panels = []
    for band in bands:
        panels.extend(find_panels_in_column(mask, band))
    return _sort_reading_order(panels)


def _detect_panels_components(arr, *, min_area=8000, min_w=180, min_h=110,
                              min_fill=0.22, dilate=4):
    """Connected-component panel detection. Robust on light backgrounds where
    caption text mixes into the same x-band as the panels — each panel is a
    distinct dense rectangle, captions are thin sparse rows that get filtered
    out by the fill-ratio check."""
    try:
        from scipy import ndimage
    except ImportError:
        sys_stderr_print('scipy required for light-bg detection; pip install scipy')
        return []
    mask = _panel_color_mask(arr, bg_kind='light')
    dilated = ndimage.binary_dilation(mask, iterations=dilate)
    labeled, num = ndimage.label(dilated)
    panels = []
    for i in range(1, num + 1):
        ys, xs = np.where(labeled == i)
        if len(ys) < min_area:
            continue
        x0, x1 = int(xs.min()), int(xs.max())
        y0, y1 = int(ys.min()), int(ys.max())
        w, h = x1 - x0 + 1, y1 - y0 + 1
        if w < min_w or h < min_h:
            continue
        fill = mask[y0:y1 + 1, x0:x1 + 1].sum() / (w * h)
        if fill < min_fill:
            continue
        panels.append((x0, y0, x1, y1))
    return panels


def sys_stderr_print(*a, **kw):
    print(*a, file=sys.stderr, **kw)


def _sort_reading_order(panels):
    """Sort: columns left-to-right, panels top-to-bottom inside each column."""
    if not panels:
        return panels
    panels = sorted(panels, key=lambda p: p[0])
    columns = [[panels[0]]]
    for p in panels[1:]:
        col = columns[-1]
        col_x0 = min(q[0] for q in col)
        col_x1 = max(q[2] for q in col)
        overlap = max(0, min(p[2], col_x1) - max(p[0], col_x0))
        min_w = min(col_x1 - col_x0, p[2] - p[0])
        if min_w > 0 and overlap / min_w > 0.5:
            col.append(p)
        else:
            columns.append([p])
    out = []
    for col in columns:
        col.sort(key=lambda p: p[1])
        out.extend(col)
    return out


# ---------- background sync ------------------------------------------------- #

BG_EXTS = ('.jpg', '.jpeg', '.png', '.webp')


def sync_background(kit_dir: Path, story_dir: Path, *, fresh_copy: bool = False):
    """Mirror kit's background/ → story_dir/background/.

    - Files already present in story_dir/background/ are preserved (user's
      per-story photos win).
    - Missing files are copied from kit's background/.
    - If `fresh_copy=True`, overwrite all files from kit (use with --refresh-bg).
    """
    src = kit_dir / 'background'
    dst = story_dir / 'background'
    dst.mkdir(parents=True, exist_ok=True)
    copied = 0
    if src.exists():
        for f in src.iterdir():
            if not f.is_file() or f.suffix.lower() not in BG_EXTS:
                continue
            target = dst / f.name
            if fresh_copy or not target.exists():
                shutil.copy2(f, target)
                copied += 1
    images = sorted(p.name for p in dst.iterdir()
                    if p.is_file() and p.suffix.lower() in BG_EXTS)
    print(f'Background:        {dst}  ({len(images)} images, '
          f'{copied} copied from kit)')
    return images


# ---------- Build single-file HTML ----------------------------------------- #

def _file_to_data_uri(path: Path) -> str:
    """Read a file and return a 'data:<mime>;base64,...' URI."""
    import base64
    suffix = path.suffix.lower()
    mime = {
        '.png':  'image/png',
        '.jpg':  'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.webp': 'image/webp',
        '.gif':  'image/gif',
    }.get(suffix, 'application/octet-stream')
    b64 = base64.b64encode(path.read_bytes()).decode('ascii')
    return f'data:{mime};base64,{b64}'


def build_single_html(kit_dir: Path, story_dir: Path,
                       captions_path: Path = None,
                       comics_dir: Path = None,
                       bg_dir: Path = None,
                       output_path: Path = None) -> Path:
    """Bake captions + every referenced comic + every background image into a
    single self-contained index.html that opens via file:// (no server)."""
    import json as _json
    captions_path = captions_path or (story_dir / 'captions.json')
    comics_dir   = comics_dir   or (story_dir / 'comics')
    bg_dir       = bg_dir       or (story_dir / 'background')
    output_path  = output_path  or (story_dir / 'index.html')

    if not captions_path.exists():
        print(f'No captions.json at {captions_path}; skipping HTML build',
              file=sys.stderr)
        return None
    if not (kit_dir / 'viewer.html').exists():
        print(f'viewer.html template not found in kit ({kit_dir})',
              file=sys.stderr)
        return None

    config = _json.loads(captions_path.read_text(encoding='utf-8'))

    # Encode every referenced panel image to a data URI
    panel_images = {}
    for ch in config.get('chapters', []) or []:
        for img_name in ch.get('panels', []) or []:
            if img_name in panel_images:
                continue
            img_path = comics_dir / img_name
            if not img_path.exists():
                print(f'WARNING: missing panel {img_path}', file=sys.stderr)
                continue
            panel_images[img_name] = _file_to_data_uri(img_path)

    # Encode every background image to a data URI
    bg_uris = []
    if bg_dir.exists():
        for f in sorted(bg_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in BG_EXTS:
                bg_uris.append(_file_to_data_uri(f))

    # Build the inline data block
    inline = (
        '<script>\n'
        '  window.STORY_DATA = '
        + _json.dumps(config, ensure_ascii=False) + ';\n'
        '  window.PANEL_IMAGES = '
        + _json.dumps(panel_images) + ';\n'
        '  window.BG_IMAGES = '
        + _json.dumps(bg_uris) + ';\n'
        '</script>'
    )

    template = (kit_dir / 'viewer.html').read_text(encoding='utf-8')
    if '<!-- INLINE_DATA -->' not in template:
        print('ERROR: kit viewer.html missing <!-- INLINE_DATA --> placeholder',
              file=sys.stderr)
        return None
    html = template.replace('<!-- INLINE_DATA -->', inline)
    output_path.write_text(html, encoding='utf-8')

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f'Single-file HTML:  {output_path}  '
          f'({len(panel_images)} panels + {len(bg_uris)} bgs, '
          f'{size_mb:.2f} MB)')
    return output_path


# ---------- CLI ------------------------------------------------------------- #

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('input_dir', type=Path,
                        help='Directory containing screenshot images')
    parser.add_argument('--output', '-o', type=Path,
                        help='Output dir for cropped panels (default: <input>/comics)')
    parser.add_argument('--pattern', default='*.png',
                        help='Glob pattern for screenshots (default: *.png)')
    parser.add_argument('--padding', type=int, default=4,
                        help='Padding around each crop in pixels (default: 4)')
    parser.add_argument('--captions', type=Path,
                        help='Output path for captions JSON template '
                             '(default: <input>/captions_template.json)')
    parser.add_argument('--no-captions', action='store_true',
                        help='Skip writing the captions JSON template')
    parser.add_argument('--no-background', action='store_true',
                        help='Skip syncing background/ into the input dir')
    parser.add_argument('--no-build', action='store_true',
                        help='Skip baking the single-file index.html at the end')
    parser.add_argument('--refresh-bg', action='store_true',
                        help='Only re-sync background/ then rebuild index.html, '
                             'skip cropping')
    parser.add_argument('--rebuild', action='store_true',
                        help='Only rebuild index.html from existing captions.json '
                             '+ comics/ + background/, skip cropping')
    args = parser.parse_args(argv)

    KIT_DIR = Path(__file__).resolve().parent
    input_dir: Path = args.input_dir

    # --refresh-bg: only sync background then rebuild index.html, skip cropping
    if args.refresh_bg:
        sync_background(KIT_DIR, input_dir, fresh_copy=True)
        build_single_html(KIT_DIR, input_dir)
        return 0

    # --rebuild: only rebuild index.html from existing captions/comics/bgs
    if args.rebuild:
        build_single_html(KIT_DIR, input_dir)
        return 0

    output_dir: Path = args.output or (input_dir / 'comics')
    output_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(input_dir.glob(args.pattern))
    if not files:
        print(f'No files matching {args.pattern} in {input_dir}', file=sys.stderr)
        return 1

    crops = []  # (out_name, source_name, panel_index_in_source)
    for f in files:
        img = Image.open(f).convert('RGB')
        arr = np.array(img)
        panels = detect_panels(arr)
        print(f'{f.name}: {len(panels)} panels')
        for j, (x0, y0, x1, y1) in enumerate(panels, 1):
            W, H = img.size
            x0p = max(0, x0 - args.padding)
            y0p = max(0, y0 - args.padding)
            x1p = min(W, x1 + args.padding)
            y1p = min(H, y1 + args.padding)
            n = len(crops) + 1
            out_name = f'comic_{n:02d}.png'
            img.crop((x0p, y0p, x1p, y1p)).save(output_dir / out_name)
            crops.append((out_name, f.name, j))

    print(f'\nSaved {len(crops)} panels to {output_dir}')

    if not args.no_captions:
        cap_path = args.captions or (input_dir / 'captions_template.json')
        template = {
            'title': '',
            'subtitle': '',
            'chapters': [
                {
                    'name': '',
                    'subtitle': '',
                    'panels': [name for name, _, _ in crops],
                }
            ],
            'captions': {
                name: {'cn': '', 'en': '', '_source': f'{src} #{j}'}
                for name, src, j in crops
            },
        }
        cap_path.write_text(json.dumps(template, ensure_ascii=False, indent=2),
                            encoding='utf-8')
        print(f'Captions template: {cap_path}')
        print('  → Fill in title / chapters / captions in this JSON.')

    if not args.no_background:
        sync_background(KIT_DIR, input_dir, fresh_copy=False)

    if not args.no_build:
        build_single_html(KIT_DIR, input_dir)

    print(f'\n→ Double-click {input_dir / "index.html"} to read it. '
          f'No server needed.')
    print(f'  After editing captions.json or swapping background/, run:')
    print(f'    python {Path(__file__).name} "{input_dir}" --rebuild')
    return 0


if __name__ == '__main__':
    sys.exit(main())
