"""Genera las fotos genéricas de producto del catálogo de plantillas.

Sin fotos buenas una plantilla no se ve de agencia y el cliente no entiende qué
va en cada hueco. Estas son fotos de MediaView, iguales para todos, y el cliente
las reemplaza por las suyas al llenar la plantilla.

Se corre a mano y el resultado se versiona en el repo: el catálogo no puede
depender de que haya saldo de IA en cada despliegue.

    cd /app/backend && python scripts/seed_template_photos.py pizzeria
"""
import asyncio
import base64
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT = Path(__file__).resolve().parents[1] / "static" / "template-samples"

# Un único "set fotográfico" para todo el rubro: mismo ángulo, misma luz, mismo
# fondo y sin utilería. Es lo que hace que doce fotos generadas por separado se
# vean como una sola sesión de fotos y la cartelera no parezca un collage.
STYLE = ("professional food photography for a digital menu board, camera at a fixed "
         "45 degree angle, single soft warm key light from the upper left with a subtle "
         "fill, dark charred wood surface background, identical framing and identical "
         "lighting across the whole series, subject centered and filling the frame, "
         "shallow depth of field, rich warm tones, appetizing, no props, no cutlery, "
         "no napkins, no hands, no people, no text, no watermark, square crop")

# Cada rubro tiene su propio «set fotográfico»: la luz y el ángulo de una
# hamburguesería no son los de un restaurante de autor, y eso es justamente lo
# que hace que cada plantilla se vea de su rubro.
SET_BY_INDUSTRY = {
    "latin_honduras": ("authentic Honduran home cooking photography, rustic dark wood table "
                       "with a woven palm mat, warm afternoon daylight from the right, "
                       "40 degree angle, glazed terracotta plate, no hands, no people, "
                       "no text, no watermark, square crop"),
    "latin_salvador": ("authentic Salvadoran comedor photography, dark volcanic stone slab, "
                       "soft warm overhead light, 35 degree angle, food served on a simple "
                       "white enamel plate, no hands, no people, no text, no watermark, "
                       "square crop"),
    "latin_panama": ("authentic Panamanian food photography, pale sand coloured wooden table, "
                     "bright tropical daylight, 30 degree angle, white ceramic plate with a "
                     "blue rim, fresh and colourful, no hands, no people, no text, "
                     "no watermark, square crop"),
    "latin_venezuela": ("authentic Venezuelan street food photography, dark charcoal slate "
                        "board, warm dramatic side light, 40 degree angle, generous rustic "
                        "serving, no hands, no people, no text, no watermark, square crop"),
    "mexican": ("authentic Mexican taqueria photography, warm terracotta tiled surface, "
                "bright warm light from the upper left, 35 degree angle, served on a small "
                "colourful talavera plate, lime wedges and salsa in tiny bowls, no hands, "
                "no people, no text, no watermark, square crop"),
    "fast_food": ("bright commercial fast food photography, clean light grey seamless "
                  "background, bright even studio light, slight top-down 30 degree angle, "
                  "vivid saturated colors, product centered and filling the frame, "
                  "no props, no hands, no people, no text, no watermark, square crop"),
    "restaurant": ("fine dining plated dish photography, dark slate table, single soft "
                   "window light from the left, 35 degree angle, elegant minimal plating, "
                   "moody and refined, shallow depth of field, no cutlery in frame, "
                   "no hands, no people, no text, no watermark, square crop"),
}

