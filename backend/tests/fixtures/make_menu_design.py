"""Builds a fake designed menu (JPG) so we can test the canvas flow end to end
without shipping a binary fixture into the repo.

Uses the Liberation/FreeSans fonts that ship with the container; falls back to
Pillow's bitmap font only if none is present (the layout still renders, just
with tiny glyphs).
"""
import io
import os

from PIL import Image, ImageDraw, ImageFont

SERIF_BOLD = [
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSerifBold.ttf",
]
SANS_BOLD = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]


def _font(candidates, size):
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def build(path="/tmp/menu_design.jpg", width=1600, height=900):
    img = Image.new("RGB", (width, height), "#FDF6E3")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, width, 130], fill="#7B2D26")
    title = _font(SERIF_BOLD, 60)
    name = _font(SANS_BOLD, 40)
    price = _font(SANS_BOLD, 38)
    d.text((60, 34), "TRATTORIA BELLA", font=title, fill="#FDF6E3")

    rows = [("Pizza Margherita", "12.50", "#C1440E"),
            ("Lasagna de la Casa", "16.00", "#4E6E58"),
            ("Ravioli de Ricotta", "14.75", "#8A6D3B"),
            ("Tiramisu Clasico", "8.00", "#5B4636")]
    y = 200
    for label, value, swatch in rows:
        # solid swatch standing in for a product photo
        d.rounded_rectangle([60, y, 260, y + 150], radius=16, fill=swatch)
        d.text((300, y + 55), label, font=name, fill="#3A2A18")
        d.text((1330, y + 55), "$" + value, font=price, fill="#7B2D26")
        y += 170
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    with open(path, "wb") as fh:
        fh.write(buf.getvalue())
    return path


if __name__ == "__main__":
    print(build())
