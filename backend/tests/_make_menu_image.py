"""Generate a synthetic menu image with real, legible text.
The AI vision model must be able to extract these products & prices."""
import base64
import io

from PIL import Image, ImageDraw, ImageFont


def make_menu_jpeg_b64() -> str:
    W, H = 800, 900
    img = Image.new("RGB", (W, H), (252, 248, 240))
    d = ImageDraw.Draw(img)

    # Try to use a common truetype font; fall back to default if missing.
    def _font(size):
        for path in [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]:
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
        return ImageFont.load_default()

    title = _font(46)
    section = _font(30)
    body = _font(28)

    d.text((240, 30), "PIZZERIA DON LUIS", fill=(30, 30, 30), font=title)
    d.text((360, 90), "MENU", fill=(120, 30, 30), font=section)

    d.text((40, 160), "PIZZAS", fill=(120, 30, 30), font=section)
    y = 210
    for name, price in [
        ("Margarita", "8.50"),
        ("Pepperoni", "9.90"),
        ("Cuatro Quesos", "11.00"),
        ("Hawaiana", "10.50"),
    ]:
        d.text((60, y), name, fill=(30, 30, 30), font=body)
        d.text((650, y), f"${price}", fill=(30, 30, 30), font=body)
        y += 55

    d.text((40, y + 20), "BEBIDAS", fill=(120, 30, 30), font=section)
    y += 70
    for name, price in [
        ("Agua Mineral", "1.50"),
        ("Refresco Cola", "2.20"),
        ("Cerveza Artesanal", "4.00"),
    ]:
        d.text((60, y), name, fill=(30, 30, 30), font=body)
        d.text((650, y), f"${price}", fill=(30, 30, 30), font=body)
        y += 55

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode("ascii")


if __name__ == "__main__":
    b64 = make_menu_jpeg_b64()
    print(f"Menu image bytes (base64 length): {len(b64)}")
