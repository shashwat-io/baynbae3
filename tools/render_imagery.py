#!/usr/bin/env python3
"""
Generates every image the storefront uses, in the two brand colours only.

    python tools/render_imagery.py

Writes SVGs to static/img/products/ and static/img/editorial/, plus a
favicon and a PNG social card (pure-Python PNG writer, no Pillow needed).
Idempotent — safe to run on every fresh clone.
"""
import math
import struct
import zlib
from pathlib import Path

BLUE = "#3B63FF"
CREAM = "#F6F5EA"
ROOT = Path(__file__).resolve().parent.parent / "static" / "img"
PRODUCTS = ROOT / "products"
EDITORIAL = ROOT / "editorial"

W, H = 800, 1000  # product canvas


# ------------------------------------------------------------------ prints
def pattern(pid, kind, ink, bg, scale=1.0):
    """Return a <pattern> element. `ink` draws the motif over a solid `bg`."""
    s = scale
    if kind == "solid":
        return f'<pattern id="{pid}" width="10" height="10" patternUnits="userSpaceOnUse"><rect width="10" height="10" fill="{bg}"/></pattern>'
    if kind == "stripe":
        t = 44 * s
        return (
            f'<pattern id="{pid}" width="{t}" height="{t}" patternUnits="userSpaceOnUse">'
            f'<rect width="{t}" height="{t}" fill="{bg}"/>'
            f'<rect width="{t}" height="{14 * s}" y="{6 * s}" fill="{ink}"/></pattern>'
        )
    if kind == "wave":
        tw, th = 96 * s, 48 * s
        return (
            f'<pattern id="{pid}" width="{tw}" height="{th}" patternUnits="userSpaceOnUse">'
            f'<rect width="{tw}" height="{th}" fill="{bg}"/>'
            f'<path d="M0,{24 * s} q{24 * s},{-22 * s} {48 * s},0 t{48 * s},0" fill="none" stroke="{ink}" stroke-width="{6 * s}" stroke-linecap="round"/></pattern>'
        )
    if kind == "dot":
        t = 56 * s
        return (
            f'<pattern id="{pid}" width="{t}" height="{t}" patternUnits="userSpaceOnUse">'
            f'<rect width="{t}" height="{t}" fill="{bg}"/>'
            f'<circle cx="{14 * s}" cy="{14 * s}" r="{7 * s}" fill="{ink}"/>'
            f'<circle cx="{42 * s}" cy="{42 * s}" r="{7 * s}" fill="{ink}"/></pattern>'
        )
    if kind == "palm":
        t = 150 * s
        leaves = ""
        for i, (cy, rx, ang) in enumerate([(40, 34, -55), (60, 40, -40), (80, 44, -25), (100, 40, -12)]):
            for side in (-1, 1):
                leaves += (
                    f'<ellipse cx="{(75 + side * rx * 0.55) * s}" cy="{cy * s}" rx="{rx * s * 0.62}" ry="{7 * s}" '
                    f'fill="{ink}" transform="rotate({side * ang} {(75 + side * rx * 0.55) * s} {cy * s})"/>'
                )
        return (
            f'<pattern id="{pid}" width="{t}" height="{t}" patternUnits="userSpaceOnUse" patternTransform="rotate(18)">'
            f'<rect width="{t}" height="{t}" fill="{bg}"/>'
            f'<path d="M{75 * s},{130 * s} C{75 * s},{90 * s} {75 * s},{60 * s} {75 * s},{22 * s}" stroke="{ink}" stroke-width="{4 * s}" fill="none" stroke-linecap="round"/>'
            f"{leaves}</pattern>"
        )
    if kind == "gingham":
        t = 48 * s
        return (
            f'<pattern id="{pid}" width="{t}" height="{t}" patternUnits="userSpaceOnUse">'
            f'<rect width="{t}" height="{t}" fill="{bg}"/>'
            f'<rect width="{24 * s}" height="{t}" fill="{ink}" opacity="0.45"/>'
            f'<rect width="{t}" height="{24 * s}" fill="{ink}" opacity="0.45"/></pattern>'
        )
    if kind == "scallop":
        tw, th = 64 * s, 32 * s
        return (
            f'<pattern id="{pid}" width="{tw}" height="{th}" patternUnits="userSpaceOnUse">'
            f'<rect width="{tw}" height="{th}" fill="{bg}"/>'
            f'<path d="M0,{32 * s} a{16 * s},{16 * s} 0 0 1 {32 * s},0 a{16 * s},{16 * s} 0 0 1 {32 * s},0" fill="none" stroke="{ink}" stroke-width="{4 * s}"/>'
            f'<path d="M{-16 * s},{16 * s} a{16 * s},{16 * s} 0 0 1 {32 * s},0 a{16 * s},{16 * s} 0 0 1 {32 * s},0 a{16 * s},{16 * s} 0 0 1 {32 * s},0" fill="none" stroke="{ink}" stroke-width="{4 * s}"/></pattern>'
        )
    if kind == "zigzag":
        tw, th = 72 * s, 36 * s
        return (
            f'<pattern id="{pid}" width="{tw}" height="{th}" patternUnits="userSpaceOnUse">'
            f'<rect width="{tw}" height="{th}" fill="{bg}"/>'
            f'<path d="M0,{26 * s} L{18 * s},{10 * s} L{36 * s},{26 * s} L{54 * s},{10 * s} L{72 * s},{26 * s}" fill="none" stroke="{ink}" stroke-width="{5 * s}" stroke-linejoin="round"/></pattern>'
        )
    if kind == "sun":
        t = 120 * s
        rays = ""
        for k in range(8):
            a = math.radians(k * 45)
            x1, y1 = 60 * s + math.cos(a) * 18 * s, 60 * s + math.sin(a) * 18 * s
            x2, y2 = 60 * s + math.cos(a) * 30 * s, 60 * s + math.sin(a) * 30 * s
            rays += f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{ink}" stroke-width="{4 * s}" stroke-linecap="round"/>'
        return (
            f'<pattern id="{pid}" width="{t}" height="{t}" patternUnits="userSpaceOnUse">'
            f'<rect width="{t}" height="{t}" fill="{bg}"/>'
            f'<circle cx="{60 * s}" cy="{60 * s}" r="{11 * s}" fill="{ink}"/>{rays}'
            f'<circle cx="{4 * s}" cy="{4 * s}" r="{4 * s}" fill="{ink}"/><circle cx="{116 * s}" cy="{116 * s}" r="{4 * s}" fill="{ink}"/></pattern>'
        )
    if kind == "floral":
        t = 84 * s

        def flower(cx, cy, r):
            out = ""
            for k in range(5):
                a = math.radians(k * 72 - 90)
                out += f'<circle cx="{cx + math.cos(a) * r * 1.35:.1f}" cy="{cy + math.sin(a) * r * 1.35:.1f}" r="{r:.1f}" fill="{ink}"/>'
            out += f'<circle cx="{cx}" cy="{cy}" r="{r * 0.75:.1f}" fill="{bg}"/>'
            return out

        return (
            f'<pattern id="{pid}" width="{t}" height="{t}" patternUnits="userSpaceOnUse">'
            f'<rect width="{t}" height="{t}" fill="{bg}"/>'
            f"{flower(21 * s, 21 * s, 5.5 * s)}{flower(63 * s, 63 * s, 5.5 * s)}"
            f'<circle cx="{63 * s}" cy="{21 * s}" r="{2.5 * s}" fill="{ink}"/><circle cx="{21 * s}" cy="{63 * s}" r="{2.5 * s}" fill="{ink}"/></pattern>'
        )
    if kind == "diamond":
        t = 52 * s
        return (
            f'<pattern id="{pid}" width="{t}" height="{t}" patternUnits="userSpaceOnUse">'
            f'<rect width="{t}" height="{t}" fill="{bg}"/>'
            f'<polygon points="{26 * s},{4 * s} {44 * s},{26 * s} {26 * s},{48 * s} {8 * s},{26 * s}" fill="none" stroke="{ink}" stroke-width="{4 * s}" stroke-linejoin="round"/>'
            f'<circle cx="{26 * s}" cy="{26 * s}" r="{4 * s}" fill="{ink}"/></pattern>'
        )
    raise ValueError(kind)


