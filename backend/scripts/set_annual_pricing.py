"""
Sets the annual price of every plan from a *configurable* "free months" rule
instead of a hardcoded discount: annual_price = monthly_price * (12 - annual_free_months).

`annual_free_months` lives on the plan document, so an admin can change it later
(2 = two months free, the current commercial rule) without touching code.

Idempotent.  Run:  python scripts/set_annual_pricing.py [free_months]
"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

FREE_MONTHS = int(sys.argv[1]) if len(sys.argv) > 1 else 2


async def main() -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "mediaview")]

    async for plan in db.plans.find({}):
        monthly = float(plan.get("monthly_price") or 0)
        free = 0 if monthly == 0 else FREE_MONTHS
        annual = round(monthly * (12 - free), 2)
        await db.plans.update_one(
            {"plan_id": plan["plan_id"]},
            {"$set": {"annual_free_months": free, "annual_price": annual}},
        )
        print(f"{plan['plan_id']:12s} monthly={monthly:>8.2f}  free_months={free}  annual={annual:>9.2f}")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
