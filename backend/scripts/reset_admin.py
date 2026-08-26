#!/usr/bin/env python3
"""
MediaView — Admin recovery script
=================================

Use este script desde el **Render Shell** cuando pierdas el acceso al panel
admin o quedes bloqueado por el brute-force lockout (15 minutos).

Uso rápido (desde el Render Shell del servicio `mediadview` en /opt/render/project/src):

    cd backend
    python scripts/reset_admin.py --unlock-all
    python scripts/reset_admin.py --email tu@email.com --password "NuevaClave123!"
    python scripts/reset_admin.py --email tu@email.com --show
    python scripts/reset_admin.py --list-admins

Flags:
    --unlock-all           Borra TODOS los intentos fallidos de login
                           (libera cualquier lockout de 15 min por email o IP).
    --unlock-email EMAIL   Borra los intentos fallidos SOLO de un email.
    --email EMAIL          Selecciona el usuario a modificar.
    --password PASSWORD    Nueva contraseña (bcrypt, 12 rounds).
    --activate             Fuerza active=true y role=superadmin.
    --show                 Muestra info del usuario (sin password_hash completo).
    --list-admins          Lista todos los usuarios con role admin/superadmin.
    --dry-run              No escribe cambios, solo muestra lo que haría.

El script usa MONGO_URL y DB_NAME desde las env vars del entorno (Render).
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Cargar .env si existe (útil en local)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

import bcrypt
from motor.motor_asyncio import AsyncIOMotorClient


MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "mediaview_db")


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def _mask_url(url: str) -> str:
    """Oculta la contraseña de la MONGO_URL para no filtrarla en los logs."""
    try:
        if "@" in url and "://" in url:
            head, tail = url.split("://", 1)
            creds, host = tail.split("@", 1)
            if ":" in creds:
                user, _pw = creds.split(":", 1)
                return f"{head}://{user}:***@{host}"
        return url
    except Exception:
        return "***"


async def run(args) -> int:
    print(f"→ Conectando a MongoDB: {_mask_url(MONGO_URL)}  db={DB_NAME}")
    client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=8000)
    db = client[DB_NAME]

    try:
        await db.command("ping")
    except Exception as e:
        print(f"❌ No pude conectar a Mongo: {e}")
        return 2

    # 1) LISTAR ADMINS
    if args.list_admins:
        cursor = db.users.find(
            {"role": {"$in": ["admin", "superadmin"]}},
            {"email": 1, "name": 1, "role": 1, "active": 1, "created_at": 1},
        )
        docs = await cursor.to_list(length=200)
        if not docs:
            print("⚠️  No hay usuarios con rol admin/superadmin.")
        else:
            print(f"\n📋 {len(docs)} admin(s) encontrados:")
            for d in docs:
                print(
                    f"  • {d.get('email','?'):40s}  "
                    f"role={d.get('role','?'):10s}  "
                    f"active={d.get('active', True)}  "
                    f"name={d.get('name','')}"
                )
        return 0

    # 2) UNLOCK GLOBAL
    if args.unlock_all:
        if args.dry_run:
            n = await db.login_attempts.count_documents({"success": False})
            print(f"[dry-run] Se borrarían {n} intentos fallidos de login_attempts.")
        else:
            res = await db.login_attempts.delete_many({"success": False})
            print(f"✅ Borrados {res.deleted_count} intentos fallidos globales. Lockout liberado.")
        # continuamos por si también hay --email/--password

    # 3) UNLOCK POR EMAIL
    if args.unlock_email:
        email = args.unlock_email.strip().lower()
        if args.dry_run:
            n = await db.login_attempts.count_documents({"email": email, "success": False})
            print(f"[dry-run] Se borrarían {n} intentos fallidos para {email}.")
        else:
            res = await db.login_attempts.delete_many({"email": email, "success": False})
            print(f"✅ Borrados {res.deleted_count} intentos fallidos para {email}.")

    # 4) OPERACIONES POR USUARIO
    if args.email:
        email = args.email.strip().lower()
        user = await db.users.find_one({"email": email})
        if not user:
            print(f"❌ No existe usuario con email {email}.")
            print("   Sugerencia: usa --list-admins para ver los emails disponibles.")
            return 3

        if args.show:
            print("\n👤 Usuario encontrado:")
            print(f"  id            = {user.get('id')}")
            print(f"  email         = {user.get('email')}")
            print(f"  name          = {user.get('name')}")
            print(f"  role          = {user.get('role')}")
            print(f"  active        = {user.get('active', True)}")
            print(f"  company_name  = {user.get('company_name')}")
            print(f"  session_epoch = {user.get('session_epoch', 0)}")
            print(f"  created_at    = {user.get('created_at')}")
            print(f"  password_hash = {(user.get('password_hash','') or '')[:12]}…"
                  f" (len={len(user.get('password_hash','') or '')})")
            return 0

        update: dict = {}
        if args.password:
            if len(args.password) < 8:
                print("❌ La contraseña debe tener al menos 8 caracteres.")
                return 4
            update["password_hash"] = _hash(args.password)
            # Invalida sesiones/refresh tokens anteriores.
            update["session_epoch"] = int(user.get("session_epoch", 0)) + 1

        if args.activate:
            update["active"] = True
            update["role"] = "superadmin"

        if not update:
            print("ℹ️  Nada que hacer para este usuario. Usa --password / --activate / --show.")
            return 0

        if args.dry_run:
            print(f"[dry-run] Se actualizaría {email} con campos: {list(update.keys())}")
            return 0

        update["updated_at"] = datetime.now(timezone.utc)
        res = await db.users.update_one({"email": email}, {"$set": update})
        print(f"✅ Usuario {email} actualizado. matched={res.matched_count} modified={res.modified_count}")

        # Además, borrar los intentos fallidos de este email para desbloquearlo.
        cleared = await db.login_attempts.delete_many({"email": email, "success": False})
        print(f"   ↳ Además, borrados {cleared.deleted_count} intentos fallidos de este email.")

        # Y por si sus refresh tokens quedaron colgados:
        try:
            rt = await db.refresh_tokens.delete_many({"user_id": user.get("id")})
            print(f"   ↳ Refresh tokens revocados: {rt.deleted_count}")
        except Exception:
            pass

        print("\n🔐 Pruébalo AHORA en una ventana Incognito:")
        print(f"   https://panel.mediadview.com  →  {email}  /  <la nueva contraseña>")
        return 0

    # Ninguna acción explícita
    if not (args.unlock_all or args.unlock_email):
        print("ℹ️  Nada que hacer. Ejecuta con --help para ver las opciones.")
    return 0


async def run_interactive() -> int:
    """Modo asistido: 1) conecta, 2) muestra admins, 3) desbloquea lockout,
    4) pide email + contraseña, 5) resetea todo."""
    print("\n════════════════════════════════════════════════════════════")
    print("   MediaView — Recuperación de Acceso Admin (modo asistido)")
    print("════════════════════════════════════════════════════════════\n")
    print(f"→ Conectando a MongoDB: {_mask_url(MONGO_URL)}")
    print(f"  db = {DB_NAME}\n")

    client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=8000)
    db = client[DB_NAME]
    try:
        await db.command("ping")
    except Exception as e:
        print(f"❌ No pude conectar a Mongo: {e}")
        print("   Verifica que MONGO_URL esté configurada en las env vars de Render.")
        return 2
    print("✅ Conexión OK.\n")

    # 1) Listar admins
    docs = await db.users.find(
        {"role": {"$in": ["admin", "superadmin"]}},
        {"email": 1, "name": 1, "role": 1, "active": 1},
    ).to_list(length=200)

    if not docs:
        print("⚠️  No hay usuarios admin/superadmin en la base de datos.")
        print("   Sugerencia: activa SEED_DEMO=true en Render y redeploy, o crea uno manualmente.")
        return 3

    print(f"📋 {len(docs)} admin(s) encontrados:\n")
    for i, d in enumerate(docs, start=1):
        print(f"  [{i}]  {d.get('email','?'):40s}  role={d.get('role',''):11s}  active={d.get('active', True)}")
    print()

    # 2) Desbloquear intentos fallidos globales (siempre)
    res = await db.login_attempts.delete_many({"success": False})
    print(f"🔓 Lockout liberado: se borraron {res.deleted_count} intentos fallidos.\n")

    # 3) Elegir usuario
    while True:
        raw = input("👉 ¿Qué admin quieres resetear? (escribe el número o el email, o 'q' para salir): ").strip()
        if raw.lower() in ("q", "quit", "exit", ""):
            print("Saliendo sin cambios de password. El lockout ya fue liberado, prueba a entrar.")
            return 0
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(docs):
                email = docs[idx]["email"]
                break
            print("Número fuera de rango, intenta de nuevo.")
            continue
        if "@" in raw:
            match = next((d for d in docs if d["email"].lower() == raw.lower()), None)
            if match:
                email = match["email"]
                break
            print("Ese email no está en la lista, intenta de nuevo.")
            continue
        print("Entrada no válida.")

    print(f"\n→ Usuario seleccionado: {email}")

    # 4) Pedir contraseña de forma segura
    while True:
        pw = getpass.getpass("🔑 Escribe la NUEVA contraseña (min 8, no se mostrará): ")
        if len(pw) < 8:
            print("   ❌ Muy corta. Debe tener al menos 8 caracteres.")
            continue
        pw2 = getpass.getpass("🔑 Confírmala de nuevo: ")
        if pw != pw2:
            print("   ❌ No coinciden. Intenta otra vez.")
            continue
        break

    # 5) Aplicar cambios
    user = await db.users.find_one({"email": email})
    update = {
        "password_hash": _hash(pw),
        "session_epoch": int((user or {}).get("session_epoch", 0)) + 1,
        "active": True,
        "updated_at": datetime.now(timezone.utc),
    }
    await db.users.update_one({"email": email}, {"$set": update})
    cleared = await db.login_attempts.delete_many({"email": email.lower(), "success": False})
    try:
        rt = await db.refresh_tokens.delete_many({"user_id": (user or {}).get("id")})
        rt_n = rt.deleted_count
    except Exception:
        rt_n = 0

    print("\n════════════════════════════════════════════════════════════")
    print("✅ LISTO. Contraseña actualizada.")
    print(f"   • usuario:             {email}")
    print(f"   • intentos limpiados:  {cleared.deleted_count}")
    print(f"   • refresh tokens:      {rt_n} revocados")
    print(f"   • active:              True")
    print("\n🔐 Prueba AHORA en una ventana Incognito:")
    print("   https://panel.mediadview.com")
    print(f"   Email:    {email}")
    print("   Password: (la que acabas de escribir)")
    print("════════════════════════════════════════════════════════════\n")
    return 0


def main():
    p = argparse.ArgumentParser(
        description="MediaView admin recovery (unlock + password reset).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--email", help="Email del usuario a modificar.")
    p.add_argument("--password", help="Nueva contraseña (min 8 chars).")
    p.add_argument("--activate", action="store_true",
                   help="Fuerza active=true y role=superadmin.")
    p.add_argument("--show", action="store_true", help="Muestra info del usuario.")
    p.add_argument("--unlock-all", action="store_true",
                   help="Libera el lockout global borrando todos los intentos fallidos.")
    p.add_argument("--unlock-email", help="Libera el lockout solo para un email.")
    p.add_argument("--list-admins", action="store_true",
                   help="Lista todos los admins/superadmins.")
    p.add_argument("--dry-run", action="store_true",
                   help="No escribe cambios, solo muestra qué haría.")
    args = p.parse_args()

    # Modo asistido: si no pasas NINGÚN flag, corre interactivo.
    if not any([args.email, args.password, args.activate, args.show,
                args.unlock_all, args.unlock_email, args.list_admins, args.dry_run]):
        code = asyncio.run(run_interactive())
        sys.exit(code)

    code = asyncio.run(run(args))
    sys.exit(code)


if __name__ == "__main__":
    main()