# -------------------------------------------------------------- silhouettes
# Each returns a list of (path_d, role) where role in {"body", "trim", "detail"}.
# Coordinates are on the 800x1000 canvas, garment centred at x=400.
def kaftan(back=False):
    body = (
        "M352,178 L118,330 L150,428 L290,414 L206,884 L594,884 L510,414 L650,428 L682,330 L448,178 "
        "L400,300 Z" if not back else
        "M352,178 L118,330 L150,428 L290,414 L206,884 L594,884 L510,414 L650,428 L682,330 L448,178 Q400,210 352,178 Z"
    )
    parts = [(body, "body")]
    if not back:
        parts.append(("M352,178 L400,300 L448,178", "trim"))  # V-neck band
        parts.append(("M378,300 L400,340 L422,300", "detail"))  # tie loop
        parts.append(("M392,340 L384,392 M408,340 L416,392", "detail"))  # tassels
    parts.append(("M214,860 L586,860", "detail"))  # hem line
    return parts


def coverup(back=False):
    body = "M356,176 L114,326 L146,434 L296,418 L262,872 L538,872 L504,418 L654,434 L686,326 L444,176 Q400,200 356,176 Z"
    parts = [(body, "body")]
    if not back:
        parts.append(("M386,206 L366,872 L434,872 L414,206 Z", "gap"))  # open front shows cream
        parts.append(("M386,206 L366,872 M414,206 L434,872", "trim"))
        parts.append(("M300,540 L330,540 M470,540 L500,540", "detail"))  # belt loops
    return parts


