"""Borra los clientes de prueba que dejan los tests (y todo lo que arrastran).

Los tests crean clientes «Borrar Test xxxx» / «Dulce Vida Test xxxx» con sus
contratos, facturas, depósitos y movimientos de correo. Sin esto el panel de
desarrollo se llena de basura y no se puede revisar nada.
"""
import asyncio
import os
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

PREFIJOS = ["Borrar Test ", "Dulce Vida Test "]


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]
    regex = "|".join(f"^{p}" for p in PREFIJOS)
    clientes = await db.fin_clients.find({"business_name": {"$regex": regex}}).to_list(1000)
    ids = [c["id"] for c in clientes]
    print(f"clientes de prueba: {len(ids)}")
    if not ids:
        return
    if "--yes" not in sys.argv:
        print("Agregá --yes para borrar de verdad.")
        return
    for col in ("fin_contracts", "fin_invoices", "fin_deposits", "fin_payments",
                "fin_email_log", "fin_print_queue"):
        r = await db[col].delete_many({"client_id": {"$in": ids}})
        print(f"  {col}: {r.deleted_count}")
    r = await db.fin_clients.delete_many({"id": {"$in": ids}})
    print(f"  fin_clients: {r.deleted_count}")


asyncio.run(main())
