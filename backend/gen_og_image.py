"""
Generate:
  1) og-image.png (1200x630) — social sharing card. Logo big & centered, no text.
  2) favicon.png (512x512)   — square icon for browser tabs.
"""
import os
from PIL import Image, ImageDraw

WEB = os.path.join(os.path.dirname(__file__), 'web')
OG_OUT       = os.path.join(WEB, 'og-image.png')
FAV_OUT      = os.path.join(WEB, 'favicon.png')
LOGO_CANDIDATES = [
    os.path.join(WEB, 'logo-new.png'),
    os.path.join(WEB, 'logo-dark.png'),
]


def gradient(w, h, top, bottom):
    img = Image.new('RGB', (w, h), top)
    px = img.load()
    for y in range(h):
        t = y / (h - 1)
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    return img


def build_og():
    W, H = 1200, 630
    img = gradient(W, H, (12, 18, 44), (24, 30, 70))
    draw = ImageDraw.Draw(img, 'RGBA')

    # Subtle decorative glows
    for cx, cy, r, col in [
        (W - 180, 140, 260, (99, 102, 241, 55)),
        (140, H - 120, 320, (34, 211, 238, 45)),
        (W // 2, H // 2, 480, (99, 102, 241, 18)),
    ]:
        for i in range(28, 0, -1):
            alpha = int(col[3] * (i / 28) * 0.35)
            draw.ellipse((cx - r * i / 28, cy - r * i / 28,
                          cx + r * i / 28, cy + r * i / 28),
                         fill=(col[0], col[1], col[2], alpha))

    # Logo — BIG and centered
    logo_path = next((p for p in LOGO_CANDIDATES if os.path.exists(p)), None)
    if logo_path:
        logo = Image.open(logo_path).convert('RGBA')
        # Fit logo to ~78% of the canvas width (visually dominant)
        target_w = int(W * 0.78)
        ratio = target_w / logo.width
        target_h = int(logo.height * ratio)
        # If height too tall, constrain by height instead
        if target_h > H * 0.72:
            target_h = int(H * 0.72)
            ratio = target_h / logo.height
            target_w = int(logo.width * ratio)
        logo = logo.resize((target_w, target_h), Image.LANCZOS)
        pos = ((W - target_w) // 2, (H - target_h) // 2)
        img.paste(logo, pos, logo)

    # Bottom accent bar (cyan → indigo)
    bar_h = 8
    for x in range(W):
        t = x / (W - 1)
        r = int(34 * (1 - t) + 99 * t)
        g = int(211 * (1 - t) + 102 * t)
        b = int(238 * (1 - t) + 241 * t)
        draw.line([(x, H - bar_h), (x, H)], fill=(r, g, b, 255))

    img.save(OG_OUT, 'PNG', optimize=True)
    print(f"OG image: {OG_OUT}  ({os.path.getsize(OG_OUT)} bytes)")


def build_favicon():
    """A square icon browsers scale down to 16/32/48 px in tabs.
    The MediAd View logo is wide (letterbox), so we crop just the 'symbol'
    portion on the left and place it centered on a solid brand-navy square."""
    SIZE = 512
    logo_path = next((p for p in LOGO_CANDIDATES if os.path.exists(p)), None)
    if not logo_path:
        return

    # Solid brand-navy background — high contrast in light + dark browser themes
    icon = Image.new('RGBA', (SIZE, SIZE), (12, 18, 44, 255))
    draw = ImageDraw.Draw(icon, 'RGBA')

    logo = Image.open(logo_path).convert('RGBA')

    # The logo is wide (letterbox): estimate the "symbol" area on the left
    # by cropping the leftmost ~30% (typical MediAd View play-triangle icon).
    lw, lh = logo.size
    # Find the leftmost non-transparent column to trim padding
    alpha = logo.split()[-1]
    bbox = alpha.getbbox() or (0, 0, lw, lh)
    left, top, right, bottom = bbox
    # Crop to symbol: leftmost 22% of the actual content (just the phone/play icon)
    content_w = right - left
    sym_right = left + int(content_w * 0.22)
    symbol = logo.crop((left, top, sym_right, bottom))

    # Resize symbol to ~75% of canvas, centered
    sw, sh = symbol.size
    target_h = int(SIZE * 0.78)
    ratio = target_h / sh
    target_w = int(sw * ratio)
    if target_w > SIZE * 0.85:
        target_w = int(SIZE * 0.85)
        ratio = target_w / sw
        target_h = int(sh * ratio)
    symbol = symbol.resize((target_w, target_h), Image.LANCZOS)
    icon.paste(symbol, ((SIZE - target_w) // 2, (SIZE - target_h) // 2), symbol)

    icon.save(FAV_OUT, 'PNG', optimize=True)
    print(f"Favicon: {FAV_OUT}  ({os.path.getsize(FAV_OUT)} bytes)")


if __name__ == '__main__':
    build_og()
    build_favicon()