def slip_dress(back=False):
    body = (
        "M332,300 Q400,340 468,300 L462,332 Q470,400 452,446 Q560,640 548,904 L252,904 Q240,640 348,446 Q330,400 338,332 Z"
        if not back else
        "M332,300 L468,300 L462,332 Q470,400 452,446 Q560,640 548,904 L252,904 Q240,640 348,446 Q330,400 338,332 Z"
    )
    parts = [(body, "body")]
    parts.append(("M346,300 L352,186 M454,300 L448,186", "strap"))
    if not back:
        parts.append(("M348,446 Q400,470 452,446", "detail"))
    return parts


def tiered_dress(back=False):
    parts = []
    parts.append(("M336,252 Q296,262 282,340 L336,340 Z", "body"))  # cap sleeve L
    parts.append(("M464,252 Q504,262 518,340 L464,340 Z", "body"))  # cap sleeve R
    if not back:
        parts.append(("M336,252 Q400,300 464,252 L458,300 Q470,380 448,428 L352,428 Q330,380 342,300 Z", "body"))
    else:
        parts.append(("M336,252 Q400,236 464,252 L458,300 Q470,380 448,428 L352,428 Q330,380 342,300 Z", "body"))
    parts.append(("M352,428 L448,428 Q470,440 452,448 L348,448 Q330,440 352,428 Z", "trim"))  # waistband
    parts.append(("M348,448 L452,448 Q500,600 510,620 L290,620 Q300,600 348,448 Z", "body"))
    parts.append(("M290,620 L510,620 Q548,760 556,780 L244,780 Q252,760 290,620 Z", "body"))
    parts.append(("M244,780 L556,780 Q590,900 596,910 L204,910 Q210,900 244,780 Z", "body"))
    parts.append(("M290,620 L510,620 M244,780 L556,780", "detail"))
    return parts


def coord(back=False):
    parts = []
    top = "M330,226 L470,226 Q540,236 552,320 L512,330 L508,412 L292,412 L288,330 L248,320 Q260,236 330,226 Z"
    parts.append((top, "body"))
    if not back:
        parts.append(("M370,226 Q400,262 430,226", "trim"))
        parts.append(("M400,262 L400,412", "detail"))
        parts.append(("M400,300 m-4,0 a4,4 0 1,0 8,0 a4,4 0 1,0 -8,0 M400,350 m-4,0 a4,4 0 1,0 8,0 a4,4 0 1,0 -8,0", "trim"))
    parts.append(("M292,412 L508,412", "detail"))
    pants = "M322,446 L478,446 L536,916 L412,916 L400,620 L388,916 L264,916 Z"
    parts.append((pants, "body"))
    parts.append(("M322,446 L478,446 L482,470 L318,470 Z", "trim"))
    return parts


