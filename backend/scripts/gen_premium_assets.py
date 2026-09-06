"""
MediaView — Premium marketing asset generator (Gemini Nano Banana).

One-time / re-runnable offline script. Skips assets that already exist.
Outputs PNG files to /app/backend/web/assets/ (served at /api/web/assets/<id>.png).

Usage:
    python -m scripts.gen_premium_assets            # generate all missing
    python -m scripts.gen_premium_assets MV-HERO-001 MV-ICE-001
"""
import asyncio
import base64
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

OUT_DIR = BACKEND_DIR / "web" / "assets"
MODEL = "gemini-3.1-flash-image-preview"

# Shared style guardrails so the whole library feels like one brand.
BASE_STYLE = (
    "Ultra-realistic, high-end commercial advertising photography quality. "
    "Crisp, modern, premium SaaS marketing look. Clean composition, generous negative space, "
    "professional studio-grade lighting, subtle depth of field. "
    "Modern restrained color palette - never garish or neon. "
    "No watermarks, no real-world brand logos, no gibberish text: any visible text must be "
    "real, correctly spelled English words. Photorealistic, not illustrated, not cartoon."
)

SCREEN_STYLE = (
    "This is the artwork displayed ON a digital signage screen (full-bleed, edge to edge, "
    "no device frame, no bezel, no room, no perspective - a flat frontal 16:9 screen design). "
    "Designed like a professional digital menu board: strong typographic hierarchy, "
    "appetizing photography, clear prices, readable from a distance. "
    "No watermarks, no real brand logos. All text must be real correctly spelled English words."
)

