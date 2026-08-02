#!/usr/bin/env python3
"""
MediaDView — Reset for Production
=================================
Prepares a MediaDView Mongo database for the FIRST deploy to production.

WHAT IT DOES
------------
1. Refuses to run without an explicit `--i-know-what-im-doing` flag AND
   `MEDIADVIEW_ALLOW_RESET=1` in the environment.
2. Prints a DRY-RUN summary of everything it would delete/change.
3. Asks the operator to type the DB name (destructive-op typo guard).
4. Optionally seeds a REAL production superadmin if requested.
5. Verifies at the end that no test/demo credentials remain.

USAGE
-----
Dry run (safe, read-only):
    python -m tools.reset_for_production --dry-run

Wet run (requires flag + env):
    export MEDIADVIEW_ALLOW_RESET=1
    python -m tools.reset_for_production --i-know-what-im-doing

Optional additional flags:
    --skip-users            Do not touch users collection
    --skip-screens          Do not touch screens collection
    --seed-superadmin       Prompt for superadmin email/password and create it

WHAT GETS DELETED
-----------------
Financial + operational data from smoke/dev runs:
    orders, fin_invoices, fin_credit_notes, refunds, fin_ledger,
    stripe_events, slot_reservations, checkout_sessions, order_tokens,
    notifications, campaigns (legacy), dev_customers, dev_payment_intents,
    dev_refunds, financial_audit (legacy), counters, media

Users:
    Anything matching demo|test|smoke in email (unless --skip-users).
    Real 'superadmin' + 'admin' with strong passwords are preserved.

Screens:
    Screens named "(unknown)", "smoke*", "test*" (unless --skip-screens).

WHAT IT NEVER TOUCHES
---------------------
    · Application config
    · Indexes (recreated at next backend startup automatically)
    · Environment variables

EXIT CODES
----------
    0 = success (dry-run or wet-run)
    1 = safety-guard triggered
    2 = user aborted at confirmation
    3 = post-verification failed
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import re
import sys
from pathlib import Path
from typing import Any

# Load .env before importing anything that uses it
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / "backend" / ".env")

from motor.motor_asyncio import AsyncIOMotorClient


# ── Collections we DELETE completely ─────────────────────────────
DROP_COLLECTIONS_FINANCIAL = [
    "orders",
    "fin_invoices",
    "fin_credit_notes",
    "refunds",
    "fin_ledger",
    "financial_audit",       # legacy audit — new ledger takes over
    "stripe_events",
    "slot_reservations",
    "checkout_sessions",
    "order_tokens",
    "notifications",
    "campaigns",             # legacy — user decision
    "dev_customers",
    "dev_payment_intents",
    "dev_refunds",
    "counters",              # invoice/credit/refund numbering
    "media",                 # base64 media of dev tests
    "payments",              # legacy payments collection
    "customers_stripe",
]

# Regex patterns for demo/test artefacts inside preserved collections
DEMO_EMAIL_RE   = re.compile(r"(demo|test|smoke|example\.com|admin\.demo|superadmin@)", re.I)
DEMO_SCREEN_RE  = re.compile(r"^(smoke|test|dev|unknown|\(unknown\))", re.I)
DEMO_SCREEN_ID  = re.compile(r"^scr_(smoke|test|dev)")

# Screens that should be preserved even in prod-reset
PRESERVE_SCREEN_IDS: set[str] = set()  # empty by default — operator must curate


class C:
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    END    = "\033[0m"


def say(msg: str, *, color: str = "") -> None:
    print(f"{color}{msg}{C.END}")


# ═══════════════════════════════════════════════════════════════════
# Safety guards
# ═══════════════════════════════════════════════════════════════════
def safety_check(args) -> None:
    """Refuse to proceed unless BOTH the flag AND env variable are set."""
    if args.dry_run:
        return
    if not args.i_know_what_im_doing:
        say("\n❌ Refusing to run destructive operations without "
            "--i-know-what-im-doing flag.", color=C.RED)
        say("   Run with --dry-run first to preview changes.", color=C.YELLOW)
        sys.exit(1)
    if os.environ.get("MEDIADVIEW_ALLOW_RESET") != "1":
        say("\n❌ Environment variable MEDIADVIEW_ALLOW_RESET must equal '1' "
            "to run destructive operations.", color=C.RED)
        say("   export MEDIADVIEW_ALLOW_RESET=1", color=C.YELLOW)
        sys.exit(1)


def confirm_db_name(actual: str) -> None:
    say(f"\n{C.BOLD}⚠  You are about to WIPE data from Mongo database:{C.END}", color=C.YELLOW)
    say(f"    {C.RED}{C.BOLD}{actual}{C.END}\n")
    typed = input("Type the database name to confirm (exactly, case-sensitive): ").strip()
    if typed != actual:
        say(f"\n❌ Typed {typed!r} but expected {actual!r}. Aborted.", color=C.RED)
        sys.exit(2)
    say("✓ Confirmed.", color=C.GREEN)


# ═══════════════════════════════════════════════════════════════════
# Preview / delete
# ═══════════════════════════════════════════════════════════════════
async def preview(db) -> dict:
    say(f"\n{C.BOLD}📊 Dry-run preview{C.END}", color=C.BLUE)
    summary = {"drop_totals": {}, "users_to_delete": [], "screens_to_delete": []}

    # Collections to drop
    say("\nCollections to DROP:")
    for name in DROP_COLLECTIONS_FINANCIAL:
        try:
            n = await db[name].count_documents({})
        except Exception:
            n = 0
        summary["drop_totals"][name] = n
        say(f"  {C.DIM}·{C.END} {name:<25} → {n:>6} documents")

    # Users to delete
    say("\nUsers to DELETE (email matching demo|test|smoke|example.com):")
    cursor = db.users.find({"email": {"$regex": DEMO_EMAIL_RE.pattern, "$options": "i"}})
    async for u in cursor:
        summary["users_to_delete"].append({
            "email": u.get("email"),
            "role": u.get("role"),
            "created_at": u.get("created_at"),
        })
        say(f"  {C.DIM}·{C.END} {u.get('email','(no-email)'):<40} role={u.get('role','?')}")
    if not summary["users_to_delete"]:
        say(f"  {C.DIM}(none){C.END}")

    # Screens to delete
    say("\nScreens to DELETE (name matches smoke|test|unknown OR id starts with scr_smoke_/scr_test_):")
    cursor = db.screens.find({"$or": [
        {"name":  {"$regex": DEMO_SCREEN_RE.pattern, "$options": "i"}},
        {"id":    {"$regex": DEMO_SCREEN_ID.pattern, "$options": "i"}},
    ]})
    async for s in cursor:
        summary["screens_to_delete"].append({
            "id": s.get("id"),
            "name": s.get("name"),
            "location": s.get("location"),
        })
        say(f"  {C.DIM}·{C.END} {s.get('id',''):<20} {s.get('name','(no-name)'):<25} "
            f"{(s.get('location') or {}).get('city','')}")
    if not summary["screens_to_delete"]:
        say(f"  {C.DIM}(none){C.END}")

    # Users kept
    kept = await db.users.count_documents(
        {"email": {"$not": {"$regex": DEMO_EMAIL_RE.pattern, "$options": "i"}}}
    )
    total_screens_kept = await db.screens.count_documents(
        {"$nor": [
            {"name":  {"$regex": DEMO_SCREEN_RE.pattern, "$options": "i"}},
            {"id":    {"$regex": DEMO_SCREEN_ID.pattern, "$options": "i"}},
        ]}
    )
    say(f"\n{C.BOLD}Preserved:{C.END} {kept} user(s) · {total_screens_kept} screen(s)",
        color=C.GREEN)

    return summary


async def execute(db, args) -> dict:
    stats: dict = {"dropped": {}, "users_deleted": 0, "screens_deleted": 0}

    # 1. Drop financial + operational collections
    say(f"\n{C.BOLD}🗑  Deleting financial + operational collections…{C.END}", color=C.YELLOW)
    for name in DROP_COLLECTIONS_FINANCIAL:
        try:
            n = await db[name].count_documents({})
            if n > 0:
                await db[name].delete_many({})   # keep the collection (indexes stay)
            stats["dropped"][name] = n
            say(f"  ✓ {name:<25} deleted {n} docs")
        except Exception as e:
            say(f"  ! {name:<25} skipped ({e})", color=C.YELLOW)

    # 2. Users
    if not args.skip_users:
        say(f"\n{C.BOLD}👥 Deleting demo/test users…{C.END}", color=C.YELLOW)
        result = await db.users.delete_many(
            {"email": {"$regex": DEMO_EMAIL_RE.pattern, "$options": "i"}}
        )
        stats["users_deleted"] = result.deleted_count
        say(f"  ✓ Deleted {result.deleted_count} user(s)")
    else:
        say(f"\n{C.DIM}(skipping users per --skip-users){C.END}")

    # 3. Screens
    if not args.skip_screens:
        say(f"\n{C.BOLD}📺 Deleting demo/test screens…{C.END}", color=C.YELLOW)
        result = await db.screens.delete_many({"$or": [
            {"name":  {"$regex": DEMO_SCREEN_RE.pattern, "$options": "i"}},
            {"id":    {"$regex": DEMO_SCREEN_ID.pattern, "$options": "i"}},
        ]})
        stats["screens_deleted"] = result.deleted_count
        say(f"  ✓ Deleted {result.deleted_count} screen(s)")
    else:
        say(f"\n{C.DIM}(skipping screens per --skip-screens){C.END}")

    # 4. Optional: seed real production superadmin
    if args.seed_superadmin:
        await _seed_prod_superadmin(db)

    return stats


# ═══════════════════════════════════════════════════════════════════
# Production superadmin seed
# ═══════════════════════════════════════════════════════════════════
async def _seed_prod_superadmin(db) -> None:
    say(f"\n{C.BOLD}🔑 Seeding production superadmin{C.END}", color=C.BLUE)
    say("   This account will have full permissions. Choose a strong password"
        " and store it in a password manager.")
    email = input("Superadmin email (production): ").strip().lower()
    if not email or "@" not in email:
        say("  ! Invalid email — skipping seed.", color=C.RED)
        return
    if DEMO_EMAIL_RE.search(email):
        say("  ! Email looks like a demo/test address — refuse.", color=C.RED)
        return
    p1 = getpass.getpass("Password (min 16 chars, mixed): ")
    p2 = getpass.getpass("Repeat password: ")
    if p1 != p2:
        say("  ! Passwords do not match — skipping seed.", color=C.RED)
        return
    if len(p1) < 16:
        say("  ! Password too short (need >=16 chars) — skipping.", color=C.RED)
        return

    # Import backend auth to hash the password consistently with the app
    try:
        from auth_v2 import hash_password
    except ImportError:
        import bcrypt
        def hash_password(pw: str) -> str:
            return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=12)).decode()

    import uuid
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    doc = {
        "id": str(uuid.uuid4()),
        "_id": str(uuid.uuid4()),
        "email": email,
        "password_hash": hash_password(p1),
        "role": "superadmin",
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "created_by": "reset_for_production.py",
        "must_rotate_password": True,
    }
    await db.users.insert_one(doc)
    say(f"  ✓ Superadmin {email} created. IMPORTANT: rotate the password after "
        "your first login.", color=C.GREEN)


# ═══════════════════════════════════════════════════════════════════
# Post-verification
# ═══════════════════════════════════════════════════════════════════
async def verify(db) -> tuple[bool, list[str]]:
    say(f"\n{C.BOLD}✅ Post-verification{C.END}", color=C.BLUE)
    problems: list[str] = []

    # No demo users remain
    async for u in db.users.find({"email": {"$regex": DEMO_EMAIL_RE.pattern,
                                              "$options": "i"}}):
        problems.append(f"user {u.get('email')!r} still present")

    # No demo screens
    async for s in db.screens.find({"$or": [
        {"name":  {"$regex": DEMO_SCREEN_RE.pattern, "$options": "i"}},
        {"id":    {"$regex": DEMO_SCREEN_ID.pattern, "$options": "i"}},
    ]}):
        problems.append(f"screen {s.get('name')!r} ({s.get('id')}) still present")

    # Financial collections empty
    for c in ["orders", "fin_invoices", "fin_credit_notes", "refunds",
              "fin_ledger", "counters"]:
        n = await db[c].count_documents({})
        if n > 0:
            problems.append(f"collection {c} still has {n} documents")

    # At least ONE non-demo superadmin exists
    non_demo_admins = await db.users.count_documents({
        "role": {"$in": ["superadmin", "admin"]},
        "email": {"$not": {"$regex": DEMO_EMAIL_RE.pattern, "$options": "i"}},
    })
    if non_demo_admins == 0:
        problems.append(
            "no real superadmin/admin exists — re-run with --seed-superadmin "
            "OR create one manually before deploying")

    if problems:
        say(f"  ✗ {len(problems)} issue(s) found:", color=C.RED)
        for p in problems:
            say(f"      {p}", color=C.RED)
        return False, problems

    say("  ✓ Database is clean and ready for production.", color=C.GREEN)
    return True, []


# ═══════════════════════════════════════════════════════════════════
# Entry
# ═══════════════════════════════════════════════════════════════════
async def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview only. No writes.")
    parser.add_argument("--i-know-what-im-doing", action="store_true",
                        help="Required for destructive operations.")
    parser.add_argument("--skip-users", action="store_true")
    parser.add_argument("--skip-screens", action="store_true")
    parser.add_argument("--seed-superadmin", action="store_true",
                        help="Prompt for a new production superadmin.")
    args = parser.parse_args()

    mongo_url = os.environ.get("MONGO_URL")
    db_name   = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        say("❌ MONGO_URL and DB_NAME must be set (check backend/.env).", color=C.RED)
        sys.exit(1)

    safety_check(args)

    say(f"\n{C.BOLD}MediaDView — Reset for Production{C.END}", color=C.BLUE)
    say(f"  MongoDB: {mongo_url.split('@')[-1] if '@' in mongo_url else mongo_url}")
    say(f"  Database: {db_name}")
    say(f"  Mode:    {'DRY-RUN (no changes)' if args.dry_run else 'WET-RUN (destructive)'}",
        color=C.YELLOW if not args.dry_run else C.DIM)

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    summary = await preview(db)

    if args.dry_run:
        say(f"\n{C.BOLD}Dry-run complete. Nothing was changed.{C.END}", color=C.GREEN)
        say("Re-run without --dry-run once you're satisfied with the preview.")
        return

    confirm_db_name(db_name)
    say("\nProceeding with destructive operations…\n", color=C.YELLOW)
    stats = await execute(db, args)

    ok, problems = await verify(db)
    say("\n" + "="*60)
    say(f"Summary: {sum(stats['dropped'].values())} financial docs removed · "
        f"{stats['users_deleted']} users · {stats['screens_deleted']} screens.")
    if not ok:
        say(f"\n{C.BOLD}❌ Post-verification FAILED. See issues above.{C.END}",
            color=C.RED)
        sys.exit(3)
    say(f"\n{C.BOLD}✓ Database is production-ready.{C.END}", color=C.GREEN)
    say("Next steps:")
    say("  1. Restart the backend so ensure_stripe_indexes() re-creates indexes.")
    say("  2. Verify that a real superadmin can log in.")
    say("  3. Rotate JWT_SECRET / FERNET_KEY / ORDER_LINK_SECRET for prod.")
    say("  4. Deploy following docs/RUNBOOK.md.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n(aborted by user)")
        sys.exit(2)
