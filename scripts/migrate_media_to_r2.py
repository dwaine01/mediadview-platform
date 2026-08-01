"""
MediAd View — Migrate legacy media (base64+disk) to Cloudflare R2

USAGE:
    # Dry-run (report what would happen, no writes)
    python -m scripts.migrate_media_to_r2 --dry-run

    # Real migration; keeps legacy fields until you verify + confirm
    python -m scripts.migrate_media_to_r2

    # After verifying media plays correctly from R2, purge legacy blobs:
    python -m scripts.migrate_media_to_r2 --purge-legacy

Safety guarantees:
    1. Never deletes anything until --purge-legacy is passed explicitly.
    2. Verifies each R2 upload with a HEAD request before touching Mongo.
    3. Idempotent: re-running skips docs already migrated (storage=r2).
    4. Rate-limited (5 parallel uploads by default) to protect the R2 bucket.
    5. Writes a JSON report to /tmp/media_migration_YYYYMMDD-HHMM.json.
"""
from __future__ import annotations
import os, sys, json, base64, asyncio, argparse, mimetypes
from datetime import datetime, timezone
from pathlib import Path

# Allow: `python scripts/migrate_media_to_r2.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv()

from motor.motor_asyncio import AsyncIOMotorClient
from storage import (
    R2_ENABLED, R2_BUCKET, build_key, public_url_for_key,
    r2_put_bytes, r2_head, _ext_of,
)

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME   = os.getenv("DB_NAME", "mediadview")
MEDIA_DIR = os.getenv("MEDIA_DIR", "/app/backend/media")


async def main(dry_run: bool, purge_legacy: bool, concurrency: int):
    if not R2_ENABLED:
        print("❌ R2 not configured. Set R2_ENDPOINT/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY/R2_BUCKET_NAME.")
        return 2

    client = AsyncIOMotorClient(MONGO_URL, tz_aware=True)
    db = client[DB_NAME]

    # Find candidates: legacy media that has NOT yet moved to R2
    query = {"$and": [
        {"$or": [{"storage": {"$exists": False}}, {"storage": {"$in": ["legacy", "disk", "base64"]}}]},
        {"$or": [{"data": {"$exists": True}}, {"stored_filename": {"$exists": True}}]},
        {"r2_key": {"$exists": False}},
    ]}
    total = await db.media.count_documents(query)
    print(f"🔎 Candidates to migrate: {total}")
    if total == 0:
        return 0

    sem = asyncio.Semaphore(concurrency)
    report = {"started_at": datetime.now(timezone.utc).isoformat(),
              "dry_run": dry_run, "purge_legacy": purge_legacy,
              "total": total, "migrated": 0, "skipped": 0,
              "errors": [], "purged": 0}

    async def process(doc: dict):
        async with sem:
            mid  = doc.get("id") or str(doc.get("_id"))
            ct   = doc.get("content_type") or "application/octet-stream"
            ext  = _ext_of(doc.get("filename", ""), ct) or ".bin"

            # Resolve bytes: prefer disk file (accurate), fallback to base64
            raw: bytes | None = None
            src = None
            if doc.get("stored_filename"):
                p = Path(MEDIA_DIR) / doc["stored_filename"]
                if p.exists():
                    raw = p.read_bytes(); src = "disk"
            if raw is None and doc.get("data"):
                try:
                    raw = base64.b64decode(doc["data"]); src = "base64"
                except Exception as e:
                    report["errors"].append({"id": mid, "error": f"base64 decode: {e}"})
                    return
            if raw is None:
                report["errors"].append({"id": mid, "error": "no source bytes"})
                return

            user_id = doc.get("user_id") or "legacy"
            key = build_key(tenant_id="legacy", client_id=user_id,
                            campaign_id="migrated", ext=ext)
            if dry_run:
                print(f"  [dry] would upload {mid} ({src}, {len(raw)}B) → r2://{R2_BUCKET}/{key}")
                report["skipped"] += 1
                return

            try:
                info = await r2_put_bytes(key, raw, ct)
            except Exception as e:
                report["errors"].append({"id": mid, "error": f"r2_put: {e}"})
                return

            # Verify head_object before touching Mongo
            head = await r2_head(key)
            if not head:
                report["errors"].append({"id": mid, "error": "head_object empty after put"})
                return

            update = {
                "storage":    "r2",
                "r2_key":     key,
                "r2_etag":    (info.get("etag") or "").strip('"'),
                "public_url": public_url_for_key(key),
                "size":       int(head.get("ContentLength") or len(raw)),
                "status":     "ready",
                "migrated_at": datetime.now(timezone.utc),
                "migrated_from": src,
            }
            unset = {}
            if purge_legacy:
                if src == "disk":
                    try: (Path(MEDIA_DIR) / doc["stored_filename"]).unlink()
                    except Exception: pass
                unset = {"data": "", "stored_filename": ""}
                report["purged"] += 1

            ops = {"$set": update}
            if unset: ops["$unset"] = unset
            await db.media.update_one({"_id": doc["_id"]}, ops)
            report["migrated"] += 1
            if report["migrated"] % 10 == 0:
                print(f"  migrated: {report['migrated']}/{total}")

    tasks = []
    async for doc in db.media.find(query):
        tasks.append(process(doc))
    await asyncio.gather(*tasks)

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    out = Path(f"/tmp/media_migration_{datetime.now().strftime('%Y%m%d-%H%M')}.json")
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"\n✅ Done. Report: {out}")
    print(f"   migrated={report['migrated']}  skipped={report['skipped']}  errors={len(report['errors'])}  purged={report['purged']}")
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Report only, no writes")
    ap.add_argument("--purge-legacy", action="store_true",
                    help="AFTER migration, also delete data/stored_filename from Mongo and disk")
    ap.add_argument("--concurrency", type=int, default=5)
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.dry_run, args.purge_legacy, args.concurrency)))
