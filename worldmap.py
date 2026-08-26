#!/usr/bin/env python3
"""
worldmap.py — the game's in-game world map, out to PNG and back in.

    python worldmap.py extract            # T_WorldMap_Jeju -> worldmap_vanilla.png
    python worldmap.py extract --mod      # whatever our pak currently ships

This is the OTHER half of map.py. That one photographs your level; this one
reads the texture the game actually draws on the in-game map, so the two can
be lined up and the island can be painted into the right place.

THE ASSET
    UI/InGame/Map/WorldMap/T_WorldMap_Jeju
    4096 x 4096, PF_DXT1 (BC1), no mips.

    The .uexp is 8,388,751 bytes: 119 bytes of header, then exactly
    4096*4096/2 = 8,388,608 bytes of BC1 blocks, then a 24-byte footer ending
    in the package tag 0x9E2A83C1. Those numbers are checked at runtime rather
    than trusted, so a game update that changes the format fails loudly instead
    of writing a corrupted map.

WHY BC1 MATTERS
    BC1 is lossy 4x4 block compression with a 1-bit alpha. Re-encoding a PNG
    back to BC1 loses a little quality every round trip, so edit from the
    ORIGINAL PNG each time rather than re-extracting your own output.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import struct
import sys

from mt_paths import GAME_CONTENT, MOD_CONTENT_ROOT, effective_asset

REL = "UI/InGame/Map/WorldMap/T_WorldMap_Jeju"
SIZE = 4096
HEADER = 119                      # bytes before the first BC1 block
PAYLOAD = SIZE * SIZE // 2        # BC1: 8 bytes per 4x4 block
PACKAGE_TAG = 0x9E2A83C1


def _split(uexp: bytes) -> tuple[bytes, bytes, bytes]:
    """(header, bc1 payload, footer), validated."""
    if len(uexp) < HEADER + PAYLOAD:
        raise SystemExit(f"uexp is {len(uexp):,} bytes, too small for a "
                         f"{SIZE}x{SIZE} BC1 texture")
    tag = struct.unpack("<I", uexp[-4:])[0]
    if tag != PACKAGE_TAG:
        raise SystemExit(f"unexpected package tag 0x{tag:08X} — the texture "
                         f"format has changed, refusing to guess")
    return uexp[:HEADER], uexp[HEADER:HEADER + PAYLOAD], uexp[HEADER + PAYLOAD:]


def decode_bc1(data: bytes, size: int = SIZE):
    """BC1 -> an RGB numpy array. Straightforward: each 8-byte block holds two
    RGB565 endpoints and sixteen 2-bit indices into a 4-colour ramp."""
    import numpy as np
    blocks = size // 4
    raw = np.frombuffer(data, dtype=np.uint8).reshape(-1, 8)
    c0 = raw[:, 0].astype(np.uint16) | (raw[:, 1].astype(np.uint16) << 8)
    c1 = raw[:, 2].astype(np.uint16) | (raw[:, 3].astype(np.uint16) << 8)

    def unpack565(c):
        r = ((c >> 11) & 0x1F).astype(np.float32) * (255.0 / 31.0)
        g = ((c >> 5) & 0x3F).astype(np.float32) * (255.0 / 63.0)
        b = (c & 0x1F).astype(np.float32) * (255.0 / 31.0)
        return np.stack([r, g, b], axis=-1)

    e0, e1 = unpack565(c0), unpack565(c1)
    # Four-entry palette. When c0 > c1 the middle two are 1/3 and 2/3 blends;
    # otherwise it is a 3-colour mode whose fourth entry is transparent black.
    opaque = (c0 > c1)[:, None]
    p2 = np.where(opaque, (2 * e0 + e1) / 3.0, (e0 + e1) / 2.0)
    p3 = np.where(opaque, (e0 + 2 * e1) / 3.0, 0.0)
    palette = np.stack([e0, e1, p2, p3], axis=1)          # (nblocks, 4, 3)

    idx = raw[:, 4:8].copy().view(np.uint32).reshape(-1)   # 16 x 2-bit indices
    shifts = (np.arange(16, dtype=np.uint32) * 2)
    sel = (idx[:, None] >> shifts[None, :]) & 0x3          # (nblocks, 16)

    texel = np.take_along_axis(palette, sel[:, :, None], axis=1)   # (n,16,3)
    texel = texel.reshape(-1, 4, 4, 3)                             # block rows
    img = texel.reshape(blocks, blocks, 4, 4, 3).transpose(0, 2, 1, 3, 4)
    return img.reshape(size, size, 3).astype(np.uint8)


def _top_colours(im, n=8):
    """The most common EXACT colours, with their share of the image. A flat
    unlit material shows up here as one huge entry; lit terrain never does,
    because lighting spreads it across thousands of near-values."""
    import numpy as np
    key = (im[:, :, 0].astype(np.int32) << 16
           | im[:, :, 1].astype(np.int32) << 8
           | im[:, :, 2].astype(np.int32))
    vals, counts = np.unique(key, return_counts=True)
    order = np.argsort(-counts)[:n]
    total = key.size
    return [(((int(vals[i]) >> 16) & 255, (int(vals[i]) >> 8) & 255, int(vals[i]) & 255),
             counts[i] / total) for i in order]


def _shift(a, dy, dx):
    import numpy as np
    o = np.zeros_like(a)
    ys, yd = slice(max(0, dy), a.shape[0] + min(0, dy)), slice(max(0, -dy), a.shape[0] + min(0, -dy))
    xs, xd = slice(max(0, dx), a.shape[1] + min(0, dx)), slice(max(0, -dx), a.shape[1] + min(0, -dx))
    o[yd, xd] = a[ys, xs]
    return o


def _reaches_border(mask, cap=4000):
    """The part of `mask` a path can reach from the edge of the frame."""
    import numpy as np
    reach = np.zeros_like(mask)
    reach[0, :], reach[-1, :] = mask[0, :], mask[-1, :]
    reach[:, 0], reach[:, -1] = mask[:, 0], mask[:, -1]
    for _ in range(cap):
        g = reach.copy()
        g[1:, :] |= reach[:-1, :]; g[:-1, :] |= reach[1:, :]
        g[:, 1:] |= reach[:, :-1]; g[:, :-1] |= reach[:, 1:]
        g &= mask
        if g.sum() == reach.sum():
            return g
        reach = g
    return reach


def _strip_dark_slivers(alpha, rgb, passes=3, dark=40, lonely=6):
    """Key opaque pixels that are dark AND almost surrounded by transparency.

    The water plane is a little smaller than the frame, so its edge runs
    through open water with painted sea on one side and bare background on the
    other. Both get keyed; the pixel of blend between them belongs to neither
    -- measured at RGB(9, 0, 8), one over the black cutoff and nowhere near the
    magenta floor -- and it survives as a hairline that traces the rectangle
    across the finished map.

    Neither colour test can be widened to catch it without reaching real
    terrain, so this asks a different question: what is around it. A pixel with
    transparency on six sides is not part of anything. Restricted to DARK
    pixels on purpose -- the suspension bridge over the bay is one pixel wide,
    adrift in exactly the same way, and bright, so this leaves it alone.
    """
    import numpy as np
    killed = np.zeros(alpha.shape, dtype=bool)
    for _ in range(passes):
        t = (alpha == 0).astype(np.uint8)
        near = sum(_shift(t, dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                   if (dy, dx) != (0, 0))
        hit = (alpha != 0) & (rgb.max(axis=2) < dark) & (near >= lonely)
        if not hit.any():
            break
        alpha[hit] = 0
        killed |= hit
    return killed


def _inpaint(rgb, gaps, cap=200):
    """Grow the surrounding pixels inward over `gaps`, one ring per pass.

    Works on the LIST of gap pixels, not on whole-image arrays. The gaps are a
    rounding error -- a few thousand pixels in tens of millions -- but the
    obvious implementation allocates two float32 images to find them, which is
    414 MB at a 6016 capture and simply fails. Cost here follows the number of
    holes, so raising MTMI_MAP_SCALE costs nothing extra.
    """
    import numpy as np
    out = rgb                      # already a private copy from the caller
    h, w = gaps.shape
    todo = gaps.copy()
    for _ in range(cap):
        ys, xs = np.nonzero(todo)
        if len(ys) == 0:
            break
        acc = np.zeros((len(ys), 3), np.uint32)
        cnt = np.zeros(len(ys), np.uint32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            yy, xx = ys + dy, xs + dx
            ok = (yy >= 0) & (yy < h) & (xx >= 0) & (xx < w)
            yy, xx = np.clip(yy, 0, h - 1), np.clip(xx, 0, w - 1)
            ok &= ~todo[yy, xx]          # only average pixels already settled
            acc[ok] += out[yy[ok], xx[ok]]
            cnt[ok] += 1
        fill = cnt > 0
        if not fill.any():
            break                        # nothing borders known pixels; stop
        out[ys[fill], xs[fill]] = (acc[fill] // cnt[fill][:, None]).astype(np.uint8)
        todo[ys[fill], xs[fill]] = False
    return out


def cutout(src: str = "static_meshes_parts/map.png",
           out: str = "static_meshes_parts/map_cutout.png",
           keys: list | None = None, tol: int = 30, key_tol: int = 12,
           water: bool = False) -> int:
    """Turn map.py's flat background into real transparency.

    map.py clears the render target to a colour nothing in the world uses
    (magenta), so keying it out cannot eat real pixels the way keying white or
    black would -- terrain and buildings are full of both.

    Runs OUT here rather than inside the editor because UE's Python has no
    imaging library, and reading 16.7M pixels back through the render target
    API one at a time is not a serious option.
    """
    try:
        import numpy as np
        from PIL import Image
        # These images are deliberately enormous -- a 16384 map is 268 MPx --
        # and Pillow's decompression-bomb guard is aimed at untrusted input,
        # not at a file this pipeline just wrote.
        Image.MAX_IMAGE_PIXELS = None
    except ImportError as e:
        print(f"  needs numpy and Pillow: {e}", file=sys.stderr)
        return 1
    import json

    sp = pathlib.Path(src)
    if not sp.is_file():
        print(f"  {sp} not found — run map.py in the editor first", file=sys.stderr)
        return 1

    im = np.array(Image.open(sp).convert("RGB")).astype(np.int16)

    # What is actually in the image, before deciding what to remove. A flat
    # unlit water material appears here as a single large exact colour, which
    # is the whole point of making it unlit: lit water reflects the sky and
    # smears across thousands of shades that no key can catch.
    print("  most common exact colours:")
    for rgb, frac in _top_colours(im):
        print(f"    {rgb}  #{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}  {frac:6.2%}")

    # Detect the background from the image itself rather than requiring the
    # capture to paint a known colour. The four corners of a top-down render
    # are sky, and asking map.py to clear to a keyable colour meant touching
    # the render setup -- which is where two black-image regressions came from.
    # Reading the corners costs nothing and cannot break the capture.
    h, w, _ = im.shape
    corners = np.stack([im[0, 0], im[0, w - 1], im[h - 1, 0], im[h - 1, w - 1]])
    bg = tuple(int(v) for v in np.median(corners, axis=0))
    spread = int(np.abs(corners - np.array(bg)).max())
    if spread > 24:
        print(f"  corners disagree by {spread} — the background may not be flat; "
              f"keying on {bg} anyway", file=sys.stderr)

    chroma = None
    bounds = sp.with_name("map_bounds.json")
    if bounds.is_file():
        try:
            meta = json.loads(bounds.read_text(encoding="utf-8"))
            if meta.get("background_rgb"):
                bg = tuple(meta["background_rgb"])   # an explicit colour wins
            # map.py paints the water a flat unlit colour for the capture and
            # records it here, so the key is never typed in twice and cannot
            # drift out of step with what was actually rendered.
            if meta.get("chroma_rgb"):
                chroma = tuple(meta["chroma_rgb"])
                print(f"  map.py painted the water {chroma} "
                      f"- keying that, --water not needed")
        except Exception:
            pass
    # Tolerance, not equality: BC1 is not involved here but the render target
    # and PNG round trip still shift a value or two at the edges.
    # --water keys LIT water, which no single colour can catch. Measured off a
    # real capture: the sea occupies 48% of the frame spanning R 0-39, G 21-81,
    # B 43-118 -- a whole family of shades, because it reflects the sky. What is
    # constant is the SHAPE of the colour: blue clearly ahead of green, green
    # clearly ahead of red, red almost absent. Terrain is the opposite (brown,
    # sage, grey), so the rule separates them without needing a flat material.
    # Measured, so nobody retries these: a shadowed gully and the sea come out
    # the SAME pixels. Both are lit by the sky and nothing else, so hue is
    # identical (R exactly 0, B-G 36 for both) and brightness overlaps (sea
    # B 43-118, gullies 78-94). Clustering does not save it either -- the
    # gullies chain down the slopes to the coast, so anything connectivity-based
    # keeps them, and opening keys on width so wide ravines survive it.
    #
    # The fix is upstream: HIDE_MATCHING in map.py keeps the water out of the
    # capture, the sea comes back as flat background, and the key is exact.
    # --water is the fallback for a render where that did not match.
    if water:
        b, g, r = im[:, :, 2], im[:, :, 1], im[:, :, 0]
        wet = (b > g + 20) & (g > r + 20) & (r < 40)
        print(f"    water rule -> {wet.mean():6.2%} of the image")
    else:
        wet = None

    alpha = np.full(im.shape[:2], 255, dtype=np.uint8)
    rgb = im.astype(np.uint8)

    if chroma is not None:
        # Match the SHAPE of the painted colour, not its value. The capture is
        # tone-mapped, so a material authored at pure (255, 0, 255) arrives
        # spread over R 91-206 and B 71-176 -- exposure and vignetting see to
        # that, and no tolerance narrow enough to be safe would cover it. What
        # tone mapping cannot do is reorder the channels: magenta keeps green
        # far below both red and blue, and nothing in a landscape does that.
        hi = [i for i, v in enumerate(chroma) if v > 127]
        lo = [i for i, v in enumerate(chroma) if v <= 127]
        m = np.ones(im.shape[:2], dtype=bool)
        for i in hi:
            m &= im[:, :, i] > 80
        for i in lo:
            m &= im[:, :, i] < 60
        for i in hi:
            for j in lo:
                m &= im[:, :, i] > im[:, :, j] + 50
        alpha[m] = 0
        print(f"    painted sea -> {m.mean():6.2%} of the image")

        # Black means two different things and they must not be conflated. The
        # water plane is slightly smaller than the frame, so bare background
        # shows past its edge -- that is outside the island and belongs
        # transparent. Black with land all around it is a gap between meshes,
        # the camera seeing through to an empty render target, and that belongs
        # filled. Reaching the frame edge is what separates them.
        #
        # Safe to decide by connectivity here, where every earlier attempt at
        # it failed, because colour has already taken the sea out of the
        # question. A bridge sealing off a bay used to turn that bay into an
        # enclosed region and sink the whole idea; the bay is magenta now, so
        # this never sees it.
        blk = (im.max(axis=2) < 8) & (alpha != 0)
        if blk.any():
            outer = _reaches_border(blk)          # not `out` - that is the filename
            alpha[outer] = 0
            gaps = blk & ~outer
            print(f"    background past the water's edge -> {outer.mean():6.2%}")
            if gaps.any():
                print(f"    terrain gaps -> {gaps.sum():,} px ({gaps.mean():.2%}), "
                      f"filled from the land around them")
                rgb = _inpaint(rgb, gaps)

        # Despill the coastline. Anti-aliasing mixes the painted sea into the
        # land pixel next to it, leaving a pink fringe that traces the whole
        # shore -- the pixel is opaque, so the key never touches it, but a third
        # of its colour came from the paint. Both red and blue standing above
        # green is the signature: terrain runs r > g > b, so nothing real here
        # reads that way, and pulling the two down to green's level takes the
        # paint back out without touching anything that was not tinted.
        rr, gg, bb = (rgb[:, :, i].astype(np.int16) for i in range(3))
        fringe = (alpha != 0) & (rr > gg + 8) & (bb > gg + 8)
        if fringe.any():
            # Two different fringes, and they need opposite treatment. The
            # water plane is a rectangle a little smaller than the frame, so
            # its edge runs through open water with painted sea on one side and
            # bare background on the other -- both keyed, leaving a hairline of
            # blend between them that belongs to neither. Desaturating that
            # line does not remove it, it just repaints it grey, which is the
            # rectangle traced across the finished map.
            #
            # Neighbours tell them apart. A pixel with transparency most of the
            # way round is floating in the sea and should go with it; one with
            # land behind it is real coast that merely caught some paint, and
            # only wants the paint taken back out.
            adrift = _strip_dark_slivers(alpha, rgb)
            fringe &= ~adrift
            print(f"    keyed {adrift.sum():,} px of blend adrift in the sea "
                  f"(the water plane's own edge), despilled {fringe.sum():,} "
                  f"px of coastline")
            rgb[:, :, 0] = np.where(fringe, np.minimum(rr, gg + 8), rr)
            rgb[:, :, 2] = np.where(fringe, np.minimum(bb, gg + 8), bb)
    else:
        if water:
            b, g, r = im[:, :, 2], im[:, :, 1], im[:, :, 0]
            wet = (b > g + 20) & (g > r + 20) & (r < 40)
            print(f"    water rule -> {wet.mean():6.2%} of the image")
            alpha[wet] = 0
        for i, t in enumerate([bg] + list(keys or [])):
            d = np.abs(im - np.array(t, dtype=np.int16)).sum(axis=2)
            hit = d < (tol if i == 0 else key_tol)
            alpha[hit] = 0
            print(f"    keyed {t} -> {hit.mean():6.2%} of the image")

    rgba = np.dstack([rgb, alpha])
    op = pathlib.Path(out)
    Image.fromarray(rgba, "RGBA").save(op)

    # A second copy over magenta, because the cutout ALONE cannot be checked.
    # Most viewers show transparency as white, and a hole punched in a pale
    # grey plateau then reads as sunlit rock -- the map looked perfect right up
    # until it was composited onto the blue sea and the same holes came back as
    # a bright blue ridge running over a mountain. Magenta is in nothing here,
    # so anything pink in the preview is a hole, and it shows at a glance.
    prev = op.with_name(op.stem + "_preview.png")
    pink = Image.new("RGB", (im.shape[1], im.shape[0]), (255, 0, 255))
    fg = Image.fromarray(rgba, "RGBA")
    pink.paste(fg, (0, 0), fg)
    pink.save(prev)
    h4, w4 = alpha.shape[0] // 4, alpha.shape[1] // 4
    inner = alpha[h4:-h4, w4:-w4] == 0
    print(f"  wrote {prev} - anything MAGENTA in it is a hole "
          f"({inner.mean():.2%} of the middle of the frame is)")
    if chroma is None and inner.mean() > 0.002:
        print(f"  WARNING: {inner.mean():.2%} of the MIDDLE of the frame was "
              f"keyed out, and the sea was guessed by colour rather than "
              f"painted. That is how shadowed slopes and gaps in the terrain "
              f"end up keyed with it. Set CHROMA_MATCHING in map.py instead.")
    print(f"  wrote {op} — {(alpha == 0).mean():.1%} transparent, "
          f"keyed on RGB{bg}")
    return 0


# The game's world map covers this world-space square. Recovered from
# script.js in this repo's first commits -- the original live map used it to
# place player markers, so it is the game's own transform rather than a guess.
#
#   537.109375 uu per pixel  =  (920000 - -1280000) / 4096
#
# Untested against the game itself. It predicts that 13 of the island's 35
# delivery points fall off the west and south edges of the map; opening the
# in-game map and looking for Braila Port confirms or kills it in one look.
MAP_MIN_X, MAP_MAX_X = -1280000.0, 920000.0
MAP_MIN_Y, MAP_MAX_Y = -320000.0, 1880000.0

# Does an increasing world Y move DOWN the texture, or up?
#
# DOWN, as script.js always had it. World (0,0) is the middle of Jeju, and Jeju
# sits at the TOP of the map -- Y-down puts (0,0) at pixel (2383, 596), Y-up
# puts it at (2383, 3500), near the bottom. The anchor decides it outright.
#
# This was briefly flipped on the reasoning that the bridge leaves Jeju's
# south-west, so the island ought to composite south-west. That was reading
# position off a bad extraction and inferring a transform from it; a known
# coordinate beats an impression of a picture.
MAP_Y_DOWN = True

# The two sea layers in the vanilla map, measured from the FModel export.
# They differ by 3 in green and nothing else, which is why the boundary reads
# as a faint border ring rather than a colour change:
#
#   SEA_INNER  (27, 56, 93)  #1B385D   37.8% of the map
#   SEA_OUTER  (27, 53, 93)  #1B355D   27.9%, and the colour of all four corners
#
# Flattening the outer to the inner removes that ring, so a composited island
# does not sit across a visible seam. SEA_INNER is also the colour to use for a
# water material that should blend into the vanilla map.
SEA_INNER = (27, 56, 93)
SEA_OUTER = (27, 53, 93)


def _default_base() -> pathlib.Path:
    """Find the FModel-exported PNG.

    FModel writes T_WorldMap_Jeju.png beside the .uasset, so wherever the user
    exported the game to already has it -- no extraction step, and one-to-one
    with what the game ships. Checked in order:

      MT_FMODEL_EXPORT   an export kept separately from the pipeline's content
      MTMI_GAME_CONTENT  when the pipeline reads the FModel export directly
      the repo           worldmap_vanilla.png, our own BC1 decode, last resort
    """
    # _cfg reads .env the same way every other script does; os.environ alone
    # misses it, because mt_paths parses .env into its own values rather than
    # exporting them into the process environment.
    from mt_paths import _cfg
    for root in (_cfg("MT_FMODEL_EXPORT").strip().strip('"'),
                 str(GAME_CONTENT)):
        if not root:
            continue
        cand = pathlib.Path(root) / f"{REL}.png"
        if cand.is_file():
            return cand
    return pathlib.Path("worldmap_vanilla.png")


def compose(island: str = "static_meshes_parts/map_cutout.png",
            base: str | None = None,
            out: str = "T_WorldMap_Jeju.png",
            flatten_sea: bool = True) -> int:
    """Paste the island onto the vanilla map, keeping the VANILLA world rect.

    Output is named T_WorldMap_Jeju.png, ready to cook straight over the
    original -- and unlike `expand`, it needs nothing changed inside the game.
    The game converts world positions to map pixels with its own bounds; this
    keeps those bounds valid, so markers stay correct. The cost is that the
    parts of the island outside the vanilla rectangle cannot be shown.

    Use `expand` only once the game's own bounds can be moved to match."""
    """Paste the cut-out island onto the vanilla world map, in the right place.

    Position comes from arithmetic, not eyeballing: map_bounds.json records the
    EDITOR rectangle the capture covers, mt_paths supplies the import offset the
    pipeline shifts everything by, and the constants above turn world
    coordinates into map pixels. Every step is a number we already know.
    """
    try:
        import numpy as np
        from PIL import Image
        # These images are deliberately enormous -- a 16384 map is 268 MPx --
        # and Pillow's decompression-bomb guard is aimed at untrusted input,
        # not at a file this pipeline just wrote.
        Image.MAX_IMAGE_PIXELS = None
    except ImportError as e:
        print(f"  needs numpy and Pillow: {e}", file=sys.stderr)
        return 1
    import json
    from mt_paths import (IMPORT_OFFSET_X as OX, IMPORT_OFFSET_Y as OY)

    ip = pathlib.Path(island)
    bp = pathlib.Path(base) if base else _default_base()
    bounds_p = ip.with_name("map_bounds.json")
    for pth, what in ((ip, "run map.py then `worldmap.py cutout --water`"),
                      (bp, "export the game with FModel — T_WorldMap_Jeju.png "
                           "lands beside the .uasset in MTMI_GAME_CONTENT"),
                      (bounds_p, "run map.py")):
        if not pth.is_file():
            print(f"  missing {pth} - {what}", file=sys.stderr)
            return 1

    b = json.loads(bounds_p.read_text(encoding="utf-8"))
    # Editor -> world. The capture is authored in editor space; the pipeline
    # shifts the whole island by this offset when it injects it into Jeju, so
    # the map has to use the shifted coordinates, not the ones in the editor.
    wx0, wx1 = b["min_x"] + OX, b["max_x"] + OX
    wy0, wy1 = b["min_y"] + OY, b["max_y"] + OY

    base_img = Image.open(bp).convert("RGBA")
    if flatten_sea:
        arr = np.array(base_img)
        hit = (np.abs(arr[:, :, :3].astype(np.int16)
                      - np.array(SEA_OUTER, dtype=np.int16)).sum(axis=2) < 6)
        arr[hit, :3] = SEA_INNER
        base_img = Image.fromarray(arr, "RGBA")
        print(f"  flattened {hit.mean():.1%} of deep sea {SEA_OUTER} -> {SEA_INNER}")
    W, H = base_img.size
    sx = W / (MAP_MAX_X - MAP_MIN_X)
    sy = H / (MAP_MAX_Y - MAP_MIN_Y)
    px0 = (wx0 - MAP_MIN_X) * sx
    px1 = (wx1 - MAP_MIN_X) * sx
    if MAP_Y_DOWN:
        py0 = (wy0 - MAP_MIN_Y) * sy
        py1 = (wy1 - MAP_MIN_Y) * sy
    else:
        py0 = (MAP_MAX_Y - wy1) * sy
        py1 = (MAP_MAX_Y - wy0) * sy
    tw, th = int(round(px1 - px0)), int(round(py1 - py0))
    print(f"  island covers world X {wx0:.0f}..{wx1:.0f}  Y {wy0:.0f}..{wy1:.0f}")
    print(f"  -> map pixels x {px0:.0f}..{px1:.0f}  y {py0:.0f}..{py1:.0f}  ({tw}x{th})")

    if tw <= 0 or th <= 0:
        print("  degenerate target rectangle - check map_bounds.json", file=sys.stderr)
        return 1
    off_l, off_t = max(0, -int(px0)), max(0, -int(py0))
    off_r, off_b = max(0, int(px1) - W), max(0, int(py1) - H)
    if off_l or off_t or off_r or off_b:
        print(f"  WARNING: the island runs off the map by "
              f"left {off_l}px top {off_t}px right {off_r}px bottom {off_b}px. "
              f"Those parts cannot be shown - the game's map does not reach "
              f"that far. Everything on-map still composites.")

    isl = Image.open(ip).convert("RGBA")
    src_w, src_h = isl.size
    scale = tw / src_w
    print(f"  island render is {src_w}x{src_h}, scaling by {scale:.3f}"
          + ("  (near 1.0 means the capture already matched the map scale)"
             if 0.9 < scale < 1.11 else
             "  <- far from 1.0: set MATCH_GAME_SCALE in map.py for a sharp result"))
    isl = isl.resize((tw, th), Image.LANCZOS)

    out_img = base_img.copy()
    out_img.alpha_composite(isl, dest=(int(round(px0)), int(round(py0))))
    op = pathlib.Path(out)
    out_img.convert("RGB").save(op)
    print(f"  wrote {op} ({W}x{H})")
    return 0


