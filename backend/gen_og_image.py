"""
Generate the Open Graph preview image for MediAd View social sharing.
Recommended size: 1200x630 (Facebook/LinkedIn/Twitter standard).
Overlays the existing MediAd View logo onto a brand-gradient background.
Run once at deploy time — output saved to backend/web/og-image.png.
"""
import os
from PIL import Image, ImageDraw, ImageFont

WEB = os.path.join(os.path.dirname(__file__), 'web')
OUT = os.path.join(WEB, 'og-image.png')
LOGO_CANDIDATES = [
    os.path.join(WEB, 'logo-new.png'),
    os.path.join(WEB, 'logo-dark.png'),
]

W, H = 1200, 630

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

def find_font(size):
    for path in [
        '/usr/share/fonts/truetype/dejavu/DejaVu-Sans-Bold.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/System/Library/Fonts/Helvetica.ttc',
    ]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

def build():
    # Deep navy → indigo → cyan gradient (MediAd View brand)
    img = gradient(W, H, (12, 18, 44), (24, 30, 70))
    draw = ImageDraw.Draw(img, 'RGBA')

    # Decorative glow blobs
    for cx, cy, r, col in [
        (W - 180, 140, 220, (99, 102, 241, 60)),
        (100, H - 100, 280, (34, 211, 238, 45)),
        (W // 2, H // 2, 400, (99, 102, 241, 22)),
    ]:
        for i in range(24, 0, -1):
            alpha = int(col[3] * (i / 24) * 0.35)
            draw.ellipse((cx - r * i / 24, cy - r * i / 24,
                          cx + r * i / 24, cy + r * i / 24),
                         fill=(col[0], col[1], col[2], alpha))

    # Logo — centered upper 60%
    logo_path = next((p for p in LOGO_CANDIDATES if os.path.exists(p)), None)
    if logo_path:
        logo = Image.open(logo_path).convert('RGBA')
        target_w = 640
        ratio = target_w / logo.width
        logo = logo.resize((target_w, int(logo.height * ratio)), Image.LANCZOS)
        img.paste(logo, ((W - logo.width) // 2, 130), logo)

    # Tagline
    tagline = "Digital Advertising Solutions"
    f_tag = find_font(38)
    tw = draw.textlength(tagline, font=f_tag)
    draw.text(((W - tw) / 2, 400), tagline, font=f_tag,
              fill=(226, 232, 240, 255))

    # Sub tagline
    sub = "LED Displays  ·  Content Management  ·  Campaign Analytics"
    f_sub = find_font(24)
    sw = draw.textlength(sub, font=f_sub)
    draw.text(((W - sw) / 2, 470), sub, font=f_sub,
              fill=(148, 163, 184, 255))

    # Bottom accent bar (cyan → indigo)
    bar_h = 8
    for x in range(W):
        t = x / (W - 1)
        r = int(34 * (1 - t) + 99 * t)
        g = int(211 * (1 - t) + 102 * t)
        b = int(238 * (1 - t) + 241 * t)
        draw.line([(x, H - bar_h), (x, H)], fill=(r, g, b, 255))

    # Domain in bottom-right corner
    dom = "mediadview.com"
    f_dom = find_font(20)
    dw = draw.textlength(dom, font=f_dom)
    draw.text((W - dw - 40, H - bar_h - 40), dom, font=f_dom,
              fill=(148, 163, 184, 220))

    img.save(OUT, 'PNG', optimize=True)
    print(f"OG image written: {OUT}  ({os.path.getsize(OUT)} bytes)")

if __name__ == '__main__':
    build()