PROMPTS = {
    "latin_honduras": {
        "plato_tipico": "a Honduran plato tipico with grilled carne asada, refried beans, fried plantain slices, chismol salsa, white cheese and a corn tortilla",
        "baleada_sencilla": "a Honduran baleada, a folded thick flour tortilla filled with refried beans, cream and crumbled white cheese",
        "baleada_especial": "a Honduran baleada especial, folded flour tortilla filled with beans, cream, cheese, scrambled egg and avocado",
        "pollo_tajadas": "Honduran pollo con tajadas, fried chicken over green plantain chips with cabbage salad and red sauce",
        "sopa_caracol": "Honduran conch soup in a clay bowl, creamy coconut broth with yuca and plantain",
        "pastelitos": "three Honduran pastelitos de carne, fried corn turnovers with cabbage salad and tomato sauce on top",
        "nacatamal": "a Honduran tamal wrapped in banana leaf, opened to show the corn dough with pork and vegetables",
        "horchata": "a tall glass of Honduran horchata with ice, creamy rice drink with cinnamon",
        "tres_leches": "a slice of tres leches cake with a cherry on top",
    },
    "latin_salvador": {
        "pupusa_revuelta": "two Salvadoran pupusas revueltas with curtido cabbage slaw and tomato salsa on the side",
        "pupusa_queso": "two Salvadoran cheese and loroco pupusas, one torn open showing melted cheese",
        "pupusa_frijol": "two Salvadoran bean and cheese pupusas stacked with curtido",
        "yuca_frita": "Salvadoran fried yuca with chicharron and curtido cabbage slaw",
        "pan_pollo": "a Salvadoran pan con pollo sandwich, french bread with stewed chicken, salad and relish",
        "tamal_elote": "a Salvadoran sweet corn tamal in its husk with a spoon of cream",
        "platanos_crema": "Salvadoran fried sweet plantains with sour cream and refried beans",
        "atol_elote": "a mug of Salvadoran atol de elote, warm sweet corn drink",
        "horchata_salv": "a tall glass of Salvadoran morro seed horchata with ice",
    },
    "latin_panama": {
        "sancocho": "Panamanian sancocho de gallina, chicken and yam soup with culantro in a deep bowl with white rice on the side",
        "ropa_vieja": "Panamanian ropa vieja, shredded beef in tomato sauce with white rice and fried plantain",
        "arroz_pollo": "Panamanian arroz con pollo with peas, carrot and olives",
        "carimanolas": "three Panamanian carimanolas, fried yuca fritters stuffed with seasoned beef",
        "hojaldras": "two Panamanian hojaldras, golden fried flat dough, with white cheese",
        "pescado_patacones": "a whole fried red snapper with patacones and lime",
        "tamal_panameno": "a Panamanian tamal wrapped in banana leaf, opened to show corn dough with chicken and olives",
        "chicheme": "a tall glass of Panamanian chicheme, sweet corn and milk drink with cinnamon",
        "raspado": "a Panamanian raspado, shaved ice cone with red syrup and condensed milk",
    },
    "latin_venezuela": {
        "arepa_reina": "a Venezuelan arepa reina pepiada, split corn arepa stuffed with chicken and avocado salad",
        "arepa_pelua": "a Venezuelan arepa pelua stuffed with shredded beef and yellow cheese",
        "cachapa": "a Venezuelan cachapa, sweet corn pancake folded over melted queso de mano",
        "pepito": "a Venezuelan pepito, long bread sandwich with grilled beef, cheese and potato sticks",
        "tequenos": "five Venezuelan tequenos, cheese sticks wrapped in fried dough, with a dipping sauce",
        "empanadas": "three Venezuelan fried corn empanadas, one broken open showing shredded beef",
        "pabellon": "Venezuelan pabellon criollo with shredded beef, black beans, white rice and fried plantain",
        "papelon": "a tall glass of Venezuelan papelon con limon with ice",
        "yuca_frita": "Venezuelan fried yuca sticks with a garlic dipping sauce",
        "tajadas": "Venezuelan fried sweet plantain slices topped with grated white cheese",
        "quesillo": "a slice of Venezuelan quesillo caramel flan on a plate",
    },
    "mexican": {
        "taco_pastor": "three Mexican tacos al pastor with pineapple, onion and cilantro on corn tortillas",
        "taco_asada": "three Mexican carne asada tacos with onion, cilantro and lime",
        "taco_birria": "three Mexican birria tacos, crispy and red, with a small cup of consome",
        "quesadilla": "a Mexican cheese quesadilla cut in halves with melted cheese stretching",
        "burrito": "a large Mexican burrito cut in half showing beans, rice and carne asada",
        "sopes": "three Mexican sopes with beans, lettuce, cream and crumbled cheese",
        "elote": "a Mexican elote, grilled corn on the cob with mayonnaise, cheese and chili powder",
        "guacamole": "a bowl of fresh guacamole with tortilla chips around it",
        "horchata_mx": "a tall glass of Mexican horchata with ice and cinnamon",
        "churros": "three Mexican churros with sugar and a cup of chocolate sauce",
        "jamaica": "a tall glass of Mexican hibiscus agua de jamaica with ice",
    },
    "fast_food": {
        "combo_doble": "a double bacon cheeseburger combo with a large box of french fries and a paper cup of soda",
        "combo_pollo": "a crispy fried chicken sandwich combo with french fries and a soda cup",
        "combo_familiar": "four burgers, four fry boxes and four soda cups arranged as a family meal",
        "clasica": "a classic cheeseburger with melted cheddar",
        "veggie": "a chickpea veggie burger with lettuce and tomato",
        "picante": "a spicy jalapeno burger with red sauce dripping",
        "bbq": "a bbq burger topped with onion rings",
        "papas": "a large box of golden french fries",
        "aros": "a pile of crispy golden onion rings",
        "nuggets": "eight golden chicken nuggets with a dipping sauce cup",
        "ensalada": "a fresh green side salad in a clear bowl",
        "refresco": "a large paper cup of cola with a straw and condensation",
        "malteada": "a tall chocolate milkshake with whipped cream",
        "cafe": "a paper cup of hot coffee with a lid",
        "agua": "a clear plastic bottle of water with condensation",
    },
    "restaurant": {
        "burrata": "burrata cheese with confit cherry tomatoes and basil oil on a ceramic plate",
        "vieiras": "three seared scallops with cauliflower puree on a dark plate",
        "tartar": "beef tartare quenelle with capers and egg yolk on a slate plate",
        "sopa": "a bowl of roasted pumpkin cream soup with olive oil drizzle",
        "ensalada": "a seasonal green salad with pear slices and walnuts",
        "cordero": "slow cooked lamb shank with smoked potato puree and rosemary jus",
        "lubina": "a whole sea bass baked in a salt crust, opened, on a ceramic platter",
        "risotto": "creamy wild mushroom risotto with parmesan shavings",
        "pato": "sliced duck magret with cherry sauce, fanned on a plate",
        "ravioles": "ricotta ravioli with brown butter and sage leaves",
        "tarta": "a warm chocolate tart slice with a molten center",
        "helado": "a scoop of vanilla bean ice cream in a small glass bowl",
        "citricos": "a citrus and meringue dessert with torched meringue peaks",
    },
    "pizzeria": {
        "pepperoni": "a whole pepperoni pizza, crispy cupped pepperoni, bubbling mozzarella, wood fired crust",
        "margherita": "a whole margherita pizza with san marzano tomato, fresh mozzarella and basil leaves",
        "meatlovers": "a whole meat lovers pizza loaded with pepperoni, italian sausage, ham and bacon",
        "quattro": "a whole four cheese pizza, molten cheese pull, golden blistered crust",
        "veggie": "a whole vegetable pizza with roasted peppers, mushrooms, red onion and black olives",
        "prosciutto": "a whole pizza topped with prosciutto, fresh arugula and shaved parmesan",
        "combo_lunch": "a personal pizza with a soft drink, lunch combo on a wooden board",
        "combo_family": "two large pizzas with a two liter soda bottle, family combo",
        "combo_duo": "two medium pizzas with a basket of french fries",
        "combo_kids": "a small kids pizza with apple slices and a juice box",
        "combo_calzone": "a golden baked calzone cut open with melted cheese, next to a drink",
        "coke": "a cold glass bottle of cola with condensation and ice",
        "sprite": "a cold glass bottle of clear lemon lime soda with condensation",
        "water": "a bottle of sparkling mineral water with condensation",
        "lemonade": "a tall glass of fresh homemade lemonade with mint and ice",
    },
}