MANIFEST: dict[str, dict] = {
    # ─────────────── HERO ───────────────
    "MV-HERO-001": {
        "purpose": "Homepage hero — TV in a real restaurant",
        "where": "landing.html hero",
        "ratio": "16:9",
        "prompt": (
            "A warm, modern pizzeria interior at golden hour. On the wall behind the service counter, "
            "a large 55-inch flat-screen display is mounted, showing a beautiful digital pizza menu board "
            "with dark background, appetizing pizza photography and clear white prices. "
            "The screen glows and is the clear focal point, perfectly sharp. "
            "Blurred warm background: wooden counter, hanging pendant lights, a couple of out-of-focus customers. "
            "Shot on 35mm, shallow depth of field, cinematic but bright and inviting. " + BASE_STYLE
        ),
    },
    "MV-HERO-002": {
        "purpose": "Hero alternate — multi-screen menu wall",
        "where": "landing.html hero / environments",
        "ratio": "16:9",
        "prompt": (
            "A bright modern fast-casual restaurant. Three large landscape displays mounted side by side "
            "above the ordering counter form a continuous digital menu wall: left screen shows burgers, "
            "center shows combo meals, right shows drinks and desserts. Screens are bright, sharp and legible. "
            "Clean white and light wood interior, soft daylight, no people in focus. "
            "Straight-on architectural photography, symmetrical composition. " + BASE_STYLE
        ),
    },

    # ─────────────── SCREEN CONTENT: RESTAURANTS ───────────────
    "MV-REST-PIZZA": {
        "purpose": "Pizza menu board artwork",
        "where": "Industries grid / templates",
        "ratio": "16:9",
        "prompt": (
            "A premium digital PIZZA menu board. Deep charcoal background with warm amber accents. "
            "Header reads 'WOOD FIRED PIZZA'. Exactly six unique items, arranged in two rows of three, "
            "each with a small round overhead photo of that pizza: "
            "'Margherita 12.99', 'Pepperoni 14.49', 'Four Cheese 15.99', 'Prosciutto 16.50', "
            "'Veggie Garden 13.99', 'BBQ Chicken 15.49'. No repeated item names. "
            "Elegant modern sans-serif typography, generous spacing. "
            + SCREEN_STYLE
        ),
    },
    "MV-REST-BURGER": {
        "purpose": "Burger menu board artwork",
        "where": "Industries grid / templates",
        "ratio": "16:9",
        "prompt": (
            "A bold digital BURGER menu board. Dark slate background, large hero photo of a juicy "
            "double cheeseburger on the left third. Right side: header 'BURGERS & COMBOS' and a clean list: "
            "'Classic Smash 9.99', 'Double Bacon 12.99', 'Crispy Chicken 10.49', 'Combo + Fries + Drink 14.99'. "
            "Confident condensed typography, subtle red accent line. " + SCREEN_STYLE
        ),
    },
    "MV-REST-COFFEE": {
        "purpose": "Coffee shop menu board artwork",
        "where": "Industries grid / templates",
        "ratio": "16:9",
        "prompt": (
            "An elegant minimal digital COFFEE menu board. Warm cream and soft beige background, "
            "hand-drawn style coffee cup line icons. Header 'THE DAILY GRIND'. "
            "Two tidy columns: 'Espresso 2.75', 'Cappuccino 4.25', 'Flat White 4.50', 'Cold Brew 4.75', "
            "'Matcha Latte 5.25', 'Croissant 3.50'. Refined serif headings, airy spacing, boutique cafe feel. "
            + SCREEN_STYLE
        ),
    },
    "MV-REST-BREAKFAST": {
        "purpose": "Breakfast menu board artwork",
        "where": "Templates / scheduling story",
        "ratio": "16:9",
        "prompt": (
            "A bright cheerful digital BREAKFAST menu board. Soft off-white background with a large "
            "appetizing photo of pancakes with berries on the right. Left side header 'BREAKFAST · UNTIL 11AM' "
            "and items: 'Buttermilk Pancakes 8.99', 'Avocado Toast 9.49', 'Two Egg Plate 7.99', "
            "'Fresh Orange Juice 3.50'. Friendly rounded typography, sunny warm tone. " + SCREEN_STYLE
        ),
    },

    # ─────────────── SCREEN CONTENT: DESSERT ───────────────
    "MV-ICE-001": {
        "purpose": "Ice cream / dessert menu board artwork",
        "where": "Industries grid / templates",
        "ratio": "16:9",
        "prompt": (
            "A joyful digital ICE CREAM menu board. Soft pastel mint and cream background with playful "
            "rounded shapes. Header 'SCOOPS & SHAKES'. Colorful photos of three ice cream cones and a milkshake. "
            "Items: 'Single Scoop 3.50', 'Double Scoop 5.25', 'Waffle Cone 6.00', 'Classic Milkshake 6.50', "
            "'Banana Split 8.25'. Cheerful modern typography, tasteful pastel palette - not neon. " + SCREEN_STYLE
        ),
    },

    # ─────────────── SCREEN CONTENT: OTHER INDUSTRIES ───────────────
    "MV-MARKET-001": {
        "purpose": "Supermarket weekly specials artwork",
        "where": "Industries grid",
        "ratio": "16:9",
        "prompt": (
            "A clean digital SUPERMARKET weekly specials board. Crisp white background with a green accent bar. "
            "Header 'THIS WEEK'S SPECIALS'. A grid of four product cards with photos and bold prices: "
            "'Fresh Strawberries 2.99 lb', 'Whole Chicken 1.79 lb', 'Avocados 0.99 ea', 'Orange Juice 3.49'. "
            "Bright grocery retail look, high legibility, organized grid. " + SCREEN_STYLE
        ),
    },
    "MV-AUTO-001": {
        "purpose": "Automotive service menu artwork",
        "where": "Industries grid",
        "ratio": "16:9",
        "prompt": (
            "A professional digital AUTO SERVICE board. Dark graphite background with brushed metal texture "
            "and a single orange accent stripe. Header 'SERVICE & MAINTENANCE'. Clean service list with prices: "
            "'Full Synthetic Oil Change 59.99', 'Tire Rotation 24.99', 'Brake Inspection FREE', "
            "'Wheel Alignment 89.99', 'AC Service 119.99'. Small technical icons. "
            "Trustworthy industrial workshop aesthetic. " + SCREEN_STYLE
        ),
    },
    "MV-RETAIL-001": {
        "purpose": "Retail seasonal sale artwork",
        "where": "Industries grid",
        "ratio": "16:9",
        "prompt": (
            "A high-fashion digital RETAIL promotion screen. Editorial photo of a stylish model in autumn "
            "clothing occupying the right half, deep muted burgundy background on the left. "
            "Large elegant type: 'END OF SEASON' and beneath it '40% OFF SELECTED STYLES'. "
            "Small line: 'In store and online'. Luxury boutique campaign feel, sophisticated and restrained. "
            + SCREEN_STYLE
        ),
    },
    "MV-CHURCH-001": {
        "purpose": "Church welcome / announcements artwork",
        "where": "Industries grid",
        "ratio": "16:9",
        "prompt": (
            "A serene digital CHURCH welcome screen. Soft dawn-light photograph of clouds as a gentle background "
            "with a deep navy gradient overlay. Centered elegant type: 'WELCOME HOME'. "
            "Below, a tidy schedule: 'Sunday Service 9:00 AM', 'Bible Study Wednesday 7:00 PM', "
            "'Youth Night Friday 6:30 PM'. Peaceful, warm, dignified, generous white space. " + SCREEN_STYLE
        ),
    },
    "MV-GYM-001": {
        "purpose": "Gym class schedule artwork",
        "where": "Industries grid",
        "ratio": "16:9",
        "prompt": (
            "An energetic digital GYM class schedule screen. Near-black background with a high-contrast "
            "monochrome photo of an athlete on the left, bold lime-green accent details. "
            "Header 'TODAY'S CLASSES'. Schedule rows: '6:00 AM HIIT', '9:00 AM Yoga Flow', "
            "'12:00 PM Spin', '6:00 PM Strength', '7:30 PM Boxing'. "
            "Powerful condensed uppercase typography. " + SCREEN_STYLE
        ),
    },
    "MV-CORP-001": {
        "purpose": "Corporate lobby welcome artwork",
        "where": "Industries grid",
        "ratio": "16:9",
        "prompt": (
            "A refined digital CORPORATE lobby screen. Deep navy blue background with a very subtle "
            "geometric pattern and a thin cyan accent line. Left: 'WELCOME' in large light-weight type and "
            "'Northgate Quarterly Review'. Right: a small tidy panel with 'Meeting Room A · 10:00 AM', "
            "'Visitor Check-in · Level 2', and a simple line chart labeled 'Q3 Performance'. "
            "Calm, executive, enterprise-grade. " + SCREEN_STYLE
        ),
    },
    "MV-EDU-001": {
        "purpose": "School announcements artwork",
        "where": "Industries grid",
        "ratio": "16:9",
        "prompt": (
            "A friendly digital SCHOOL announcements screen. Clean white background with a warm blue header bar "
            "reading 'CAMPUS TODAY'. Three cards: 'Science Fair · Thursday 2 PM · Main Hall', "
            "'Basketball Tryouts · Friday 4 PM · Gym', 'Early Dismissal · Next Monday'. "
            "One cheerful photo of students collaborating. Approachable, organized, highly legible. " + SCREEN_STYLE
        ),
    },
    "MV-HEALTH-001": {
        "purpose": "Healthcare waiting room artwork",
        "where": "Industries grid",
        "ratio": "16:9",
        "prompt": (
            "A calm digital HEALTHCARE waiting room screen. Very light background of soft blue and white with "
            "a gentle gradient. Header 'YOUR HEALTH, OUR PRIORITY'. Three reassuring info tiles with simple "
            "line icons: 'Flu Shots Available Today', 'Average Wait Time 12 Minutes', "
            "'Ask About Annual Checkups'. Soothing, clinical-clean, plenty of white space. " + SCREEN_STYLE
        ),
    },

    # ─────────────── ENVIRONMENT MOCKUPS ───────────────
    "MV-ENV-ICECREAM": {
        "purpose": "Ice cream shop with portrait screen",
        "where": "Environments / industries",
        "ratio": "16:9",
        "prompt": (
            "A charming modern ice cream parlour. A large PORTRAIT (vertical) digital display is mounted on "
            "the pastel-tiled wall beside the gelato counter, showing a colorful ice cream menu with prices. "
            "The screen is sharp and bright. Soft pastel interior, marble counter, warm daylight, "
            "no recognizable faces. Straight-on retail interior photography. " + BASE_STYLE
        ),
    },
    "MV-ENV-AUTO": {
        "purpose": "Automotive workshop waiting area screen",
        "where": "Environments / industries",
        "ratio": "16:9",
        "prompt": (
            "A clean professional auto repair shop customer waiting area. A wall-mounted landscape display "
            "shows an auto service price list on a dark background with an orange accent. "
            "Sharp screen, blurred background of service bays and a car on a lift. "
            "Industrial-modern, grey concrete and steel, cool daylight. " + BASE_STYLE
        ),
    },
    "MV-ENV-RETAIL": {
        "purpose": "Retail storefront window display",
        "where": "Environments / industries",
        "ratio": "16:9",
        "prompt": (
            "A stylish clothing boutique storefront seen from the sidewalk at dusk. Behind the glass window, "
            "a tall bright digital display shows a fashion sale promotion reading '40% OFF'. "
            "Screen is perfectly legible and glowing. Reflections on the glass, blue-hour street ambience, "
            "warm interior light. Premium urban retail photography. " + BASE_STYLE
        ),
    },
    "MV-ENV-LOBBY": {
        "purpose": "Corporate office lobby display",
        "where": "Environments / industries",
        "ratio": "16:9",
        "prompt": (
            "A minimal upscale corporate office lobby. A very large landscape display on a stone feature wall "
            "shows a navy-blue welcome screen with a thin cyan accent. Polished concrete floor, "
            "floor-to-ceiling glass, a single designer bench, soft morning light. "
            "Wide architectural photograph, calm and expensive-looking. " + BASE_STYLE
        ),
    },
    "MV-ENV-CHURCH": {
        "purpose": "Church sanctuary screen",
        "where": "Environments / industries",
        "ratio": "16:9",
        "prompt": (
            "The interior of a modern church sanctuary before service. A large display beside the stage shows "
            "a serene navy welcome screen with a service schedule. Warm wooden pews, soft ambient lighting, "
            "no people. Respectful, peaceful, spacious composition. " + BASE_STYLE
        ),
    },

    # ─────────────── PRODUCT STORY ───────────────
    "MV-MOBILE-001": {
        "purpose": "Phone editing a menu price",
        "where": "Mobile-first editing section",
        "ratio": "4:3",
        "prompt": (
            "Close-up of a hand holding a modern smartphone in a restaurant. The phone screen shows a clean, "
            "light mobile app editing form: a small photo of a pepperoni pizza, a text field labeled 'Name' "
            "containing 'Pepperoni Pizza', a field labeled 'Price' containing '13.99', and a bright cyan "
            "button reading 'Save & Publish'. The UI is minimal, white, with cyan accents. "
            "Warm blurred pizzeria background. Sharp focus on the phone screen. " + BASE_STYLE
        ),
    },
    "MV-PLAYER-001": {
        "purpose": "TV showing 6-digit pairing code",
        "where": "Connect a screen / step 2",
        "ratio": "16:9",
        "prompt": (
            "A modern flat-screen television mounted on a light plaster wall in a small business. "
            "The TV displays a very clean pairing screen: deep navy background, a small cyan circular icon, "
            "the words 'ENTER THIS CODE IN YOUR WORKSPACE' in small light-grey uppercase letters, and below it "
            "a huge crisp six-digit code '482 731' in white. Nothing else on the screen. "
            "Perfectly legible, straight-on, minimal room, soft shadows. " + BASE_STYLE
        ),
    },
    "MV-LAPTOP-001": {
        "purpose": "Laptop dashboard controlling screens",
        "where": "Product story / platform section",
        "ratio": "4:3",
        "prompt": (
            "An open silver laptop on a clean light wooden desk. The screen shows a modern, light, "
            "white digital-signage dashboard with cyan accents: a left sidebar, four small statistic cards, "
            "and a list of screens with green 'Online' status dots and thumbnail previews of menu boards. "
            "The UI is crisp and readable. Behind the desk, two out-of-focus wall-mounted displays glow softly. "
            "Bright airy office, minimal props. " + BASE_STYLE
        ),
    },
    "MV-IMPORT-001": {
        "purpose": "Menu import before/after",
        "where": "Smart menu import section",
        "ratio": "16:9",
        "prompt": (
            "A clean flat-lay concept image on a light neutral background, split into two halves separated by "
            "a thin cyan arrow pointing right. LEFT half: a slightly worn printed paper restaurant menu, "
            "photographed from above, labeled 'PDF / JPG'. RIGHT half: a modern flat-screen display showing "
            "the same menu rebuilt as a beautiful editable digital menu board with photos and clear prices, "
            "labeled 'EDITABLE MENU'. Bright product-photography lighting, minimal and self-explanatory. "
            + BASE_STYLE
        ),
    },
}