def expand(island: str = "static_meshes_parts/map_cutout.png",
           base: str | None = None,
           out_dir: str = ".",
           size: int | None = None,
           flatten_sea: bool = True) -> int:
    """Build a world map big enough for the island, and the bounds to match.

    The vanilla map covers a fixed 22 km square and the island does not fit in
    it -- roughly 6 km hangs off the west edge and 4 km off the north. Rather
    than crop the island to the game's rectangle, this grows the rectangle.

    Two things come out, and BOTH are needed:

      T_WorldMap_Jeju.png   the image, under the game's own name so it can be
                            cooked straight over the original
      worldmap_bounds.json  the world rectangle the new image covers

    The image alone is not enough. The game converts a world position into a
    map pixel using the OLD rectangle, so a wider image with unchanged bounds
    would show the island in the right place and put every marker in the wrong
    one. Whatever holds those bounds in the game has to be moved to match, and
    the JSON is what tells that step where to.

    Resolution defaults to the smallest power of two that keeps the vanilla
    pixel density or better, so nothing already on the map gets softer than it
    was.
    """
    try:
        import numpy as np
        from PIL import Image
        # These images are deliberately enormous -- a 16384 map is 268 MPx --
        # and Pillow's decompression-bomb guard is aimed at untrusted input,
        # not at a file this pipeline just wrote.
        Image.MAX_IMAGE_PIXELS = None
    except ImportError as e:
        print(f"  needs numpy and Pillow: {e}", file=sys.stderr)
        return 1
    import json
    from mt_paths import IMPORT_OFFSET_X as OX, IMPORT_OFFSET_Y as OY

    ip = pathlib.Path(island)
    bp = pathlib.Path(base) if base else _default_base()
    bounds_p = ip.with_name("map_bounds.json")
    for pth, what in ((ip, "run map.py then `worldmap.py cutout --water`"),
                      (bp, "export the game with FModel"),
                      (bounds_p, "run map.py")):
        if not pth.is_file():
            print(f"  missing {pth} - {what}", file=sys.stderr)
            return 1

    b = json.loads(bounds_p.read_text(encoding="utf-8"))
    iw0, iw1 = b["min_x"] + OX, b["max_x"] + OX
    ih0, ih1 = b["min_y"] + OY, b["max_y"] + OY

    # Union of the vanilla rectangle and the island, then squared. A
    # non-square world rect in a square texture stretches every coordinate
    # derived from it.
    nx0, nx1 = min(MAP_MIN_X, iw0), max(MAP_MAX_X, iw1)
    ny0, ny1 = min(MAP_MIN_Y, ih0), max(MAP_MAX_Y, ih1)
    span = max(nx1 - nx0, ny1 - ny0)
    cx, cy = (nx0 + nx1) / 2.0, (ny0 + ny1) / 2.0
    nx0, nx1 = cx - span / 2.0, cx + span / 2.0
    ny0, ny1 = cy - span / 2.0, cy + span / 2.0

    old_span = MAP_MAX_X - MAP_MIN_X
    base_img = Image.open(bp).convert("RGBA")
    W, _ = base_img.size
    old_uu_px = old_span / W

    if size is None:
        # Keep at least the vanilla density: enough pixels that one covers no
        # more world than it used to. Rounded up to a power of two, because a
        # texture that is not one loses mips and some tooling refuses it.
        need = span / old_uu_px
        size = 1 << (int(need - 1).bit_length())
        size = max(W, min(size, 16384))
        # MTMI_MAP_SCALE raises the CAPTURE resolution; without matching it
        # here the extra detail is thrown away on the way in, since the island
        # is scaled to fit whatever this size implies. Same multiplier, so one
        # setting governs the whole chain.
        try:
            from mt_paths import _cfg
            mul = float(_cfg("MTMI_MAP_SCALE", "1") or 1)
        except Exception:
            mul = 1.0
        if mul > 1:
            scaled = 1 << (int(size * mul - 1).bit_length())
            size = min(scaled, 16384)
            print(f"  MTMI_MAP_SCALE={mul:g} -> {size} px texture")
    uu_px = span / size
    print(f"  vanilla: {old_span/100000:.1f} km over {W} px = {old_uu_px:.1f} uu/px")
    print(f"  expanded: {span/100000:.1f} km over {size} px = {uu_px:.1f} uu/px"
          + ("  (finer)" if uu_px < old_uu_px else "  (COARSER - raise size)"))

    if flatten_sea:
        arr = np.array(base_img)
        hit = (np.abs(arr[:, :, :3].astype(np.int16)
                      - np.array(SEA_OUTER, dtype=np.int16)).sum(axis=2) < 6)
        arr[hit, :3] = SEA_INNER
        base_img = Image.fromarray(arr, "RGBA")
        print(f"  flattened {hit.mean():.1%} of the deep sea")

    # Fill with sea, so the newly exposed area is not a black or white void.
    canvas = Image.new("RGBA", (size, size), SEA_INNER + (255,))

    def to_px(wx, wy):
        px = (wx - nx0) / uu_px
        py = (wy - ny0) / uu_px if MAP_Y_DOWN else (ny1 - wy) / uu_px
        return px, py

    # Place the vanilla map into its own corner of the bigger rectangle.
    vx0, vy_a = to_px(MAP_MIN_X, MAP_MIN_Y if MAP_Y_DOWN else MAP_MAX_Y)
    vx1, vy_b = to_px(MAP_MAX_X, MAP_MAX_Y if MAP_Y_DOWN else MAP_MIN_Y)
    vw, vh = int(round(vx1 - vx0)), int(round(vy_b - vy_a))
    canvas.alpha_composite(base_img.resize((vw, vh), Image.LANCZOS),
                           dest=(int(round(vx0)), int(round(vy_a))))
    print(f"  vanilla map placed at ({vx0:.0f},{vy_a:.0f}) size {vw}x{vh}")

    # Then the island on top.
    ix0, iy_a = to_px(iw0, ih0 if MAP_Y_DOWN else ih1)
    ix1, iy_b = to_px(iw1, ih1 if MAP_Y_DOWN else ih0)
    iw, ih = int(round(ix1 - ix0)), int(round(iy_b - iy_a))
    isl = Image.open(ip).convert("RGBA")
    canvas.alpha_composite(isl.resize((iw, ih), Image.LANCZOS),
                           dest=(int(round(ix0)), int(round(iy_a))))
    print(f"  island placed at ({ix0:.0f},{iy_a:.0f}) size {iw}x{ih}"
          f"  (render was {isl.size[0]}px, scaling {iw/isl.size[0]:.3f})")

    od = pathlib.Path(out_dir)
    od.mkdir(parents=True, exist_ok=True)
    # The game's own name, so it can be cooked straight over the original with
    # nothing to rename. It carried a _do_not_cook_yet suffix while the game's
    # bounds still described the old 22 km square: an expanded image imported
    # against those is indistinguishable from a working map until you notice
    # every road is subtly out of place. set-worldmap moves them now, so the
    # suffix only stood between a finished image and the cooker. The numbers
    # that have to match are printed below instead, which is the part that
    # actually protects anything.
    img_out = od / "T_WorldMap_Jeju.png"
    canvas.convert("RGB").save(img_out)

    meta = {
        "image": img_out.name,
        "size_px": size,
        "min_x": nx0, "max_x": nx1,
        "min_y": ny0, "max_y": ny1,
        "uu_per_px": uu_px,
        "y_down": MAP_Y_DOWN,
        "vanilla": {"min_x": MAP_MIN_X, "max_x": MAP_MAX_X,
                    "min_y": MAP_MIN_Y, "max_y": MAP_MAX_Y,
                    "size_px": W, "uu_per_px": old_uu_px},
        "_note": [
            "The game maps a world position to a map pixel using ITS OWN copy",
            "of these bounds. Shipping this image without moving those bounds",
            "puts the island in the right place and every marker in the wrong",
            "one -- so this file is an instruction for that step, not a record.",
            "set-worldmap takes the centre and size, not the four corners.",
            "world_to_pixel: px = (X - min_x) / uu_per_px",
            "                py = (Y - min_y) / uu_per_px   when y_down",
        ],
    }
    meta_out = od / "worldmap_bounds.json"
    meta_out.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"  wrote {img_out} ({size}x{size}) and {meta_out.name}")
    print(f"  new world rect: X {nx0:.0f}..{nx1:.0f}  Y {ny0:.0f}..{ny1:.0f}")
    print(f"  cook it as T_WorldMap_Jeju, with AddressX/Y = TA_Clamp and "
          f"SRGB = False")
    print(f"  the game's bounds MUST match this image, or every road and marker "
          f"lands slightly wrong:")
    print(f"    MTBPInjector set-worldmap --center-x {(nx0+nx1)/2:.0f} "
          f"--center-y {(ny0+ny1)/2:.0f} --size {span:.0f}")
    return 0