async def generate(industry: str) -> None:
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise SystemExit("EMERGENT_LLM_KEY no está configurada")
    prompts = PROMPTS.get(industry)
    if not prompts:
        raise SystemExit(f"No hay prompts para el rubro «{industry}»")

    folder = OUT / industry
    folder.mkdir(parents=True, exist_ok=True)
    for key_name, subject in prompts.items():
        target = folder / f"{key_name}.jpg"
        if target.exists():
            print(f"  = {target.name} (ya existe)")
            continue
        from menu_ai_routes import IMAGE_MODEL
        chat = LlmChat(
            api_key=key, session_id=f"tpl-photo-{industry}-{key_name}",
            system_message="Generas fotografías de comida para menús digitales.",
        ).with_model("gemini", IMAGE_MODEL).with_params(modalities=["image", "text"])
        try:
            _text, images = await chat.send_message_multimodal_response(
                UserMessage(text=f"{subject}. {SET_BY_INDUSTRY.get(industry, STYLE)}"))
        except Exception as exc:
            print(f"  ! {key_name}: {exc}")
            continue
        if not images:
            print(f"  ! {key_name}: sin imagen")
            continue
        target.write_bytes(base64.b64decode(images[0]["data"]))
        print(f"  + {target.name} ({target.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    asyncio.run(generate(sys.argv[1] if len(sys.argv) > 1 else "pizzeria"))