async def generate_one(asset_id: str, spec: dict, api_key: str, sem: asyncio.Semaphore) -> tuple[str, bool, str]:
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    out_path = OUT_DIR / f"{asset_id.lower()}.png"
    if out_path.exists() or out_path.with_suffix(".webp").exists():
        return asset_id, True, "skipped (exists)"

    async with sem:
        try:
            chat = LlmChat(
                api_key=api_key,
                session_id=f"mv-asset-{asset_id}",
                system_message="You are a world-class commercial photographer and graphic designer.",
            )
            chat.with_model("gemini", MODEL).with_params(modalities=["image", "text"])
            prompt = f"{spec['prompt']} Aspect ratio: {spec['ratio']} exactly."
            _text, images = await chat.send_message_multimodal_response(UserMessage(text=prompt))
            if not images:
                return asset_id, False, "no image returned"
            out_path.write_bytes(base64.b64decode(images[0]["data"]))
            return asset_id, True, f"saved {out_path.stat().st_size // 1024} KB"
        except Exception as exc:  # noqa: BLE001
            return asset_id, False, f"error: {exc}"


async def main() -> None:
    api_key = os.getenv("EMERGENT_LLM_KEY")
    if not api_key:
        print("EMERGENT_LLM_KEY missing in backend/.env")
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    wanted = sys.argv[1:] or list(MANIFEST)
    sem = asyncio.Semaphore(4)
    results = await asyncio.gather(
        *(generate_one(aid, MANIFEST[aid], api_key, sem) for aid in wanted if aid in MANIFEST)
    )
    ok = sum(1 for _, s, _ in results if s)
    for aid, success, msg in results:
        print(f"{'OK ' if success else 'FAIL'} {aid}: {msg}")
    print(f"\n{ok}/{len(results)} assets ready in {OUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