def shorts_set(back=False):
    parts = []
    shirt = "M318,214 L482,214 Q556,226 570,326 L522,338 L516,530 L284,530 L278,338 L230,326 Q244,226 318,214 Z"
    parts.append((shirt, "body"))
    if not back:
        parts.append(("M366,214 L400,268 L434,214 L418,196 L400,232 L382,196 Z", "trim"))  # collar
        parts.append(("M400,268 L400,530", "detail"))
        parts.append(("M400,320 m-4,0 a4,4 0 1,0 8,0 a4,4 0 1,0 -8,0 M400,380 m-4,0 a4,4 0 1,0 8,0 a4,4 0 1,0 -8,0 M400,440 m-4,0 a4,4 0 1,0 8,0 a4,4 0 1,0 -8,0", "trim"))
        parts.append(("M440,300 L500,300 L500,350 L440,350 Z", "detail"))  # pocket
    else:
        parts.append(("M366,214 Q400,236 434,214", "trim"))
    parts.append(("M522,338 L516,346 M278,338 L284,346", "detail"))
    shorts = "M318,562 L482,562 L512,776 L412,776 L400,690 L388,776 L288,776 Z"
    parts.append((shorts, "body"))
    parts.append(("M318,562 L482,562 L485,584 L315,584 Z", "trim"))
    return parts


SILHOUETTES = {
    "kaftan": kaftan,
    "coverup": coverup,
    "slip": slip_dress,
    "tiered": tiered_dress,
    "coord": coord,
    "shorts": shorts_set,
}


# ------------------------------------------------------------ compositions
def svg(w, h, body, title):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{title}">'
        f"{body}</svg>\n"
    )


def garment_group(parts, fill, ink, bg, stroke=True, opacity_line=1.0):
    out = ""
    for d, role in parts:
        if role == "body":
            out += f'<path d="{d}" fill="{fill}" stroke="{ink}" stroke-width="{3 if stroke else 0}" stroke-linejoin="round"/>'
        elif role == "gap":
            out += f'<path d="{d}" fill="{bg}"/>'
        elif role == "trim":
            out += f'<path d="{d}" fill="{ink}" fill-opacity="0.9" stroke="{ink}" stroke-width="3" stroke-linejoin="round"/>'
        elif role == "strap":
            out += f'<path d="{d}" fill="none" stroke="{ink}" stroke-width="5" stroke-linecap="round"/>'
        else:  # detail
            out += f'<path d="{d}" fill="none" stroke="{ink}" stroke-width="3" stroke-linecap="round" opacity="{opacity_line}"/>'
    return out


def product_front(slug, shape, print_kind, inverted):
    """Front view. inverted=False: blue print on cream garment; True: cream print on blue garment."""
    ink, base = (CREAM, BLUE) if inverted else (BLUE, CREAM)
    parts = SILHOUETTES[shape]()
    pid = f"p-{slug}"
    defs = f"<defs>{pattern(pid, print_kind, ink, base)}</defs>"
    fill = f"url(#{pid})"
    line_ink = BLUE  # outlines are always blue so cream garments read on cream
    shadow = "".join(f'<path d="{d}" fill="{BLUE}" opacity="0.14"/>' for d, role in parts if role == "body")
    body = (
        f'<rect width="{W}" height="{H}" fill="{CREAM}"/>'
        f'<path d="M180,940 L180,320 A220,220 0 0 1 620,320 L620,940 Z" fill="{BLUE}" opacity="0.09"/>'
        f'<g transform="translate(10,14)">{shadow}</g>'
        f"{garment_group(parts, fill, line_ink, CREAM, stroke=True)}"
        f'<line x1="120" y1="940" x2="680" y2="940" stroke="{BLUE}" stroke-width="3" opacity="0.5"/>'
    )
    return svg(W, H, defs + body, f"{slug} front")


