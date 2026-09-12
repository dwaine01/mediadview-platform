# ruff: noqa: E701,E702,E741,E731,F811,W293,W605,I001
"""menus_routes.py -- Digital Menu CRUD, category/item management, promo media,
and the screen-facing HTML renderer.

Fase 2B-1 of the modularization plan (see docs/REFACTOR_FASE2_PLAN.md and
docs/AGENT_COORDINATION.md) -- the lowest-risk domain extraction. Pure
relocation of the 15 /menus/* route handlers out of server.py: identical
paths, methods, decorators and logic, registered on a router with
prefix="/api" so the final routes match api_router exactly as before. No
behavior change.

Out of scope / not touched here: menu_ai_routes.py (a separate, already
extracted module for the AI menu-generation surface) and GET
/api/menu-templates (a bare template-listing route that returns the
module-level MENU_TEMPLATES constant -- it does not match /menus/* and
stays in server.py).

Dependency note: gen_id, serialize_doc, _is_platform_admin,
_can_view_playlist, _bump_playlist_screens and _esc are still shared with
other, non-menu code in server.py (playlist routes, widget rendering,
etc.), so they are threaded in as create_menus_routes(...) factory
parameters, the same pattern already used by create_workspace_routes(db,
get_current_user, require_admin, bump_playlist_version, ...). Everything
else -- db, get_current_user, normalize_playlist_items, normalize_schedule
-- is imported directly at module level, per the Fase 2A pattern (deps.py /
media_utils.py / database.py).

_notify_menu_change and _safe_src were used ONLY by these 15 routes and
nothing else in server.py, so both moved here verbatim alongside the
routes they serve, instead of being threaded in as parameters.
"""
import base64
import hashlib
import hmac
import html as html_lib
import json
import logging
import os
import re
import time as _time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from database import db
from deps import get_current_user
from playlist_domain import normalize_playlist_items, normalize_schedule

logger = logging.getLogger(__name__)

# ── Menu preview tokens ───────────────────────────────────────────────────
# The render endpoint is gated to published menus (H3). To let an owner see
# «how it will look on the TV» BEFORE publishing, we hand them a short-lived
# HMAC token instead of loosening the gate or leaking a bearer token into a
# URL. Same pattern as checkout_service quotes.
PREVIEW_TOKEN_TTL_SECONDS = 3600


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64u_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _preview_secret() -> bytes:
    key = os.environ.get("JWT_SECRET", "")
    if not key:
        raise RuntimeError("JWT_SECRET not set")
    return key.encode()