def build(**kw) -> int:
    """cutout then expand, so one command turns a fresh capture into the
    texture to cook.

    They were always run back to back and there is nothing to decide between
    them: cutout keys the render map.py just wrote, expand pastes the result
    onto the game's map and prints what the game's bounds must be set to. Two
    commands only ever meant two chances to run one and forget the other, and
    a stale cutout is invisible -- the expand succeeds and quietly composites
    the previous capture.
    """
    rc = cutout(water=kw.get("water", False))
    if rc != 0:
        return rc
    print()
    return expand(base=kw.get("base"), size=kw.get("size"),
                  flatten_sea=kw.get("flatten_sea", True))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["extract", "cutout", "compose", "expand", "build"])
    ap.add_argument("--mod", action="store_true",
                    help="read the copy our pak ships instead of vanilla")
    ap.add_argument("-o", "--out", default="worldmap_vanilla.png")
    ap.add_argument("--size", type=int, default=None,
                    help="expand: output resolution. Default is the smallest "
                         "power of two that keeps the vanilla pixel density.")
    ap.add_argument("--keep-sea-border", action="store_true",
                    help="leave the vanilla map's two-tone sea alone. By "
                         "default the darker outer ring is flattened to the "
                         "inner shade so a composited island sits on one "
                         "continuous sea instead of across a seam.")
    ap.add_argument("--base", default=None,
                    help="the vanilla map PNG. Defaults to the FModel export "
                         "beside the .uasset in MTMI_GAME_CONTENT, which is "
                         "one-to-one with what the game ships. The built-in "
                         "BC1 decode (`extract`) is a fallback and its colours "
                         "are not trustworthy.")
    ap.add_argument("--water", action="store_true",
                    help="also key LIT water, by colour shape rather than an "
                         "exact value: blue > green > red with red near zero. "
                         "Use when the sea reflects the sky and no single "
                         "colour can be keyed.")
    ap.add_argument("--tol", type=int, default=30,
                    help="tolerance for the auto-detected background (default 30)")
    ap.add_argument("--key-tol", type=int, default=12,
                    help="tolerance for each --key colour (default 12). A FLAT "
                         "unlit material needs no more than this; a lit surface "
                         "spans dozens of shades and no tolerance rescues it "
                         "without eating real pixels.")
    ap.add_argument("--key", action="append", metavar="RRGGBB",
                    help="also key this exact colour to transparent. Repeatable. "
                         "Use it for a flat unlit water material.")
    args = ap.parse_args()

    if args.action == "build":
        return build(water=args.water, base=args.base, size=args.size,
                     flatten_sea=not args.keep_sea_border)

    if args.action == "expand":
        return expand(base=args.base, size=args.size,
                      flatten_sea=not args.keep_sea_border)

    if args.action == "compose":
        return compose(base=args.base, flatten_sea=not args.keep_sea_border)

    if args.action == "cutout":
        keys = []
        for h in (args.key or []):
            h = h.lstrip("#")
            if len(h) != 6:
                print(f"  --key expects RRGGBB, got '{h}'", file=sys.stderr)
                return 1
            keys.append(tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)))
        return cutout(keys=keys, tol=args.tol, key_tol=args.key_tol,
                      water=args.water)

    if args.mod:
        src = pathlib.Path(MOD_CONTENT_ROOT) / f"{REL}.uexp"
        if not src.is_file():
            print(f"  our pak ships no world map yet ({src})", file=sys.stderr)
            return 1
    else:
        src = pathlib.Path(effective_asset(f"{REL}.uasset")).with_suffix(".uexp")
    print(f"  reading {src}")
    _, payload, _ = _split(src.read_bytes())

    try:
        import numpy as np              # noqa: F401
        from PIL import Image
        # These images are deliberately enormous -- a 16384 map is 268 MPx --
        # and Pillow's decompression-bomb guard is aimed at untrusted input,
        # not at a file this pipeline just wrote.
        Image.MAX_IMAGE_PIXELS = None
    except ImportError as e:
        print(f"  needs numpy and Pillow: {e}", file=sys.stderr)
        return 1

    img = decode_bc1(payload)
    out = pathlib.Path(args.out)
    Image.fromarray(img, "RGB").save(out)
    print(f"  wrote {out} ({SIZE}x{SIZE})")

    # A quick read on what is actually in there, so an all-ocean or all-black
    # extraction is obvious immediately rather than after an hour of alignment.
    import numpy as np
    flat = img.reshape(-1, 3)
    uniq = len(np.unique(flat[::997], axis=0))
    print(f"  {uniq} distinct colours in a sample — mean RGB "
          f"{tuple(int(v) for v in flat.mean(axis=0))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
