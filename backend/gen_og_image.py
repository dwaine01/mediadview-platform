"""
Generate:
  1) og-image.png (1200x630) — social sharing preview
  2) favicon.png  (512x512)  — pro app-style icon (bold "M" on gradient)
"""
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

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


# =================== FAVICON (pro app-icon style) ===================
def build_favicon():
    """Modern iOS-style rounded square with cyan→indigo gradient +
    a bold white 'M' letter. Simple, high-contrast, works at 16px."""
    S = 512

    # 1. Base: diagonal cyan → indigo gradient
    base = gradient_diag(S, (34, 211, 238), (79, 70, 229))

    # 2. Clip into rounded square (iOS radius = ~22% of side)
    icon = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    mask = rounded_mask(S, int(S * 0.22))
    icon.paste(base, (0, 0), mask)

    # 3. Subtle inner glow (top highlight to feel glossy)
    glow = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i in range(0, 60):
        a = int(30 * (1 - i / 60))
        gd.ellipse((-S // 4 + i, -S // 4 + i,
                    S + S // 4 - i, S // 2 + i),
                   fill=(255, 255, 255, a))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=8))
    icon = Image.alpha_composite(icon, glow)

    # 4. Bold white "M" centered
    draw = ImageDraw.Draw(icon, 'RGBA')
    # Try progressively smaller font sizes until it fits nicely
    letter = "M"
    font_size = int(S * 0.72)
    font = find_font(font_size)
    while font_size > 60:
        # Measure
        bbox = draw.textbbox((0, 0), letter, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        if tw < S * 0.72 and th < S * 0.72:
            break
        font_size -= 12
        font = find_font(font_size)
    bbox = draw.textbbox((0, 0), letter, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    # Center visually (baseline correction)
    x = (S - tw) / 2 - bbox[0]
    y = (S - th) / 2 - bbox[1] - int(S * 0.02)

    # Soft drop shadow
    shadow = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.text((x + 6, y + 8), letter, font=font, fill=(0, 0, 0, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=6))
    icon = Image.alpha_composite(icon, shadow)

    # White letter on top
    draw = ImageDraw.Draw(icon, 'RGBA')
    draw.text((x, y), letter, font=font, fill=(255, 255, 255, 255))

    icon.save(FAV_OUT, 'PNG', optimize=True)
    print(f"Favicon: {FAV_OUT}  ({os.path.getsize(FAV_OUT)} bytes)")


if __name__ == '__main__':
    build_og()
    build_favicon()