def product_detail(slug, print_kind, inverted):
    ink, base = (CREAM, BLUE) if inverted else (BLUE, CREAM)
    pid = f"d-{slug}"
    defs = f"<defs>{pattern(pid, print_kind, ink, base, scale=2.6)}</defs>"
    body = (
        f'<rect width="{W}" height="{H}" fill="{base}"/>'
        f'<rect width="{W}" height="{H}" fill="url(#{pid})" transform="rotate(-8 400 500) scale(1.25)"/>'
        # a swing tag in the corner, tied with a thread
        f'<path d="M560,760 q40,-60 80,-20" fill="none" stroke="{ink}" stroke-width="3"/>'
        f'<rect x="600" y="740" width="150" height="90" rx="6" fill="{CREAM}" stroke="{BLUE}" stroke-width="3" transform="rotate(-12 675 785)"/>'
        f'<circle cx="622" cy="770" r="5" fill="{BLUE}" transform="rotate(-12 675 785)"/>'
        f'<rect x="640" y="768" width="86" height="8" rx="4" fill="{BLUE}" transform="rotate(-12 675 785)"/>'
        f'<rect x="640" y="788" width="60" height="8" rx="4" fill="{BLUE}" opacity="0.5" transform="rotate(-12 675 785)"/>'
        f'<rect x="640" y="806" width="72" height="8" rx="4" fill="{BLUE}" opacity="0.5" transform="rotate(-12 675 785)"/>'
    )
    return svg(W, H, defs + body, f"{slug} print close-up")


def product_back(slug, shape, print_kind, inverted):
    """Back view on a blue ground with the garment flipped to cream-on-blue tones."""
    ink, base = (BLUE, CREAM) if inverted else (CREAM, BLUE)
    parts = SILHOUETTES[shape](back=True)
    pid = f"b-{slug}"
    defs = f"<defs>{pattern(pid, print_kind, ink, base)}</defs>"
    shadow = "".join(f'<path d="{d}" fill="#000" opacity="0.18"/>' for d, role in parts if role == "body")
    body = (
        f'<rect width="{W}" height="{H}" fill="{BLUE}"/>'
        f'<circle cx="400" cy="420" r="300" fill="{CREAM}" opacity="0.12"/>'
        f'<g transform="translate(12,14)">{shadow}</g>'
        f"{garment_group(parts, f'url(#{pid})', CREAM, BLUE, stroke=True)}"
    )
    return svg(W, H, defs + body, f"{slug} back")


# ----------------------------------------------------------- editorial art
def sun(cx, cy, r, colour, rays=12, ray_len=0.45, width=6):
    out = f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{colour}"/>'
    for k in range(rays):
        a = math.radians(k * 360 / rays)
        x1, y1 = cx + math.cos(a) * r * 1.25, cy + math.sin(a) * r * 1.25
        x2, y2 = cx + math.cos(a) * r * (1.25 + ray_len), cy + math.sin(a) * r * (1.25 + ray_len)
        out += f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{colour}" stroke-width="{width}" stroke-linecap="round"/>'
    return out


