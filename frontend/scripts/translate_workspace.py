"""
One-shot copy migration: MediaView Customer Workspace UI strings EN -> ES,
so the workspace matches the Spanish copy already used in the dashboard.

Only literal UI strings are rewritten. Run once:
    python scripts/translate_workspace.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

T = {
    # headers / nav
    "Customer Workspace": "Panel del Cliente",
    "Billing & Plan": "Facturación y Plan",
    "Content / Media": "Contenido / Medios",
    "Your Profile": "Tu Perfil",
    "Organization": "Organización",
    "Subscription": "Suscripción",
    "Current Plan": "Plan Actual",
    "Pricing History": "Historial de Precios",
    "Playlists": "Playlists",
    "Schedules": "Horarios",
    "Screens": "Pantallas",
    "Menus": "Menús",
    "Team": "Equipo",
    "Settings": "Ajustes",
    # empty states
    "No screens yet": "Todavía no tienes pantallas",
    "No menus yet": "Todavía no tienes menús",
    "No playlists yet": "Todavía no tienes playlists",
    "No schedules yet": "Todavía no tienes horarios",
    "No items yet": "Todavía no hay productos",
    "No team members": "Todavía no hay miembros del equipo",
    "No subscription found": "No se encontró suscripción",
    "Media library is empty": "Tu biblioteca de medios está vacía",
    "Create a menu to publish it to your screens.": "Crea un menú para publicarlo en tus pantallas.",
    "Create a playlist to organise and schedule your content.": "Crea una playlist para organizar y programar tu contenido.",
    "Invite team members to collaborate in your workspace.": "Invita a tu equipo a colaborar en tu workspace.",
    "Add your first menu item below.": "Agrega tu primer producto abajo.",
    "Empty menu. Add items one by one with name, price, and photo.": "Menú vacío. Agrega productos uno por uno con nombre, precio y foto.",
    "Contact support if you believe this is an error.": "Contacta a soporte si crees que esto es un error.",
    "Code shown on your screen": "Código que aparece en tu pantalla",
    # actions
    "Connect Screen": "Conectar Pantalla",
    "Connect a Screen": "Conectar una Pantalla",
    "Connect First Screen": "Conectar Primera Pantalla",
    "Create Menu": "Crear Menú",
    "Create First Menu": "Crear Primer Menú",
    "Add Menu Items": "Agregar Productos",
    "Add Item": "Agregar Producto",
    "Add items first": "Agrega productos primero",
    "Add More Screens": "Agregar Más Pantallas",
    "Add Screens": "Agregar Pantallas",
    "Publish to Screen": "Publicar en Pantalla",
    "Import Image / PDF": "Importar Imagen / PDF",
    "Start from Scratch": "Empezar de Cero",
    "Or choose a template": "O elige una plantilla",
    "Choose how to start": "Elige cómo empezar",
    "Go to Dashboard": "Ir al Panel",
    "Get Started": "Empezar",
    "Back": "Atrás",
    "Skip": "Omitir",
    "Soon": "Pronto",
    "How many screens to add?": "¿Cuántas pantallas quieres agregar?",
    "Current monthly": "Mensual actual",
    "New monthly total": "Nuevo total mensual",
    # field labels
    'label="Monthly Price"': 'label="Precio Mensual"',
    'label="Screens Included"': 'label="Pantallas Incluidas"',
    'label="Extra Screen"': 'label="Pantalla Extra"',
    'label="Billing Cycle"': 'label="Ciclo de Facturación"',
    'label="Pricing Model"': 'label="Modelo de Precio"',
    'label="Status"': 'label="Estado"',
    'label="Provider"': 'label="Proveedor"',
    'label="Trial Ends"': 'label="Fin de Prueba"',
    'label="Period Start"': 'label="Inicio de Periodo"',
    'label="Period End"': 'label="Fin de Periodo"',
    'label="Created"': 'label="Creado"',
    'label="Name"': 'label="Nombre"',
    'label="Email"': 'label="Correo"',
    'label="Role"': 'label="Rol"',
    'label="Slug"': 'label="Identificador"',
    # form fields
    "Activation Code": "Código de Activación",
    "Screen Name": "Nombre de la Pantalla",
    "Screen name": "Nombre de la pantalla",
    "Menu name": "Nombre del menú",
    "Category": "Categoría",
    "Available": "Disponible",
    'placeholder="Short description…"': 'placeholder="Descripción corta…"',
    'placeholder="e.g. Lunch Menu, Drinks, Daily Specials"': 'placeholder="ej. Menú de Almuerzo, Bebidas, Especiales"',
    'placeholder="e.g. Main Entrance, Counter"': 'placeholder="ej. Entrada Principal, Mostrador"',
    'placeholder="e.g. Main Entrance, Window Display"': 'placeholder="ej. Entrada Principal, Vidriera"',
    'placeholder="e.g. Margherita Pizza"': 'placeholder="ej. Pizza Margherita"',
    'placeholder="e.g. Pizza, Drinks, Desserts"': 'placeholder="ej. Pizza, Bebidas, Postres"',
    # counters / misc sentences
    "screen connected": "pantalla conectada",
    "screens connected": "pantallas conectadas",
    "To connect a screen: power on the device, open the MediaView Player app (or visit the player URL), and enter the 6-character code that appears on screen.":
        "Para conectar una pantalla: enciende el dispositivo, abre la app MediaView Player (o visita la URL del reproductor) e ingresa el código de 6 caracteres que aparece en pantalla.",
}


def main() -> None:
    targets = sorted(ROOT.glob("app/workspace/*.tsx"))
    if not targets:
        print("no workspace files found")
        sys.exit(1)

    keys = sorted(T, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(k) for k in keys))

    for path in targets:
        src = path.read_text()
        out = pattern.sub(lambda m: T[m.group(0)], src)
        if out != src:
            path.write_text(out)
            print(f"translated {path.relative_to(ROOT)}")
        else:
            print(f"unchanged  {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
