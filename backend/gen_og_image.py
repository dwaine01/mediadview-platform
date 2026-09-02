"""
Generate:
  1) og-image.png (1200x630) — social sharing preview
  2) favicon.png  (512x512)  — pro app-style icon (bold "M" on gradient)
"""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

WEB = os.path.join(os.path.dirname(__file__), 'web')
OG_OUT  = os.path.join(WEB, 'og-image.png')
FAV_OUT = os.path.join(WEB, 'favicon.png')
LOGO_CANDIDATES = [
    os.path.join(WEB, 'logo-new.png'),
    os.path.join(WEB, 'logo-dark.png'),
]

def gradient_h(w, h, left, right):
    """Horizontal gradient."""
    img = Image.new('RGB', (w, h))
    px = img.load()
    for x in range(w):
        t = x / (w - 1)
        r = int(left[0] * (1 - t) + right[0] * t)
        g = int(left[1] * (1 - t) + right[1] * t)
        b = int(left[2] * (1 - t) + right[2] * t)
        for y in range(h):
            px[x, y] = (r, g, b)
    return img

def gradient_diag(size, top_left, bottom_right):
    """Diagonal gradient (top-left → bottom-right)."""
    img = Image.new('RGB', (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            r = int(top_left[0] * (1 - t) + bottom_right[0] * t)
            g = int(top_left[1] * (1 - t) + bottom_right[1] * t)
            b = int(top_left[2] * (1 - t) + bottom_right[2] * t)
            px[x, y] = (r, g, b)
    return img

def find_font(size):
    for path in [
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVu-Sans-Bold.ttf',
        '/root/.venv/lib/python3.11/site-packages/matplotlib/mpl-data/fonts/ttf/DejaVuSans-Bold.ttf',
    ]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

def rounded_mask(size, radius):
    """Return an 'L' mask that's a rounded square."""
    m = Image.new('L', (size, size), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return m


# =================== OG IMAGE ===================
def build_og():
    W, H = 1200, 630
    # Deep navy background
    img = Image.new('RGB', (W, H), (12, 18, 44))
    draw = ImageDraw.Draw(img, 'RGBA')
    # Subtle decorative gradient blobs
    for cx, cy, r, col in [
        (W - 180, 140, 280, (99, 102, 241, 55)),
        (140, H - 120, 340, (34, 211, 238, 45)),
        (W // 2, H // 2, 500, (99, 102, 241, 18)),
    ]:
        for i in range(28, 0, -1):
            alpha = int(col[3] * (i / 28) * 0.35)
            draw.ellipse((cx - r * i / 28, cy - r * i / 28,
                          cx + r * i / 28, cy + r * i / 28),
                         fill=(col[0], col[1], col[2], alpha))
    # Logo big & centered — no text
    logo_path = next((p for p in LOGO_CANDIDATES if os.path.exists(p)), None)
    if logo_path:
        logo = Image.open(logo_path).convert('RGBA')
        target_w = int(W * 0.78)
        ratio = target_w / logo.width
        target_h = int(logo.height * ratio)
        if target_h > H * 0.72:
            target_h = int(H * 0.72)
            ratio = target_h / logo.height
            target_w = int(logo.width * ratio)
        logo = logo.resize((target_w, target_h), Image.LANCZOS)
        img.paste(logo, ((W - target_w) // 2, (H - target_h) // 2), logo)
    # Bottom accent bar (cyan → indigo)
    bar = 8
    for x in range(W):
        t = x / (W - 1)
        r = int(34 * (1 - t) + 99 * t)
        g = int(211 * (1 - t) + 102 * t)
        b = int(238 * (1 - t) + 241 * t)
        draw.line([(x, H - bar), (x, H)], fill=(r, g, b, 255))
    img.save(OG_OUT, 'PNG', optimize=True)
    print(f"OG image: {OG_OUT}  ({os.path.getsize(OG_OUT)} bytes)")


# =================== FAVICON (round, isotipo-focused) ===================
def build_favicon():
    """Round icon (circle, not square) with the actual MediAd View isotipo
    (phone + swoosh) big and centered on a clean navy background."""
    S = 512

    logo_path = next((p for p in LOGO_CANDIDATES if os.path.exists(p)), None)
    if not logo_path:
        return
    logo = Image.open(logo_path).convert('RGBA')

    # 1. Crop just the isotipo (phone symbol) — leftmost ~24% of visible content
    alpha = logo.split()[-1]
    bbox = alpha.getbbox() or (0, 0, logo.width, logo.height)
    left, top, right, bottom = bbox
    content_w = right - left
    sym_right = left + int(content_w * 0.24)
    symbol = logo.crop((left, top, sym_right, bottom))

    # 2. Make the symbol square (paste onto transparent square, centered)
    sw, sh = symbol.size
    side = max(sw, sh)
    sq = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    sq.paste(symbol, ((side - sw) // 2, (side - sh) // 2), symbol)

    # 3. Scale symbol to ~68% of icon size (leaves nice breathing room)
    target = int(S * 0.68)
    symbol_scaled = sq.resize((target, target), Image.LANCZOS)

    # 4. Base circle — deep navy background with a soft radial glow inside
    icon = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    # Circle mask
    mask = Image.new('L', (S, S), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, S - 1, S - 1), fill=255)
    # Fill with navy
    navy = Image.new('RGB', (S, S), (10, 14, 46))
    # Add radial glow (cyan center → navy edge) for depth
    glow = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for r in range(int(S * 0.6), 0, -8):
        a = int(45 * (1 - r / (S * 0.6)))
        gd.ellipse((S // 2 - r, S // 2 - r, S // 2 + r, S // 2 + r),
                   fill=(99, 102, 241, a))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=12))
    navy_rgba = navy.convert('RGBA')
    navy_rgba = Image.alpha_composite(navy_rgba, glow)
    icon.paste(navy_rgba, (0, 0), mask)

    # 5. Very subtle inner ring for polish (like premium app icons)
    ring = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse((6, 6, S - 7, S - 7), outline=(255, 255, 255, 25), width=2)
    icon = Image.alpha_composite(icon, ring)

    # 6. Paste isotipo centered
    icon.paste(symbol_scaled,
               ((S - target) // 2, (S - target) // 2),
               symbol_scaled)

    icon.save(FAV_OUT, 'PNG', optimize=True)
    print(f"Favicon: {FAV_OUT}  ({os.path.getsize(FAV_OUT)} bytes)")


if __name__ == '__main__':
    build_og()
    build_favicon()