def waves(y0, w, colour, rows=5, gap=34, amp=16, width=6, opacity=1.0):
    out = ""
    for i in range(rows):
        y = y0 + i * gap
        d = f"M-40,{y} " + " ".join(f"q40,{-amp} 80,0 t80,0" for _ in range(w // 160 + 2))
        out += f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="{width}" stroke-linecap="round" opacity="{opacity}"/>'
    return out


def palm_tree(x, y, h, colour, lean=0):
    trunk = f'<path d="M{x},{y} Q{x + lean},{y - h * 0.5} {x + lean * 1.6},{y - h}" fill="none" stroke="{colour}" stroke-width="10" stroke-linecap="round"/>'
    tx, ty = x + lean * 1.6, y - h
    fronds = ""
    for ang in (-160, -125, -90, -55, -20, 15):
        a = math.radians(ang)
        ex, ey = tx + math.cos(a) * h * 0.42, ty + math.sin(a) * h * 0.42 + 20
        fronds += f'<path d="M{tx},{ty} Q{(tx + ex) / 2 + 10},{(ty + ey) / 2 - 40} {ex:.1f},{ey:.1f}" fill="none" stroke="{colour}" stroke-width="12" stroke-linecap="round"/>'
    return trunk + fronds


def hero_svg():
    w, h = 1000, 1200
    parts = kaftan()
    defs = f'<defs>{pattern("hero-stripe", "wave", CREAM, BLUE)}</defs>'
    body = (
        f'<rect width="{w}" height="{h}" fill="{BLUE}"/>'
        + sun(500, 330, 190, CREAM, rays=16, ray_len=0.32, width=10)
        + f'<rect x="0" y="700" width="{w}" height="{h}" fill="{BLUE}"/>'
        + waves(760, w, CREAM, rows=9, gap=48, amp=22, width=8, opacity=0.9)
        + f'<g transform="translate(100,180) scale(1.0)">'
        + f'<g transform="translate(12,16)">{"".join(f"<path d=\"{d}\" fill=\"#000\" opacity=\"0.18\"/>" for d, r in parts if r == "body")}</g>'
        + garment_group(parts, "url(#hero-stripe)", CREAM, BLUE)
        + "</g>"
    )
    return svg(w, h, defs + body, "A striped kaftan in front of a cream sun over blue waves")


def category_svg(shape, print_kind):
    parts = SILHOUETTES[shape]()
    pid = f"cat-{shape}"
    defs = f"<defs>{pattern(pid, print_kind, BLUE, CREAM)}</defs>"
    shadow = "".join(f'<path d="{d}" fill="#000" opacity="0.16"/>' for d, role in parts if role == "body")
    body = (
        f'<rect width="{W}" height="{H}" fill="{BLUE}"/>'
        + sun(400, 280, 150, CREAM, rays=12, ray_len=0.3, width=8).replace(CREAM, CREAM + '" opacity="0.28')
        + f'<g transform="translate(80,40) scale(0.8)"><g transform="translate(12,16)">{shadow}</g>'
        + garment_group(parts, f"url(#{pid})", CREAM, BLUE)
        + "</g>"
    )
    return svg(W, H, defs + body, f"{shape} silhouette")


def lifestyle_1():
    w, h = 1600, 900
    body = (
        f'<rect width="{w}" height="{h}" fill="{CREAM}"/>'
        + sun(1180, 300, 170, BLUE, rays=14, ray_len=0.35, width=9)
        + waves(640, w, BLUE, rows=7, gap=40, amp=18, width=7)
        + palm_tree(260, 700, 420, BLUE, lean=60)
        + palm_tree(120, 720, 300, BLUE, lean=-30)
        + f'<ellipse cx="820" cy="760" rx="260" ry="26" fill="{BLUE}" opacity="0.25"/>'
        # a lounger
        + f'<path d="M640,700 L980,700 L1000,740 L620,740 Z" fill="{BLUE}"/>'
        + f'<path d="M640,700 L600,560 L700,560 L700,700 Z" fill="{BLUE}"/>'
        + f'<line x1="660" y1="740" x2="660" y2="780" stroke="{BLUE}" stroke-width="10"/><line x1="960" y1="740" x2="960" y2="780" stroke="{BLUE}" stroke-width="10"/>'
        # a drink with umbrella
        + f'<path d="M1080,620 L1140,620 L1125,720 L1095,720 Z" fill="none" stroke="{BLUE}" stroke-width="8"/>'
        + f'<line x1="1110" y1="720" x2="1110" y2="760" stroke="{BLUE}" stroke-width="8"/><line x1="1080" y1="760" x2="1140" y2="760" stroke="{BLUE}" stroke-width="8" stroke-linecap="round"/>'
        + f'<path d="M1050,600 A60,60 0 0 1 1170,600 Z" fill="{BLUE}"/><line x1="1110" y1="600" x2="1110" y2="660" stroke="{BLUE}" stroke-width="5"/>'
    )
    return svg(w, h, body, "A sun over waves with palms and a lounger")


def lifestyle_2():
    w, h = 1600, 900
    defs = f'<defs>{pattern("l2", "gingham", CREAM, BLUE, scale=3)}</defs>'
    body = (
        f'<rect width="{w}" height="{h}" fill="{BLUE}"/>'
        f'<rect width="{w}" height="{h}" fill="url(#l2)" opacity="0.5"/>'
        + sun(800, 450, 220, CREAM, rays=20, ray_len=0.5, width=12)
    )
    return svg(w, h, defs + body, "A cream sun on blue gingham")


def about_svg():
    """A rail with three garments, studio style."""
    w, h = 1200, 900
    defs = "<defs>" + pattern("a1", "wave", BLUE, CREAM) + pattern("a2", "dot", CREAM, BLUE) + pattern("a3", "palm", BLUE, CREAM) + "</defs>"
    body = f'<rect width="{w}" height="{h}" fill="{CREAM}"/>'
    body += f'<rect x="120" y="120" width="960" height="14" rx="7" fill="{BLUE}"/>'
    body += f'<rect x="150" y="134" width="14" height="700" fill="{BLUE}"/><rect x="1036" y="134" width="14" height="700" fill="{BLUE}"/>'
    for i, (shape, pid) in enumerate([("kaftan", "a1"), ("coord", "a2"), ("slip", "a3")]):
        x = 130 + i * 300
        parts = SILHOUETTES[shape]()
        body += f'<g transform="translate({x},140) scale(0.72)">'
        body += f'<path d="M400,60 q0,-40 30,-40 q30,0 20,30 M400,60 L400,120" fill="none" stroke="{BLUE}" stroke-width="8" stroke-linecap="round"/>'
        body += f'<path d="M400,120 L200,220 L600,220 Z" fill="none" stroke="{BLUE}" stroke-width="8" stroke-linejoin="round"/>'
        body += f'<g transform="translate(0,60)">{garment_group(parts, f"url(#{pid})", BLUE, CREAM)}</g></g>'
    return svg(w, h, defs + body, "Three garments on hangers on a rail")


def ig_tile(n):
    w = 600
    blue_bg = n % 2 == 1
    bg, fg = (BLUE, CREAM) if blue_bg else (CREAM, BLUE)
    body = f'<rect width="{w}" height="{w}" fill="{bg}"/>'
    if n == 1:  # sunglasses
        body += (
            f'<rect x="90" y="250" width="180" height="120" rx="60" fill="{fg}"/><rect x="330" y="250" width="180" height="120" rx="60" fill="{fg}"/>'
            f'<path d="M270,300 q30,-30 60,0" fill="none" stroke="{fg}" stroke-width="14"/>'
            f'<line x1="90" y1="290" x2="40" y2="250" stroke="{fg}" stroke-width="14" stroke-linecap="round"/><line x1="510" y1="290" x2="560" y2="250" stroke="{fg}" stroke-width="14" stroke-linecap="round"/>'
        )
    elif n == 2:  # flip flops
        for cx in (200, 400):
            body += f'<ellipse cx="{cx}" cy="300" rx="80" ry="180" fill="{fg}"/>'
            body += f'<path d="M{cx},220 L{cx - 50},320 M{cx},220 L{cx + 50},320" stroke="{bg}" stroke-width="12" stroke-linecap="round"/>'
    elif n == 3:  # sun
        body += sun(300, 300, 120, fg, rays=12, ray_len=0.5, width=14)
    elif n == 4:  # shell
        body += f'<path d="M300,470 L120,240 A180,180 0 0 1 480,240 Z" fill="{fg}"/>'
        for k in range(-3, 4):
            a = math.radians(-90 + k * 22)
            body += f'<line x1="300" y1="470" x2="{300 + math.cos(a) * 200:.1f}" y2="{470 + math.sin(a) * 200:.1f}" stroke="{bg}" stroke-width="10"/>'
    elif n == 5:  # cocktail
        body += (
            f'<path d="M140,160 L460,160 L300,340 Z" fill="{fg}"/><rect x="288" y="340" width="24" height="120" fill="{fg}"/>'
            f'<rect x="200" y="450" width="200" height="22" rx="11" fill="{fg}"/>'
            f'<circle cx="220" cy="230" r="26" fill="{bg}"/><line x1="360" y1="90" x2="300" y2="200" stroke="{fg}" stroke-width="10"/>'
        )
    else:  # waves
        body += waves(120, w, fg, rows=8, gap=50, amp=22, width=12)
    return svg(w, w, body, f"instagram tile {n}")


def favicon_svg():
    body = f'<rect width="64" height="64" rx="14" fill="{BLUE}"/>' + sun(32, 32, 11, CREAM, rays=8, ray_len=0.5, width=3.5)
    return svg(64, 64, body, "Bay'n Bae")


# ---------------------------------------------------------- PNG (no Pillow)
def write_png(path, width, height, pixel):
    """pixel(x, y) -> (r, g, b). Minimal RGB PNG encoder."""
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pixel(x, y))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def hexrgb(h):
    return tuple(int(h[i : i + 2], 16) for i in (1, 3, 5))


def social_card_png(path, width=1200, height=630):
    blue, cream = hexrgb(BLUE), hexrgb(CREAM)
    cx, cy, r = width // 2, height // 2 - 20, 150
    rays = 16

    def pixel(x, y):
        dx, dy = x - cx, y - cy
        d = math.hypot(dx, dy)
        if d <= r:
            return cream
        if r * 1.2 <= d <= r * 1.75:
            ang = math.atan2(dy, dx)
            phase = (ang / (2 * math.pi)) * rays
            if abs(phase - round(phase)) < 0.09:
                return cream
        # wave band across the bottom
        if y > height - 110:
            wy = height - 60 + 14 * math.sin(x / 42.0)
            if abs(y - wy) < 5 or abs(y - wy - 30) < 5:
                return cream
        return blue

    write_png(path, width, height, pixel)


def icon_png(path, size=512):
    blue, cream = hexrgb(BLUE), hexrgb(CREAM)
    cx = cy = size / 2
    r = size * 0.2
    rays = 12

    def pixel(x, y):
        dx, dy = x - cx, y - cy
        d = math.hypot(dx, dy)
        if d <= r:
            return cream
        if r * 1.25 <= d <= r * 1.9:
            ang = math.atan2(dy, dx)
            phase = (ang / (2 * math.pi)) * rays
            if abs(phase - round(phase)) < 0.07:
                return cream
        return blue

    write_png(path, size, size, pixel)


# ----------------------------------------------------------------- catalog
# (slug, shape, print kind, inverted)  — mirrors catalog/seed_data.py
PRODUCT_ART = [
    ("sundowner-kaftan", "kaftan", "wave", False),
    ("do-not-disturb-kaftan", "kaftan", "dot", True),
    ("palm-reader-kaftan", "kaftan", "palm", False),
    ("late-checkout-kaftan", "kaftan", "solid", True),
    ("sheer-audacity-cover-up", "coverup", "scallop", False),
    ("beach-please-cover-up", "coverup", "zigzag", True),
    ("picnic-gone-wrong-slip-dress", "slip", "gingham", False),
    ("sun-salutation-tiered-dress", "tiered", "sun", False),
    ("golden-hour-maxi-dress", "tiered", "floral", True),
    ("room-service-slip-dress", "slip", "solid", True),
    ("main-character-co-ord", "coord", "diamond", False),
    ("stripe-tease-co-ord", "coord", "stripe", False),
    ("out-of-office-co-ord", "coord", "dot", False),
    ("boardwalk-shorts-set", "shorts", "wave", True),
    ("lazy-sunday-shorts-set", "shorts", "zigzag", False),
    ("sea-legs-shorts-set", "shorts", "palm", True),
]

CATEGORY_ART = [
    ("cat-kaftans.svg", "kaftan", "wave"),
    ("cat-cover-ups.svg", "coverup", "scallop"),
    ("cat-dresses.svg", "tiered", "sun"),
    ("cat-co-ord-sets.svg", "coord", "stripe"),
    ("cat-shorts-sets.svg", "shorts", "gingham"),
]


def main():
    PRODUCTS.mkdir(parents=True, exist_ok=True)
    EDITORIAL.mkdir(parents=True, exist_ok=True)
    count = 0
    for slug, shape, kind, inverted in PRODUCT_ART:
        (PRODUCTS / f"{slug}-1.svg").write_text(product_front(slug, shape, kind, inverted))
        (PRODUCTS / f"{slug}-2.svg").write_text(product_detail(slug, kind, inverted))
        (PRODUCTS / f"{slug}-3.svg").write_text(product_back(slug, shape, kind, inverted))
        count += 3
    (EDITORIAL / "hero.svg").write_text(hero_svg())
    (EDITORIAL / "lifestyle-1.svg").write_text(lifestyle_1())
    (EDITORIAL / "lifestyle-2.svg").write_text(lifestyle_2())
    (EDITORIAL / "about.svg").write_text(about_svg())
    for name, shape, kind in CATEGORY_ART:
        (EDITORIAL / name).write_text(category_svg(shape, kind))
    for n in range(1, 7):
        (EDITORIAL / f"ig-{n}.svg").write_text(ig_tile(n))
    (ROOT / "favicon.svg").write_text(favicon_svg())
    social_card_png(ROOT / "social-card.png")
    icon_png(ROOT / "icon-512.png")
    count += 4 + len(CATEGORY_ART) + 6 + 3
    print(f"wrote {count} images under {ROOT}")


if __name__ == "__main__":
    main()