def sign_menu_preview_token(menu_id: str, ttl: int = PREVIEW_TOKEN_TTL_SECONDS) -> str:
    payload = {"m": menu_id, "exp": int(_time.time()) + ttl}
    body = _b64u(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    sig = _b64u(hmac.new(_preview_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_menu_preview_token(token: str, menu_id: str) -> bool:
    """Boolean predicate — never raises on adversarial input."""
    try:
        body, sig = token.split(".", 1)
        expected = _b64u(hmac.new(_preview_secret(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return False
        payload = json.loads(_b64u_decode(body))
        return payload.get("m") == menu_id and payload.get("exp", 0) > _time.time()
    except Exception:
        return False


def _safe_src(v: str, *, allow_data: bool = True) -> str:
    """Allow only https:, http:, and optionally data:image/ or data:video/ in
    src= attributes. Everything else (javascript:, vbscript:, etc.) → '' (inert)."""
    s = str(v or "").strip()
    lo = s.lower()
    if lo.startswith("https://") or lo.startswith("http://"):
        return html_lib.escape(s, quote=True)
    # Same-origin absolute paths (e.g. /api/player/media/<id>) are safe.
    # "//host" is protocol-relative and therefore rejected.
    if s.startswith("/") and not s.startswith("//"):
        return html_lib.escape(s, quote=True)
    if allow_data and (lo.startswith("data:image/") or lo.startswith("data:video/")):
        return html_lib.escape(s, quote=True)
    return ""   # rejected


def create_menus_routes(gen_id, serialize_doc, _is_platform_admin, _can_view_playlist,
                         _bump_playlist_screens, _esc):
    router = APIRouter(prefix="/api", tags=["Menus"])

    async def _notify_menu_change(menu_id: str, reason: str = "menu updated") -> None:
        """Refresh every published screen whose owned playlist renders this menu."""
        playlists = await db.playlists.find(
            {"items": {"$elemMatch": {"type": "menu", "ref_id": menu_id}}},
            {"_id": 0, "id": 1, "status": 1, "screen_ids": 1},
        ).to_list(500)
        if playlists:
            await db.playlists.update_many(
                {"id": {"$in": [playlist["id"] for playlist in playlists]}},
                {"$inc": {"version": 1}, "$set": {"updated_at": datetime.utcnow()}},
            )
        screen_ids = [
            screen_id
            for playlist in playlists
            if playlist.get("status") == "published"
            for screen_id in playlist.get("screen_ids", [])
        ]
        await _bump_playlist_screens(screen_ids, reason)
        try:
            from realtime import manager as realtime_manager
            await realtime_manager.broadcast_menu(menu_id, "updated")
        except Exception as event_error:
            logger.warning("menu realtime event failed for %s: %s", menu_id, event_error)

    @router.post("/menus/{menu_id}/prepare-playlist")
    async def prepare_menu_playlist(menu_id: str, current_user: dict = Depends(get_current_user)):
        menu = await db.menus.find_one({"id": menu_id}, {"_id": 0})
        if not menu:
            raise HTTPException(404, "Menu not found")
        if not _is_platform_admin(current_user) and menu.get("user_id") != current_user["id"]:
            raise HTTPException(403, "Access denied")
        playlist = await db.playlists.find_one({"source_menu_id": menu_id}, {"_id": 0})
        if playlist and _can_view_playlist(playlist, current_user):
            return playlist
        now = datetime.utcnow()
        playlist = {
            "id": gen_id(), "name": f"{menu.get('name', 'Menu')} Playlist", "description": "Digital menu playlist",
            "source_menu_id": menu_id, "created_by_user_id": current_user["id"], "owner_user_id": current_user["id"],
            "client_user_id": menu.get("user_id"), "management_mode": "client",
            "allow_client_publish": _is_platform_admin(current_user), "allowed_screen_ids": [], "screen_ids": [],
            "items": normalize_playlist_items([{"type": "menu", "ref_id": menu_id, "title": menu.get("name"), "duration": 60}]),
            "schedule": normalize_schedule(None), "priority": 10, "status": "draft", "version": 1,
            "pending_items": [], "created_at": now, "updated_at": now,
        }
        await db.playlists.insert_one(playlist)
        return serialize_doc(playlist)

    @router.post("/menus")
    async def create_menu(data: dict, current_user: dict = Depends(get_current_user)):
        """Create a new digital menu with pre-populated professional content."""
        template_id = data.get("template_id", "classic")

        # Pre-populated content per template
        TEMPLATE_CONTENT = {
            "classic": [
                {"name": "Starters", "description": "Begin your culinary journey", "items": [
                    {"name": "French Onion Soup", "description": "Caramelized onions, gruyère cheese, toasted baguette", "price": 14.00, "featured": True},
                    {"name": "Tuna Tartare", "description": "Fresh ahi tuna, avocado, sesame, citrus vinaigrette", "price": 18.00},
                    {"name": "Caesar Salad", "description": "Romaine hearts, parmesan, anchovies, house croutons", "price": 13.00},
                    {"name": "Shrimp Cocktail", "description": "Jumbo shrimp, classic cocktail sauce, lemon", "price": 16.00},
                    {"name": "Bruschetta", "description": "Heirloom tomatoes, basil, balsamic glaze, garlic crostini", "price": 12.00},
                ]},
                {"name": "Main Course", "description": "Signature dishes from our chef", "items": [
                    {"name": "Filet Mignon", "description": "8oz center cut, truffle mashed potatoes, asparagus, red wine jus", "price": 48.00, "featured": True},
                    {"name": "Pan-Seared Salmon", "description": "Atlantic salmon, lemon butter, seasonal vegetables, rice pilaf", "price": 34.00},
                    {"name": "Lobster Tail", "description": "Butter-poached Maine lobster, drawn butter, roasted potatoes", "price": 52.00},
                    {"name": "Rack of Lamb", "description": "Herb-crusted lamb, mint pesto, roasted root vegetables", "price": 44.00},
                    {"name": "Chicken Cordon Bleu", "description": "Stuffed with ham & swiss, dijon cream sauce, haricots verts", "price": 28.00},
                    {"name": "Risotto Primavera", "description": "Arborio rice, seasonal vegetables, parmesan, white truffle oil", "price": 26.00},
                ]},
                {"name": "Desserts", "description": "Sweet endings", "items": [
                    {"name": "Crème Brûlée", "description": "Classic vanilla bean custard, caramelized sugar", "price": 12.00, "featured": True},
                    {"name": "Chocolate Fondant", "description": "Warm chocolate cake, molten center, vanilla ice cream", "price": 14.00},
                    {"name": "Tiramisu", "description": "Mascarpone, espresso-soaked ladyfingers, cocoa", "price": 12.00},
                    {"name": "Cheesecake", "description": "New York style, berry compote, whipped cream", "price": 11.00},
                ]},
                {"name": "Beverages", "description": "Curated selection", "items": [
                    {"name": "House Wine (Glass)", "description": "Red or White, ask your server for today's selection", "price": 12.00},
                    {"name": "Craft Cocktail", "description": "Classic or seasonal, crafted by our mixologist", "price": 16.00},
                    {"name": "Sparkling Water", "description": "San Pellegrino 750ml", "price": 6.00},
                    {"name": "Espresso", "description": "Double shot, Italian roast", "price": 5.00},
                ]},
            ],
            "modern": [
                {"name": "Brunch", "description": "Available until 3 PM", "items": [
                    {"name": "Avocado Toast", "description": "Sourdough, smashed avo, poached egg, microgreens, chili flakes", "price": 14.00, "featured": True},
                    {"name": "Acai Bowl", "description": "Organic acai, granola, banana, blueberries, honey drizzle", "price": 13.00},
                    {"name": "Eggs Benedict", "description": "Poached eggs, Canadian bacon, hollandaise, English muffin", "price": 16.00},
                    {"name": "Pancake Stack", "description": "Fluffy buttermilk pancakes, maple syrup, fresh berries", "price": 12.00},
                    {"name": "Smoked Salmon Bagel", "description": "Cream cheese, capers, red onion, fresh dill", "price": 15.00},
                ]},
                {"name": "Sandwiches & Wraps", "description": "Served with side salad or fries", "items": [
                    {"name": "Club Sandwich", "description": "Turkey, bacon, lettuce, tomato, mayo, toasted sourdough", "price": 15.00},
                    {"name": "Grilled Chicken Wrap", "description": "Grilled chicken, avocado, ranch, mixed greens, tortilla", "price": 14.00},
                    {"name": "Caprese Panini", "description": "Fresh mozzarella, tomato, basil, pesto, ciabatta", "price": 13.00, "featured": True},
                    {"name": "Tuna Melt", "description": "Albacore tuna salad, cheddar, tomato, grilled rye", "price": 13.00},
                ]},
                {"name": "Coffee & Drinks", "description": "Specialty coffee & fresh juices", "items": [
                    {"name": "Flat White", "description": "Double espresso, steamed milk, microfoam", "price": 5.50},
                    {"name": "Matcha Latte", "description": "Ceremonial grade matcha, oat milk, honey", "price": 6.00, "featured": True},
                    {"name": "Fresh Orange Juice", "description": "Freshly squeezed, no sugar added", "price": 6.00},
                    {"name": "Iced Americano", "description": "Double shot espresso over ice", "price": 4.50},
                    {"name": "Smoothie", "description": "Mango, banana, spinach, almond milk", "price": 7.00},
                ]},
                {"name": "Pastries", "description": "Baked fresh daily", "items": [
                    {"name": "Croissant", "description": "Butter croissant, flaky & golden", "price": 4.00},
                    {"name": "Blueberry Muffin", "description": "Jumbo muffin, fresh blueberries, streusel top", "price": 4.50},
                    {"name": "Cinnamon Roll", "description": "Warm, cream cheese frosting", "price": 5.00, "featured": True},
                ]},
            ],
            "fastfood": [
                {"name": "Burgers", "description": "100% Angus beef patties", "items": [
                    {"name": "Classic Burger", "description": "Beef patty, lettuce, tomato, onion, pickles, special sauce", "price": 9.99, "featured": True, "image": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=300&h=300&fit=crop"},
                    {"name": "Double Cheeseburger", "description": "Two patties, American cheese, lettuce, tomato, mayo", "price": 12.99, "image": "https://images.unsplash.com/photo-1553979459-d2229ba7433b?w=300&h=300&fit=crop"},
                    {"name": "Bacon BBQ Burger", "description": "Crispy bacon, BBQ sauce, onion rings, cheddar", "price": 13.99, "featured": True, "image": "https://images.unsplash.com/photo-1594212699903-ec8a3eca50f5?w=300&h=300&fit=crop"},
                    {"name": "Mushroom Swiss", "description": "Sauteed mushrooms, swiss cheese, garlic aioli", "price": 12.99, "image": "https://images.unsplash.com/photo-1572802419224-296b0aeee0d9?w=300&h=300&fit=crop"},
                    {"name": "Veggie Burger", "description": "Plant-based patty, lettuce, tomato, vegan mayo", "price": 11.99, "image": "https://images.unsplash.com/photo-1520072959219-c595dc870360?w=300&h=300&fit=crop"},
                ]},
                {"name": "Chicken", "description": "Crispy & juicy", "items": [
                    {"name": "Chicken Tenders (6pc)", "description": "Hand-breaded, served with dipping sauce", "price": 8.99, "image": "https://images.unsplash.com/photo-1562967914-608f82629710?w=300&h=300&fit=crop"},
                    {"name": "Spicy Chicken Sandwich", "description": "Crispy chicken, spicy mayo, pickles, brioche bun", "price": 10.99, "featured": True, "image": "https://images.unsplash.com/photo-1606755962773-d324e0a13086?w=300&h=300&fit=crop"},
                    {"name": "Chicken Wings (10pc)", "description": "Buffalo, BBQ, or Garlic Parmesan", "price": 12.99, "image": "https://images.unsplash.com/photo-1567620832903-9fc6debc209f?w=300&h=300&fit=crop"},
                ]},
                {"name": "Sides", "description": "Perfect additions", "items": [
                    {"name": "French Fries", "description": "Golden crispy, seasoned", "price": 3.99, "image": "https://images.unsplash.com/photo-1573080496219-bb080dd4f877?w=300&h=300&fit=crop"},
                    {"name": "Onion Rings", "description": "Beer-battered, crispy", "price": 4.99, "image": "https://images.unsplash.com/photo-1639024471283-03518883512d?w=300&h=300&fit=crop"},
                    {"name": "Mozzarella Sticks", "description": "Breaded mozzarella, marinara sauce", "price": 5.99},
                    {"name": "Loaded Nachos", "description": "Tortilla chips, cheese, jalapeños, sour cream, guacamole", "price": 8.99, "image": "https://images.unsplash.com/photo-1513456852971-30c0b8199d4d?w=300&h=300&fit=crop"},
                ]},
                {"name": "Drinks & Shakes", "description": "Ice cold refreshments", "items": [
                    {"name": "Soft Drink", "description": "Coca-Cola, Sprite, Fanta - Regular or Large", "price": 2.99},
                    {"name": "Milkshake", "description": "Vanilla, Chocolate, or Strawberry", "price": 5.99, "featured": True, "image": "https://images.unsplash.com/photo-1572490122747-3968b75cc699?w=300&h=300&fit=crop"},
                    {"name": "Lemonade", "description": "Fresh squeezed, sweetened", "price": 3.49},
                ]},
                {"name": "Combos", "description": "Best value meals", "items": [
                    {"name": "Combo #1", "description": "Classic Burger + Fries + Drink", "price": 13.99, "featured": True, "image": "https://images.unsplash.com/photo-1550547660-d9450f859349?w=300&h=300&fit=crop"},
                    {"name": "Combo #2", "description": "Double Cheeseburger + Fries + Drink", "price": 16.99},
                    {"name": "Combo #3", "description": "Chicken Tenders + Fries + Drink", "price": 12.99},
                    {"name": "Family Combo", "description": "4 Burgers + 4 Fries + 4 Drinks", "price": 44.99},
                ]},
            ],
            "mexican": [
                {"name": "Antojitos", "description": "Para empezar", "items": [
                    {"name": "Guacamole Fresco", "description": "Aguacate, cilantro, cebolla, jalapeño, limón, totopos", "price": 10.99, "featured": True, "image": "https://images.unsplash.com/photo-1615870216519-2f9fa575fa5c?w=300&h=300&fit=crop"},
                    {"name": "Queso Fundido", "description": "Queso Oaxaca derretido, chorizo, tortillas de maíz", "price": 11.99, "image": "https://images.unsplash.com/photo-1618449840665-9ed506d73a34?w=300&h=300&fit=crop"},
                    {"name": "Elote Callejero", "description": "Maíz asado, mayonesa, queso cotija, chile, limón", "price": 6.99, "image": "https://images.unsplash.com/photo-1551504734-5ee1c4a1479b?w=300&h=300&fit=crop"},
                    {"name": "Nachos Supreme", "description": "Totopos, frijoles, queso, jalapeños, crema, guacamole", "price": 12.99, "image": "https://images.unsplash.com/photo-1513456852971-30c0b8199d4d?w=300&h=300&fit=crop"},
                    {"name": "Ceviche de Camarón", "description": "Camarón fresco, limón, tomate, cebolla, aguacate, tostadas", "price": 14.99, "image": "https://images.unsplash.com/photo-1535399831218-d5bd36d1a6b3?w=300&h=300&fit=crop"},
                ]},
                {"name": "Tacos", "description": "Servidos con cebolla, cilantro y salsa", "items": [
                    {"name": "Tacos al Pastor (3)", "description": "Cerdo marinado, piña, cebolla, cilantro", "price": 11.99, "featured": True, "image": "https://images.unsplash.com/photo-1551504734-5ee1c4a1479b?w=300&h=300&fit=crop"},
                    {"name": "Tacos de Carne Asada (3)", "description": "Res a la parrilla, guacamole, cebolla", "price": 13.99, "image": "https://images.unsplash.com/photo-1599974579688-8dbdd335c77f?w=300&h=300&fit=crop"},
                    {"name": "Tacos de Pollo (3)", "description": "Pollo asado, lechuga, crema, queso fresco", "price": 11.99, "image": "https://images.unsplash.com/photo-1624300629298-e9de39c13be5?w=300&h=300&fit=crop"},
                    {"name": "Tacos de Camarón (3)", "description": "Camarón empanizado, chipotle mayo, repollo", "price": 14.99, "image": "https://images.unsplash.com/photo-1611250188496-e966043a0629?w=300&h=300&fit=crop"},
                    {"name": "Tacos de Birria (3)", "description": "Res estofada, consomé, cebolla, cilantro", "price": 14.99, "featured": True, "image": "https://images.unsplash.com/photo-1640719028782-8230f1bdc755?w=300&h=300&fit=crop"},
                ]},
                {"name": "Platos Fuertes", "description": "Especialidades de la casa", "items": [
                    {"name": "Enchiladas Suizas", "description": "Tortillas rellenas de pollo, salsa verde, crema, queso gratinado", "price": 16.99, "image": "https://images.unsplash.com/photo-1534352956036-cd81e27dd615?w=300&h=300&fit=crop"},
                    {"name": "Burrito Grande", "description": "Tortilla de harina, arroz, frijoles, carne, queso, crema, guacamole", "price": 14.99, "featured": True, "image": "https://images.unsplash.com/photo-1626700051175-6818013e1d4f?w=300&h=300&fit=crop"},
                    {"name": "Chile Relleno", "description": "Chile poblano relleno de queso, salsa de tomate, arroz, frijoles", "price": 15.99},
                    {"name": "Fajitas Mixtas", "description": "Res y pollo, pimientos, cebolla, tortillas, arroz, frijoles", "price": 19.99, "image": "https://images.unsplash.com/photo-1625398407796-82650a8c135f?w=300&h=300&fit=crop"},
                    {"name": "Mole Poblano", "description": "Pollo en mole tradicional, ajonjolí, arroz, tortillas", "price": 17.99},
                ]},
                {"name": "Bebidas", "description": "Refrescantes", "items": [
                    {"name": "Margarita", "description": "Tequila, triple sec, limón fresco - Clásica o de Mango", "price": 10.99, "featured": True},
                    {"name": "Agua de Horchata", "description": "Bebida de arroz, canela, vainilla", "price": 3.99},
                    {"name": "Jamaica", "description": "Agua de flor de jamaica, endulzada", "price": 3.99},
                    {"name": "Michelada", "description": "Cerveza, limón, chamoy, chile, sal", "price": 8.99},
                    {"name": "Mexican Coke", "description": "Coca-Cola de vidrio, hecha con azúcar de caña", "price": 3.49},
                ]},
                {"name": "Postres", "description": "Dulce final", "items": [
                    {"name": "Churros con Chocolate", "description": "Churros crujientes, azúcar y canela, salsa de chocolate", "price": 7.99, "featured": True},
                    {"name": "Flan Napolitano", "description": "Flan de vainilla, caramelo", "price": 6.99},
                    {"name": "Tres Leches", "description": "Pastel bañado en tres leches, crema batida, canela", "price": 7.99},
                ]},
            ],
            "sushi": [
                {"name": "Appetizers", "description": "To start your experience", "items": [
                    {"name": "Edamame", "description": "Steamed soybeans, sea salt", "price": 6.00},
                    {"name": "Miso Soup", "description": "Traditional dashi broth, tofu, wakame, scallions", "price": 5.00},
                    {"name": "Gyoza (6pc)", "description": "Pan-fried pork dumplings, ponzu sauce", "price": 9.00},
                    {"name": "Tuna Tataki", "description": "Seared ahi tuna, ginger sauce, microgreens", "price": 14.00, "featured": True},
                    {"name": "Shrimp Tempura", "description": "Lightly battered shrimp, tempura sauce", "price": 12.00},
                ]},
                {"name": "Signature Rolls", "description": "Chef's special creations", "items": [
                    {"name": "Dragon Roll", "description": "Shrimp tempura, avocado on top, eel sauce, sesame", "price": 16.00, "featured": True},
                    {"name": "Rainbow Roll", "description": "California roll topped with assorted sashimi", "price": 18.00},
                    {"name": "Spicy Tuna Roll", "description": "Fresh tuna, spicy mayo, cucumber, sesame", "price": 14.00},
                    {"name": "Philadelphia Roll", "description": "Smoked salmon, cream cheese, cucumber, avocado", "price": 13.00},
                    {"name": "Volcano Roll", "description": "Crab, avocado inside, baked seafood on top, spicy mayo", "price": 17.00, "featured": True},
                    {"name": "Spider Roll", "description": "Soft shell crab, cucumber, avocado, spicy mayo", "price": 16.00},
                ]},
                {"name": "Sashimi & Nigiri", "description": "Fresh cuts, premium quality", "items": [
                    {"name": "Salmon Sashimi (5pc)", "description": "Fresh Atlantic salmon", "price": 14.00},
                    {"name": "Tuna Sashimi (5pc)", "description": "Premium bluefin tuna", "price": 16.00, "featured": True},
                    {"name": "Mixed Sashimi (12pc)", "description": "Chef's selection of premium fish", "price": 28.00},
                    {"name": "Nigiri Set (8pc)", "description": "Assorted nigiri, chef's choice", "price": 22.00},
                ]},
                {"name": "Drinks", "description": "Japanese beverages", "items": [
                    {"name": "Hot Sake", "description": "Traditional Japanese rice wine", "price": 8.00},
                    {"name": "Sapporo Beer", "description": "Japanese lager, draft", "price": 6.00},
                    {"name": "Green Tea", "description": "Hot or iced sencha", "price": 3.00},
                    {"name": "Ramune Soda", "description": "Japanese marble soda, assorted flavors", "price": 4.00},
                ]},
            ],
            "pizza": [
                {"name": "Antipasti", "description": "Per iniziare", "items": [
                    {"name": "Bruschetta Classica", "description": "Toasted bread, tomatoes, garlic, fresh basil, olive oil", "price": 9.00},
                    {"name": "Caprese Salad", "description": "Buffalo mozzarella, heirloom tomatoes, basil, balsamic", "price": 12.00, "featured": True},
                    {"name": "Arancini (4pc)", "description": "Fried risotto balls, marinara sauce", "price": 10.00},
                    {"name": "Garlic Knots (6pc)", "description": "Fresh dough, garlic butter, parmesan, marinara", "price": 7.00},
                ]},
                {"name": "Pizzas", "description": "Wood-fired, hand-tossed", "items": [
                    {"name": "Margherita", "description": "San Marzano tomatoes, fresh mozzarella, basil, olive oil", "price": 14.00, "featured": True},
                    {"name": "Pepperoni", "description": "Mozzarella, pepperoni, tomato sauce", "price": 16.00},
                    {"name": "Quattro Formaggi", "description": "Mozzarella, gorgonzola, fontina, parmesan", "price": 17.00},
                    {"name": "Diavola", "description": "Spicy salami, mozzarella, chili flakes, tomato sauce", "price": 16.00},
                    {"name": "Prosciutto e Rucola", "description": "Prosciutto di Parma, arugula, parmesan shavings, truffle oil", "price": 18.00, "featured": True},
                    {"name": "Vegetariana", "description": "Grilled vegetables, mozzarella, pesto, cherry tomatoes", "price": 15.00},
                    {"name": "Hawaiian", "description": "Ham, pineapple, mozzarella, tomato sauce", "price": 15.00},
                ]},
                {"name": "Pasta", "description": "Fatto in casa", "items": [
                    {"name": "Spaghetti Bolognese", "description": "Slow-cooked meat sauce, parmesan", "price": 15.00},
                    {"name": "Fettuccine Alfredo", "description": "Cream sauce, parmesan, butter", "price": 14.00},
                    {"name": "Penne Arrabbiata", "description": "Spicy tomato sauce, garlic, chili, basil", "price": 13.00},
                    {"name": "Lasagna", "description": "Layered pasta, meat sauce, béchamel, mozzarella", "price": 16.00, "featured": True},
                ]},
                {"name": "Dolci & Bevande", "description": "Desserts & Drinks", "items": [
                    {"name": "Tiramisu", "description": "Classic Italian dessert, mascarpone, espresso", "price": 9.00, "featured": True},
                    {"name": "Panna Cotta", "description": "Vanilla cream, berry coulis", "price": 8.00},
                    {"name": "Italian Soda", "description": "Assorted flavors, sparkling water, cream", "price": 4.00},
                    {"name": "Espresso", "description": "Double shot, Italian roast", "price": 3.50},
                    {"name": "House Wine", "description": "Red: Chianti / White: Pinot Grigio - Glass", "price": 9.00},
                ]},
            ],
            "bar": [
                {"name": "Signature Cocktails", "description": "Crafted by our mixologists", "items": [
                    {"name": "Midnight Mule", "description": "Premium vodka, ginger beer, activated charcoal, lime", "price": 14.00, "featured": True},
                    {"name": "Smoky Old Fashioned", "description": "Bourbon, smoked maple syrup, aromatic bitters, orange peel", "price": 16.00, "featured": True},
                    {"name": "Lavender Martini", "description": "Gin, lavender syrup, lemon, egg white foam", "price": 15.00},
                    {"name": "Tropical Sunset", "description": "Rum, passion fruit, mango, coconut cream, pineapple", "price": 14.00},
                    {"name": "Espresso Martini", "description": "Vodka, Kahlúa, fresh espresso, vanilla", "price": 15.00},
                    {"name": "Mojito Royale", "description": "White rum, mint, lime, sugar cane, soda, prosecco float", "price": 14.00},
                ]},
                {"name": "Classic Cocktails", "description": "Timeless favorites", "items": [
                    {"name": "Margarita", "description": "Tequila, Cointreau, fresh lime juice, salt rim", "price": 12.00},
                    {"name": "Negroni", "description": "Gin, Campari, sweet vermouth, orange twist", "price": 13.00},
                    {"name": "Whiskey Sour", "description": "Bourbon, lemon juice, simple syrup, egg white", "price": 12.00},
                    {"name": "Manhattan", "description": "Rye whiskey, sweet vermouth, Angostura bitters, cherry", "price": 14.00},
                    {"name": "Piña Colada", "description": "Rum, coconut cream, pineapple juice, blended", "price": 12.00},
                ]},
                {"name": "Bar Bites", "description": "Perfect pairings", "items": [
                    {"name": "Truffle Fries", "description": "Crispy fries, truffle oil, parmesan, herbs", "price": 10.00, "featured": True},
                    {"name": "Wagyu Sliders (3)", "description": "Mini wagyu burgers, caramelized onion, gruyère", "price": 18.00},
                    {"name": "Tuna Poke Nachos", "description": "Wonton chips, ahi tuna, avocado, sriracha mayo", "price": 15.00},
                    {"name": "Charcuterie Board", "description": "Cured meats, artisan cheeses, crackers, honeycomb", "price": 22.00},
                    {"name": "Wings (10pc)", "description": "Korean BBQ or Buffalo, celery, blue cheese", "price": 14.00},
                ]},
                {"name": "Beer & Wine", "description": "Curated selection", "items": [
                    {"name": "Draft Beer", "description": "Ask your server for today's rotating selection", "price": 7.00},
                    {"name": "Craft IPA", "description": "Local craft IPA, hoppy & refreshing", "price": 8.00},
                    {"name": "Red Wine (Glass)", "description": "Cabernet Sauvignon / Malbec", "price": 12.00},
                    {"name": "White Wine (Glass)", "description": "Chardonnay / Sauvignon Blanc", "price": 11.00},
                    {"name": "Champagne (Glass)", "description": "French brut, perfect for celebrations", "price": 15.00},
                ]},
            ],
            "healthy": [
                {"name": "Bowls", "description": "Nutritious & delicious", "items": [
                    {"name": "Buddha Bowl", "description": "Quinoa, roasted sweet potato, chickpeas, avocado, tahini dressing", "price": 14.00, "featured": True},
                    {"name": "Açaí Bowl", "description": "Organic açaí, granola, banana, berries, coconut, honey", "price": 13.00},
                    {"name": "Poke Bowl", "description": "Brown rice, fresh salmon, edamame, cucumber, avocado, ponzu", "price": 16.00},
                    {"name": "Mediterranean Bowl", "description": "Falafel, hummus, tabbouleh, mixed greens, tzatziki", "price": 14.00, "featured": True},
                    {"name": "Protein Power Bowl", "description": "Grilled chicken, brown rice, broccoli, sweet potato, teriyaki", "price": 15.00},
                ]},
                {"name": "Salads", "description": "Fresh & crisp", "items": [
                    {"name": "Kale Caesar", "description": "Organic kale, vegan caesar dressing, hemp seeds, croutons", "price": 12.00},
                    {"name": "Cobb Salad", "description": "Grilled chicken, avocado, bacon, egg, blue cheese, ranch", "price": 14.00},
                    {"name": "Asian Sesame", "description": "Mixed greens, mandarin, almonds, crispy wontons, sesame dressing", "price": 13.00, "featured": True},
                    {"name": "Harvest Salad", "description": "Arugula, roasted beets, goat cheese, walnuts, balsamic", "price": 13.00},
                ]},
                {"name": "Smoothies & Juices", "description": "Cold-pressed, fresh daily", "items": [
                    {"name": "Green Machine", "description": "Spinach, kale, banana, mango, almond milk", "price": 8.00, "featured": True},
                    {"name": "Berry Blast", "description": "Strawberry, blueberry, raspberry, yogurt, honey", "price": 8.00},
                    {"name": "Tropical Paradise", "description": "Mango, pineapple, coconut water, turmeric", "price": 8.00},
                    {"name": "Detox Juice", "description": "Celery, cucumber, green apple, ginger, lemon", "price": 7.00},
                    {"name": "Protein Shake", "description": "Whey protein, banana, peanut butter, oat milk", "price": 9.00},
                ]},
                {"name": "Wraps & Toasts", "description": "Light & satisfying", "items": [
                    {"name": "Avocado Toast", "description": "Multigrain bread, smashed avo, cherry tomatoes, microgreens, seeds", "price": 11.00, "featured": True},
                    {"name": "Turkey Lettuce Wrap", "description": "Ground turkey, Asian sauce, water chestnuts, butter lettuce", "price": 13.00},
                    {"name": "Hummus Veggie Wrap", "description": "Whole wheat wrap, hummus, roasted veggies, feta, spinach", "price": 12.00},
                ]},
            ],
        }

        # Build categories with IDs
        # New visual templates reuse fastfood content with photos
        if template_id in ("mcdonalds", "modern_visual", "premium_dark"):
            template_cats = TEMPLATE_CONTENT.get("fastfood", TEMPLATE_CONTENT["classic"])
        else:
            template_cats = TEMPLATE_CONTENT.get(template_id, TEMPLATE_CONTENT["classic"])
        categories = []
        for i, cat_data in enumerate(template_cats):
            items = []
            for j, item_data in enumerate(cat_data.get("items", [])):
                items.append({
                    "id": gen_id(),
                    "name": item_data["name"],
                    "description": item_data.get("description", ""),
                    "price": item_data.get("price", 0),
                    "image": item_data.get("image", ""),
                    "featured": item_data.get("featured", False),
                    "available": True,
                    "order": j
                })
            categories.append({
                "id": gen_id(),
                "name": cat_data["name"],
                "description": cat_data.get("description", ""),
                "items": items,
                "order": i
            })

        menu = {
            "id": gen_id(),
            "user_id": current_user["id"],
            "name": data.get("name", "My Menu"),
            "template_id": template_id,
            "restaurant_name": data.get("restaurant_name", ""),
            "restaurant_logo": data.get("restaurant_logo", ""),
            "subtitle": data.get("subtitle", ""),
            "currency": data.get("currency", "USD"),
            "currency_symbol": data.get("currency_symbol", "$"),
            "theme": data.get("theme") or {},
            "categories": categories,
            "status": "draft",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        await db.menus.insert_one(menu)
        return serialize_doc(menu)

    @router.get("/menus")
    async def get_menus(current_user: dict = Depends(get_current_user)):
        """Get all menus for the current user (summary projection — excludes categories)."""
        if current_user.get("role") in ("admin", "superadmin"):
            query = {}
        else:
            query = {"user_id": current_user["id"]}

        # P0 PERF FIX: Use aggregation pipeline to return ONLY summary fields.
        # Previously: to_list(200) fetched full menu docs (categories + items = 10-50 KB each)
        #             → 200 menus × 50 KB = 10 MB over the wire → 25+ second response.
        # Now: project excludes categories; compute counts in MongoDB; < 1 KB per menu.
        pipeline = [
            {"$match": query},
            {"$sort": {"created_at": -1}},
            {"$limit": 200},
            {"$project": {
                "_id":              0,
                "id":               1,
                "name":             1,
                "restaurant_name":  1,
                "status":           1,
                "template_id":      1,
                "created_at":       1,
                "updated_at":       1,
                "category_count": {"$size": {"$ifNull": ["$categories", []]}},
                "item_count": {
                    "$sum": {
                        "$map": {
                            "input": {"$ifNull": ["$categories", []]},
                            "as": "cat",
                            "in": {"$size": {"$ifNull": ["$$cat.items", []]}}
                        }
                    }
                }
            }}
        ]
        menus = await db.menus.aggregate(pipeline).to_list(200)
        return serialize_doc(menus)

    @router.get("/menus/{menu_id}")
    async def get_menu(menu_id: str, current_user: dict = Depends(get_current_user)):
        """Get a specific menu with all its data."""
        menu = await db.menus.find_one({"id": menu_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
        return serialize_doc(menu)

    @router.put("/menus/{menu_id}")
    async def update_menu(menu_id: str, data: dict, current_user: dict = Depends(get_current_user)):
        """Update menu settings."""
        menu = await db.menus.find_one({"id": menu_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")

        update = {"updated_at": datetime.utcnow()}
        for field in ["name", "template_id", "restaurant_name", "restaurant_logo", "subtitle",
                      "currency", "currency_symbol", "status", "categories",
                      "slideshow_enabled", "slideshow_interval",
                      "split_screen_enabled", "split_screen_layout",
                      "split_promo_media", "split_widget_id", "theme"]:
            if field in data:
                update[field] = data[field]

        await db.menus.update_one({"id": menu_id}, {"$set": update})
        updated = await db.menus.find_one({"id": menu_id})
        await _notify_menu_change(menu_id)
        return serialize_doc(updated)

    @router.delete("/menus/{menu_id}")
    async def delete_menu(menu_id: str, current_user: dict = Depends(get_current_user)):
        """Delete a menu."""
        menu = await db.menus.find_one({"id": menu_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
        used_by = await db.playlists.find(
            {"items": {"$elemMatch": {"type": "menu", "ref_id": menu_id}}},
            {"_id": 0, "id": 1, "name": 1, "status": 1},
        ).to_list(200)
        if used_by:
            raise HTTPException(status_code=409, detail={
                "message": f"This menu is used by {len(used_by)} playlist(s). Remove it from those playlists first.",
                "used_by": used_by,
            })
        await db.menus.delete_one({"id": menu_id})
        return {"message": "Menu deleted"}

    @router.post("/menus/{menu_id}/categories")
    async def add_menu_category(menu_id: str, data: dict, current_user: dict = Depends(get_current_user)):
        """Add a category to a menu."""
        menu = await db.menus.find_one({"id": menu_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")

        category = {
            "id": gen_id(),
            "name": data.get("name", "Category"),
            "description": data.get("description", ""),
            "items": [],
            "order": len(menu.get("categories", [])),
            "active_hours": data.get("active_hours", None),  # {"start":"HH:MM","end":"HH:MM","days":[1,1,1,1,1,1,1]}
        }

        await db.menus.update_one({"id": menu_id}, {"$push": {"categories": category}, "$set": {"updated_at": datetime.utcnow()}})
        updated = await db.menus.find_one({"id": menu_id})
        await _notify_menu_change(menu_id)
        return serialize_doc(updated)

    @router.put("/menus/{menu_id}/categories/{category_id}")
    async def update_menu_category(menu_id: str, category_id: str, data: dict, current_user: dict = Depends(get_current_user)):
        """Update a category in a menu."""
        menu = await db.menus.find_one({"id": menu_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")

        categories = menu.get("categories", [])
        for cat in categories:
            if cat["id"] == category_id:
                if "name" in data: cat["name"] = data["name"]
                if "description" in data: cat["description"] = data["description"]
                break

        await db.menus.update_one({"id": menu_id}, {"$set": {"categories": categories, "updated_at": datetime.utcnow()}})
        await _notify_menu_change(menu_id)
        updated = await db.menus.find_one({"id": menu_id})
        return serialize_doc(updated)

    @router.delete("/menus/{menu_id}/categories/{category_id}")
    async def delete_menu_category(menu_id: str, category_id: str, current_user: dict = Depends(get_current_user)):
        """Delete a category from a menu."""
        menu = await db.menus.find_one({"id": menu_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")

        categories = [c for c in menu.get("categories", []) if c["id"] != category_id]
        await db.menus.update_one({"id": menu_id}, {"$set": {"categories": categories, "updated_at": datetime.utcnow()}})
        await _notify_menu_change(menu_id)
        return {"message": "Category deleted"}

    @router.post("/menus/{menu_id}/categories/{category_id}/items")
    async def add_menu_item(menu_id: str, category_id: str, data: dict, current_user: dict = Depends(get_current_user)):
        """Add an item to a category in a menu."""
        menu = await db.menus.find_one({"id": menu_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")

        item = {
            "id": gen_id(),
            "name": data.get("name", "Item"),
            "description": data.get("description", ""),
            "price": data.get("price", 0),
            "image": data.get("image", ""),
            "featured": data.get("featured", False),
            "available": data.get("available", True),
            "order": 0
        }

        categories = menu.get("categories", [])
        for cat in categories:
            if cat["id"] == category_id:
                item["order"] = len(cat.get("items", []))
                cat.setdefault("items", []).append(item)
                break

        await db.menus.update_one({"id": menu_id}, {"$set": {"categories": categories, "updated_at": datetime.utcnow()}})
        await _notify_menu_change(menu_id)
        updated = await db.menus.find_one({"id": menu_id})
        return serialize_doc(updated)

    @router.put("/menus/{menu_id}/categories/{category_id}/items/{item_id}")
    async def update_menu_item(menu_id: str, category_id: str, item_id: str, data: dict, current_user: dict = Depends(get_current_user)):
        """Update a menu item."""
        menu = await db.menus.find_one({"id": menu_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")

        categories = menu.get("categories", [])
        for cat in categories:
            if cat["id"] == category_id:
                for it in cat.get("items", []):
                    if it["id"] == item_id:
                        for field in ["name", "description", "price", "image", "featured", "available"]:
                            if field in data: it[field] = data[field]
                        break
                break

        await db.menus.update_one({"id": menu_id}, {"$set": {"categories": categories, "updated_at": datetime.utcnow()}})
        await _notify_menu_change(menu_id)
        updated = await db.menus.find_one({"id": menu_id})
        return serialize_doc(updated)

    @router.delete("/menus/{menu_id}/categories/{category_id}/items/{item_id}")
    async def delete_menu_item(menu_id: str, category_id: str, item_id: str, current_user: dict = Depends(get_current_user)):
        """Delete a menu item."""
        menu = await db.menus.find_one({"id": menu_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")

        categories = menu.get("categories", [])
        for cat in categories:
            if cat["id"] == category_id:
                cat["items"] = [it for it in cat.get("items", []) if it["id"] != item_id]
                break

        await db.menus.update_one({"id": menu_id}, {"$set": {"categories": categories, "updated_at": datetime.utcnow()}})
        await _notify_menu_change(menu_id)
        return {"message": "Item deleted"}

    @router.post("/menus/{menu_id}/promo-media")
    async def add_promo_media(menu_id: str, data: dict, current_user: dict = Depends(get_current_user)):
        """Add promotional video/image to a menu."""
        menu = await db.menus.find_one({"id": menu_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")

        media_item = {
            "id": gen_id(),
            "type": data.get("type", "image"),  # "image" or "video"
            "url": data.get("url", ""),
            "data": data.get("data", ""),  # base64 for uploads
            "title": data.get("title", ""),
            "order": len(menu.get("promo_media", []))
        }

        await db.menus.update_one({"id": menu_id}, {
            "$push": {"promo_media": media_item},
            "$set": {"updated_at": datetime.utcnow()}
        })
        await _notify_menu_change(menu_id)
        updated = await db.menus.find_one({"id": menu_id})
        return serialize_doc(updated)

    @router.delete("/menus/{menu_id}/promo-media/{media_id}")
    async def delete_promo_media(menu_id: str, media_id: str, current_user: dict = Depends(get_current_user)):
        """Remove promotional media from a menu."""
        menu = await db.menus.find_one({"id": menu_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")
        if current_user.get("role") not in ("admin", "superadmin") and menu["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")

        promo_media = [m for m in menu.get("promo_media", []) if m["id"] != media_id]
        await db.menus.update_one({"id": menu_id}, {
            "$set": {"promo_media": promo_media, "updated_at": datetime.utcnow()}
        })
        await _notify_menu_change(menu_id)
        return {"message": "Promo media deleted"}

    @router.get("/menus/{menu_id}/render", response_class=HTMLResponse)
    async def render_menu(menu_id: str, request: Request, preview: str = ""):
        """Render a menu as a full-screen HTML page optimized for landscape LED displays.
        Features: 3-column max per slide, auto-slideshow, always-visible food images.
        H3: Only published menus render publicly. Drafts require owner/admin auth
        or a short-lived signed ?preview= token minted for the owner."""
        menu = await db.menus.find_one({"id": menu_id})
        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")

        # ── H3: Published-state gate ────────────────────────────────────────────────
        menu_status = menu.get("status", "draft")
        if menu_status not in ("published", "active"):
            # Draft/private menus require authenticated owner or admin for preview
            auth_header = request.headers.get("Authorization", "")
            _allowed = bool(preview) and verify_menu_preview_token(preview, menu_id)
            if auth_header.startswith("Bearer "):
                _token = auth_header[7:]
                try:
                    import jwt as _jwt_lib
                    _SECRET = os.environ.get("JWT_SECRET", "")
                    _payload = _jwt_lib.decode(_token, _SECRET, algorithms=["HS256"],
                                               options={"verify_aud": False, "verify_iss": False})
                    _uid = _payload.get("sub")
                    _u = await db.users.find_one({"id": _uid}) if _uid else None
                    if _u and _u.get("active", True):
                        _is_owner = menu.get("user_id") == _uid
                        _is_admin = _u.get("role") in ("admin", "superadmin") or \
                                    _u.get("rbac_role") in ("SUPER_ADMIN", "MEDIAVIEW_ADMIN")
                        if _is_owner or _is_admin:
                            _allowed = True
                except Exception:
                    pass
            if not _allowed:
                raise HTTPException(status_code=404, detail="Menu not found")

        template_id = menu.get("template_id", "classic")
        restaurant = menu.get("restaurant_name") or menu.get("name") or "Restaurant"
        subtitle = menu.get("subtitle", "")
        currency_sym = menu.get("currency_symbol", "$")
        categories = menu.get("categories") or []
        promo_media = menu.get("promo_media", [])

        # Workspace menus keep a FLAT item list plus category names as plain strings.
        # Group them into the {name, items[]} shape this renderer expects.
        flat_items = menu.get("items") or []
        if flat_items and (not categories or not isinstance(categories[0], dict)):
            grouped: dict[str, list] = {}
            for flat in flat_items:
                if not isinstance(flat, dict):
                    continue
                if not flat.get("available", True):
                    continue  # producto agotado: desaparece del menú
                group = str(flat.get("category") or "Menú")
                grouped.setdefault(group, []).append({
                    "name": flat.get("name") or "",
                    "description": flat.get("description") or "",
                    "price": flat.get("price") or 0,
                    "image": flat.get("image_url") or "",
                    "available": flat.get("available", True),
                    "featured": bool(flat.get("featured")),
                })
            categories = [{"name": name, "items": rows} for name, rows in grouped.items()]

        # Food emoji placeholders by keyword
        food_emojis = {
            "soup": "🍲", "salad": "🥗", "tuna": "🐟", "shrimp": "🦐", "bruschetta": "🍞", "bread": "🍞",
            "steak": "🥩", "filet": "🥩", "beef": "🥩", "carne": "🥩", "res": "🥩",
            "salmon": "🐟", "fish": "🐟", "lobster": "🦞", "lamb": "🍖", "rack": "🍖",
            "chicken": "🍗", "pollo": "🍗", "wing": "🍗", "tender": "🍗",
            "risotto": "🍚", "rice": "🍚", "arroz": "🍚",
            "creme": "🍮", "flan": "🍮", "custard": "🍮", "pudding": "🍮",
            "chocolate": "🍫", "cake": "🎂", "pastel": "🎂", "cheesecake": "🍰",
            "tiramisu": "🍰", "dessert": "🍰", "postre": "🍰", "churro": "🍩", "donut": "🍩",
            "wine": "🍷", "cocktail": "🍸", "margarita": "🍹", "beer": "🍺", "cerveza": "🍺",
            "coffee": "☕", "espresso": "☕", "latte": "☕", "cappuccino": "☕", "cafe": "☕",
            "tea": "🍵", "matcha": "🍵",
            "juice": "🧃", "smoothie": "🥤", "lemonade": "🍋", "soda": "🥤", "water": "💧",
            "shake": "🥛", "milk": "🥛", "horchata": "🥛",
            "burger": "🍔", "hamburger": "🍔",
            "pizza": "🍕", "margherita": "🍕",
            "pasta": "🍝", "spaghetti": "🍝", "fettuccine": "🍝", "penne": "🍝", "lasagna": "🍝",
            "taco": "🌮", "burrito": "🌯", "enchilada": "🌯", "quesadilla": "🌯",
            "nacho": "🧀", "queso": "🧀", "cheese": "🧀",
            "guacamole": "🥑", "avocado": "🥑", "aguacate": "🥑",
            "fries": "🍟", "french": "🍟", "onion ring": "🧅",
            "sushi": "🍣", "roll": "🍣", "sashimi": "🍣", "nigiri": "🍣",
            "gyoza": "🥟", "dumpling": "🥟",
            "ramen": "🍜", "noodle": "🍜", "pho": "🍜",
            "egg": "🥚", "pancake": "🥞", "waffle": "🧇", "toast": "🍞",
            "croissant": "🥐", "muffin": "🧁", "cinnamon": "🧁", "pastry": "🧁",
            "sandwich": "🥪", "panini": "🥪", "wrap": "🌯", "bagel": "🥯",
            "ice cream": "🍦", "gelato": "🍦", "panna": "🍦",
            "elote": "🌽", "corn": "🌽", "maiz": "🌽",
            "ceviche": "🐟", "mole": "🫕", "chile": "🌶️", "jalapeno": "🌶️",
            "jamaica": "🌺", "michelada": "🍺",
            "edamame": "🫛", "miso": "🍲", "tempura": "🍤",
            "sake": "🍶", "ramune": "🍾",
            "arancini": "🧆", "garlic": "🧄", "knot": "🥨",
            "caprese": "🍅", "tomato": "🍅",
            "combo": "🍱", "family": "👨‍👩‍👧‍👦", "special": "⭐",
            "bowl": "🥣", "acai": "🫐", "poke": "🍣", "buddha": "🥗",
            "falafel": "🧆", "hummus": "🫘",
            "kale": "🥬", "spinach": "🥬", "lettuce": "🥬",
            "prosciutto": "🥓", "bacon": "🥓", "ham": "🥓",
            "truffle": "🍄", "mushroom": "🍄",
            "nachos": "🧀", "mozzarella": "🧀",
            "default": "🍽️"
        }

        def get_food_emoji(name):
            name_lower = name.lower()
            for keyword, emoji in food_emojis.items():
                if keyword in name_lower:
                    return emoji
            return food_emojis["default"]

        templates = {
            "classic": {"bg": "#1a1a2e", "bg2": "#16213e", "text": "#e2e8f0", "text2": "#94a3b8", "accent": "#d4af37", "cat_bg": "rgba(212,175,55,.08)", "item_bg": "rgba(255,255,255,.03)", "item_border": "rgba(212,175,55,.08)", "font": "'Playfair Display',Georgia,serif", "name_size": "48px", "featured_bg": "rgba(212,175,55,.06)", "img_bg": "rgba(212,175,55,.08)"},
            "modern": {"bg": "#f1f5f9", "bg2": "#e2e8f0", "text": "#1e293b", "text2": "#64748b", "accent": "#2563eb", "cat_bg": "rgba(37,99,235,.06)", "item_bg": "rgba(255,255,255,.9)", "item_border": "rgba(37,99,235,.1)", "font": "'Inter',sans-serif", "name_size": "40px", "featured_bg": "rgba(37,99,235,.05)", "img_bg": "rgba(37,99,235,.06)"},
            "fastfood": {"bg": "#fffbeb", "bg2": "#fef3c7", "text": "#1c1917", "text2": "#78716c", "accent": "#dc2626", "cat_bg": "rgba(220,38,38,.08)", "item_bg": "rgba(255,255,255,.7)", "item_border": "rgba(220,38,38,.1)", "font": "'Inter',sans-serif", "name_size": "44px", "featured_bg": "rgba(220,38,38,.05)", "img_bg": "rgba(220,38,38,.06)"},
            "mexican": {"bg": "#451a03", "bg2": "#3b1503", "text": "#fef3c7", "text2": "#d4a574", "accent": "#f59e0b", "cat_bg": "rgba(245,158,11,.1)", "item_bg": "rgba(255,255,255,.04)", "item_border": "rgba(245,158,11,.12)", "font": "'Inter',sans-serif", "name_size": "44px", "featured_bg": "rgba(245,158,11,.08)", "img_bg": "rgba(245,158,11,.1)"},
            "sushi": {"bg": "#0f172a", "bg2": "#1e293b", "text": "#e2e8f0", "text2": "#94a3b8", "accent": "#f43f5e", "cat_bg": "rgba(244,63,94,.06)", "item_bg": "rgba(255,255,255,.02)", "item_border": "rgba(244,63,94,.08)", "font": "'Inter',sans-serif", "name_size": "42px", "featured_bg": "rgba(244,63,94,.05)", "img_bg": "rgba(244,63,94,.06)"},
            "pizza": {"bg": "#1c1917", "bg2": "#292524", "text": "#fef2f2", "text2": "#a8a29e", "accent": "#dc2626", "cat_bg": "rgba(220,38,38,.08)", "item_bg": "rgba(255,255,255,.03)", "item_border": "rgba(220,38,38,.08)", "font": "'Inter',sans-serif", "name_size": "44px", "featured_bg": "rgba(220,38,38,.05)", "img_bg": "rgba(220,38,38,.06)"},
            "bar": {"bg": "#09090b", "bg2": "#18181b", "text": "#e2e8f0", "text2": "#71717a", "accent": "#a855f7", "cat_bg": "rgba(168,85,247,.07)", "item_bg": "rgba(255,255,255,.02)", "item_border": "rgba(168,85,247,.1)", "font": "'Inter',sans-serif", "name_size": "42px", "featured_bg": "rgba(168,85,247,.06)", "img_bg": "rgba(168,85,247,.08)"},
            "healthy": {"bg": "#f0fdf4", "bg2": "#dcfce7", "text": "#14532d", "text2": "#4ade80", "accent": "#16a34a", "cat_bg": "rgba(22,163,74,.06)", "item_bg": "rgba(255,255,255,.9)", "item_border": "rgba(22,163,74,.1)", "font": "'Inter',sans-serif", "name_size": "40px", "featured_bg": "rgba(22,163,74,.05)", "img_bg": "rgba(22,163,74,.06)"},
            "mcdonalds": {"bg": "#1c1917", "bg2": "#292524", "text": "#fef2f2", "text2": "#a8a29e", "accent": "#dc2626", "cat_bg": "rgba(220,38,38,.08)", "item_bg": "rgba(255,255,255,.03)", "item_border": "rgba(220,38,38,.08)", "font": "'Inter',sans-serif", "name_size": "44px", "featured_bg": "rgba(220,38,38,.05)", "img_bg": "rgba(220,38,38,.06)", "grid": True},
            "modern_visual": {"bg": "#0f172a", "bg2": "#1e293b", "text": "#e2e8f0", "text2": "#94a3b8", "accent": "#f59e0b", "cat_bg": "rgba(245,158,11,.06)", "item_bg": "rgba(255,255,255,.02)", "item_border": "rgba(245,158,11,.08)", "font": "'Inter',sans-serif", "name_size": "42px", "featured_bg": "rgba(245,158,11,.05)", "img_bg": "rgba(245,158,11,.06)", "grid": True},
            "premium_dark": {"bg": "#000000", "bg2": "#0a0a0a", "text": "#e2e8f0", "text2": "#71717a", "accent": "#d4af37", "cat_bg": "rgba(212,175,55,.06)", "item_bg": "rgba(255,255,255,.02)", "item_border": "rgba(212,175,55,.08)", "font": "'Playfair Display',Georgia,serif", "name_size": "44px", "featured_bg": "rgba(212,175,55,.05)", "img_bg": "rgba(212,175,55,.06)", "grid": True}
        }

        t = dict(templates.get(template_id, templates["classic"]))
        custom_theme = menu.get("theme") or {}
        for key in ("bg", "bg2", "text", "text2", "accent"):
            value = str(custom_theme.get(key) or "")
            if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                t[key] = value

        is_grid = t.get('grid', False)

        # -------- Time-based category filtering (Chat #2 feature) --------
        # Categories can define active_hours: {"start":"HH:MM","end":"HH:MM","days":[1,1,1,1,1,1,1]}
        # Filter out categories that shouldn't be shown at this hour on this weekday.
        try:
            import pytz as _pytz
            _tz = _pytz.timezone(os.getenv("MENU_TZ", "America/New_York"))
            _now = datetime.now(_tz)
            _hm = _now.hour * 60 + _now.minute
            _wd = _now.weekday()  # 0=Mon .. 6=Sun
            _filtered = []
            for _cat in categories:
                _ah = _cat.get("active_hours")
                if not _ah:
                    _filtered.append(_cat); continue
                _days = _ah.get("days") or [1]*7
                if len(_days) < 7:
                    _days = (_days + [1]*7)[:7]
                if not _days[_wd]:
                    continue
                _s = _ah.get("start", "00:00"); _e = _ah.get("end", "23:59")
                try:
                    _sh, _sm = map(int, _s.split(":")); _eh, _em = map(int, _e.split(":"))
                    _sm_ = _sh*60+_sm; _em_ = _eh*60+_em
                    # Overnight support: end < start means it wraps midnight
                    if _em_ < _sm_:
                        _ok = (_hm >= _sm_) or (_hm <= _em_)
                    else:
                        _ok = _sm_ <= _hm <= _em_
                except Exception:
                    _ok = True
                if _ok:
                    _filtered.append(_cat)
            # If schedule wipes everything, keep the first category to avoid an empty screen.
            if not _filtered and categories:
                _filtered = [categories[0]]
            categories = _filtered
        except Exception:
            pass

        # -------- Slideshow settings (menu-level override) --------
        slideshow_enabled = menu.get("slideshow_enabled", True)
        slideshow_interval = int(menu.get("slideshow_interval") or 12)

        # Split categories into slides of 3
        slides = []
        for i in range(0, len(categories), 3):
            slides.append(categories[i:i+3])
        if not slides:
            slides = [[]]

        num_slides = len(slides)
        slide_duration = slideshow_interval if slideshow_enabled else 999999

        has_promo = len(promo_media) > 0
        menu_height = "75%" if has_promo else "calc(100% - 80px)"
        promo_height = "25%" if has_promo else "0"

        html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Playfair+Display:wght@400;700;900&display=swap" rel="stylesheet">
    <style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    html,body{{width:100%;height:100%;overflow:hidden}}
    body{{background:{t['bg']};color:{t['text']};font-family:{t['font']}}}

    .menu-container{{width:100%;height:100%;display:flex;flex-direction:column}}

    .header{{text-align:center;padding:20px 40px 12px;flex-shrink:0;border-bottom:2px solid {t['accent']}25}}
    .restaurant-name{{font-size:{t['name_size']};font-weight:900;color:{t['accent']};letter-spacing:3px;text-transform:uppercase}}
    .subtitle{{font-size:15px;color:{t['text2']};margin-top:2px;letter-spacing:1px}}

    .slides-wrapper{{flex:1;position:relative;overflow:hidden}}
    .slide{{position:absolute;top:0;left:0;width:100%;height:100%;display:flex;gap:20px;padding:16px 28px;opacity:0;transition:opacity 0.8s ease}}
    .slide.active{{opacity:1}}

    .category{{flex:1;display:flex;flex-direction:column;min-width:0;background:{t['bg2']};border-radius:14px;border:1px solid {t['accent']}12;overflow:hidden}}
    .cat-header{{padding:12px 16px;background:{t['cat_bg']};border-bottom:1px solid {t['accent']}15;flex-shrink:0}}
    .cat-title{{font-size:18px;font-weight:800;color:{t['accent']};text-transform:uppercase;letter-spacing:3px;text-align:center}}
    .cat-desc{{font-size:10px;color:{t['text2']};text-align:center;margin-top:2px}}
    .cat-items{{flex:1;overflow-y:auto;padding:6px 8px;scrollbar-width:none}}
    .cat-items::-webkit-scrollbar{{display:none}}

    .item{{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:10px;margin-bottom:5px;border:1px solid {t['item_border']};background:{t['item_bg']}}}
    .item.featured{{background:{t['featured_bg']};border-color:{t['accent']}30}}

    .item-img{{width:56px;height:56px;border-radius:10px;object-fit:cover;flex-shrink:0;border:1px solid {t['accent']}20}}
    .item-emoji{{width:56px;height:56px;border-radius:10px;background:{t['img_bg']};flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:26px;border:1px solid {t['accent']}15}}

    .item-info{{flex:1;min-width:0}}
    .item-name{{font-size:13px;font-weight:700;line-height:1.2}}
    .item-desc{{font-size:9px;color:{t['text2']};margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
    .item-price{{font-size:17px;font-weight:900;color:{t['accent']};white-space:nowrap;flex-shrink:0}}
    .star{{color:{t['accent']};font-size:8px;margin-left:3px;font-weight:400}}
    .unavailable{{opacity:.35}}

    .grid-items{{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px;padding:8px}}
    .grid-card{{background:{t['item_bg']};border:1px solid {t['item_border']};border-radius:10px;overflow:hidden;text-align:center}}
    .grid-card.featured{{border-color:{t['accent']}30;background:{t['featured_bg']}}}
    .grid-card-img{{width:100%;height:100px;object-fit:cover}}
    .grid-card-emoji{{width:100%;height:100px;background:{t['img_bg']};display:flex;align-items:center;justify-content:center;font-size:40px}}
    .grid-card-info{{padding:8px}}
    .grid-card-name{{font-size:12px;font-weight:700;line-height:1.2;margin-bottom:4px}}
    .grid-card-price{{font-size:16px;font-weight:900;color:{t['accent']}}}

    .promo-strip{{height:160px;flex-shrink:0;display:flex;gap:12px;padding:10px 28px;overflow:hidden;border-top:2px solid {t['accent']}15;background:{t['bg2']}}}
    .promo-item{{flex-shrink:0;height:140px;border-radius:12px;overflow:hidden;border:1px solid {t['accent']}15;position:relative}}
    .promo-item img{{height:100%;width:auto;max-width:250px;object-fit:cover;display:block}}
    .promo-item video{{height:100%;width:auto;max-width:250px;object-fit:cover;display:block}}
    .promo-scroll{{display:flex;gap:12px;animation:promoScroll linear infinite}}
    @keyframes promoScroll{{0%{{transform:translateX(0)}}100%{{transform:translateX(-50%)}}}}

    .footer{{padding:6px 40px;display:flex;justify-content:space-between;align-items:center;flex-shrink:0;border-top:1px solid {t['accent']}10}}
    .footer-text{{font-size:10px;color:{t['text2']}}}
    .dots{{display:flex;gap:6px}}
    .dot{{width:8px;height:8px;border-radius:50%;background:{t['text2']}40;transition:all .3s}}
    .dot.active{{background:{t['accent']};width:20px;border-radius:4px}}
    </style></head><body>
    <div class="menu-container">
    <div class="header">
    <div class="restaurant-name">{_esc(restaurant)}</div>"""

        if subtitle:
            html += f'<div class="subtitle">{_esc(subtitle)}</div>'

        html += '</div><div class="slides-wrapper">'

        for si, slide_cats in enumerate(slides):
            active = ' active' if si == 0 else ''
            html += f'<div class="slide{active}" data-slide="{si}">'

            for cat in slide_cats:
                items = cat.get("items", [])
                html += '<div class="category"><div class="cat-header">'
                html += f'<div class="cat-title">{_esc(cat.get("name", ""))}</div>'
                if cat.get("description"):
                    html += f'<div class="cat-desc">{_esc(cat["description"])}</div>'
                html += '</div><div class="cat-items">' if not is_grid else '</div><div class="grid-items">'

                for it in items:
                    if is_grid:
                        # GRID CARD LAYOUT (McDonald's style)
                        cls = "grid-card"
                        if it.get("featured"): cls += " featured"
                        html += f'<div class="{cls}">'
                        if it.get("image"):
                            _img_src = _safe_src(it["image"])
                            if _img_src:
                                html += f'<img class="grid-card-img" src="{_img_src}" alt="" loading="lazy">'
                        else:
                            emoji = get_food_emoji(it.get("name", ""))
                            html += f'<div class="grid-card-emoji">{emoji}</div>'
                        html += '<div class="grid-card-info">'
                        html += f'<div class="grid-card-name">{_esc(it.get("name", ""))}</div>'
                        html += f'<div class="grid-card-price">{_esc(currency_sym)}{it.get("price", 0):.2f}</div>'
                        html += '</div></div>'
                    else:
                        # LIST LAYOUT (original)
                        cls = "item"
                        if it.get("featured"): cls += " featured"
                        if not it.get("available", True): cls += " unavailable"
                        html += f'<div class="{cls}">'
                        if it.get("image"):
                            _img_src = _safe_src(it["image"])
                            if _img_src:
                                html += f'<img class="item-img" src="{_img_src}" alt="" loading="lazy">'
                        else:
                            emoji = get_food_emoji(it.get("name", ""))
                            html += f'<div class="item-emoji">{emoji}</div>'
                        html += '<div class="item-info">'
                        html += f'<div class="item-name">{_esc(it.get("name", ""))}'
                        if it.get("featured"):
                            html += '<span class="star">★ ESPECIAL</span>'
                        html += '</div>'
                        if it.get("description"):
                            html += f'<div class="item-desc">{_esc(it["description"])}</div>'
                        html += f'</div><div class="item-price">{_esc(currency_sym)}{it.get("price", 0):.2f}</div></div>'

                html += '</div></div>'

            html += '</div>'

        html += '</div>'

        # Promo media strip
        if promo_media:
            if len(promo_media) == 1:
                # Single media: show full width, no scroll
                pm = promo_media[0]
                src = pm.get("data") or pm.get("url", "")
                if src:
                    _psrc = _safe_src(src)
                    html += '<div class="promo-strip" style="justify-content:center;padding:0">'
                    if pm.get("type") == "video":
                        html += f'<video src="{_psrc}" muted autoplay loop playsinline style="width:100%;height:100%;object-fit:cover"></video>'
                    else:
                        html += f'<img src="{_psrc}" style="width:100%;height:100%;object-fit:cover" alt="">'
                    html += '</div>'
            else:
                # Multiple media: scrolling strip
                html += '<div class="promo-strip"><div class="promo-scroll" id="promo-scroll">'
                for _ in range(2):
                    for pm in promo_media:
                        src = pm.get("data") or pm.get("url", "")
                        if not src:
                            continue
                        _psrc = _safe_src(src)
                        html += '<div class="promo-item">'
                        if pm.get("type") == "video":
                            html += f'<video src="{_psrc}" muted autoplay loop playsinline></video>'
                        else:
                            html += f'<img src="{_psrc}" alt="">'
                        html += '</div>'
                html += '</div></div>'

        # Footer
        html += '<div class="footer">'
        html += f'<div class="footer-text">{_esc(restaurant)}</div>'
        if num_slides > 1:
            html += '<div class="dots">'
            for i in range(num_slides):
                active = ' active' if i == 0 else ''
                html += f'<div class="dot{active}" data-dot="{i}"></div>'
            html += '</div>'
        html += '<div class="footer-text">MediAd View</div>'
        html += '</div></div>'

        # Slideshow JS + Promo scroll
        promo_count = len(promo_media)
        scroll_speed = max(promo_count * 8, 20)  # seconds for full scroll

        html += f"""<script>
    var current=0,total={num_slides},duration={slide_duration}000;
    function showSlide(n){{
      document.querySelectorAll('.slide').forEach(function(s){{s.classList.remove('active')}});
      document.querySelectorAll('.dot').forEach(function(d){{d.classList.remove('active')}});
      var slide=document.querySelector('[data-slide="'+n+'"]');
      var dot=document.querySelector('[data-dot="'+n+'"]');
      if(slide)slide.classList.add('active');
      if(dot)dot.classList.add('active');
    }}
    if(total>1){{setInterval(function(){{current=(current+1)%total;showSlide(current)}},duration)}}
    // Promo scroll animation
    var ps=document.getElementById('promo-scroll');
    if(ps){{ps.style.animationDuration='{scroll_speed}s'}}
    // Fallback: reload every 5 min (in case WebSocket dies). Also re-runs the hour-based filter.
    setTimeout(function(){{location.reload()}},300000);
    // -------- Live sync via WebSocket (Chat #2 real-time feature) --------
    (function(){{
      var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      var wsUrl = proto + '//' + location.host + '/api/ws/menu/{menu_id}';
      var ws, retry = 0, keepalive;
      function connect(){{
        try {{ ws = new WebSocket(wsUrl); }} catch(e){{ scheduleReconnect(); return; }}
        ws.onopen = function(){{ retry = 0;
          keepalive = setInterval(function(){{ try{{ ws.send('ping'); }}catch(e){{}} }}, 30000);
        }};
        ws.onmessage = function(ev){{
          try {{ var m = JSON.parse(ev.data); }} catch(e){{ return; }}
          if(m.type === 'menu' && (m.event === 'updated' || m.event === 'reload')){{
            // Immediate reload — instant price/menu change on TV
            location.reload();
          }}
        }};
        ws.onclose = function(){{ clearInterval(keepalive); scheduleReconnect(); }};
        ws.onerror = function(){{ try {{ ws.close(); }} catch(e){{}} }};
      }}
      function scheduleReconnect(){{
        retry = Math.min(retry+1, 6);
        var delay = Math.pow(2, retry) * 1000; // 2s..64s
        setTimeout(connect, delay);
      }}
      connect();
      // Also re-run the hour filter every full minute (client-side hint)
      var lastMin = new Date().getMinutes();
      setInterval(function(){{
        var m = new Date().getMinutes();
        if(m !== lastMin){{ lastMin = m; }}
      }}, 15000);
    }})();
    </script>"""

        html += '</body></html>'
        return HTMLResponse(content=html)

    return router
