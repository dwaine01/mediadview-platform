#!/usr/bin/env python3
"""
MediAd View — Windows Print Agent
==================================
Polls the MediAd View server every N seconds for pending print jobs,
downloads each PDF and prints it silently to the default Windows printer.

INSTALLATION (Windows)
----------------------
1) Install Python 3.10+ from https://www.python.org/downloads/  (check "Add to PATH")
2) Open Command Prompt (cmd) and run:
       pip install requests pywin32
3) Download SumatraPDF (portable .exe) for silent printing:
       https://www.sumatrapdfreader.org/download-free-pdf-viewer
   Place SumatraPDF.exe in the SAME folder as this script.
4) Edit print_agent.config.json (next to this script) with:
       {
         "server_url": "https://YOUR-SERVER.com",
         "token":      "PASTE-YOUR-AGENT-TOKEN-HERE",
         "printer":    "",                  // empty = default printer
         "poll_seconds": 30,
         "copies": 1
       }
5) Run the agent:
       python print_agent.py
   (or double-click the included `start-print-agent.bat`)

To run automatically on Windows startup:
  - Press Win + R, type:  shell:startup
  - Drop a shortcut to `start-print-agent.bat` into that folder.

LOGS
----
Activity is written to print_agent.log next to this script.
"""
import os
import sys
import json
import time
import logging
import subprocess
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run:  pip install requests")
    sys.exit(1)

# Optional Windows printing
try:
    import win32print
    import win32api
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

# =============== CONFIG ===============
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "print_agent.config.json"
LOG_FILE = SCRIPT_DIR / "print_agent.log"
DOWNLOADS = SCRIPT_DIR / "downloads"
DOWNLOADS.mkdir(exist_ok=True)
SUMATRA = SCRIPT_DIR / "SumatraPDF.exe"

DEFAULT_CONFIG = {
    "server_url": "https://your-server.com",
    "token": "PASTE-YOUR-AGENT-TOKEN-HERE",
    "printer": "",
    "poll_seconds": 30,
    "copies": 1,
}


def setup_logging():
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def load_config():
    if not CONFIG_FILE.exists():
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        print(f"\n❗ Created template config: {CONFIG_FILE}")
        print("  Edit it with your server URL and agent token, then run again.\n")
        sys.exit(1)
    with open(CONFIG_FILE) as f:
        cfg = json.load(f)
    # Validate
    if cfg.get("token", "").startswith("PASTE"):
        print(f"\n❗ Please edit {CONFIG_FILE} and paste your real token.\n")
        sys.exit(1)
    if not cfg.get("server_url", "").startswith("http"):
        print(f"\n❗ Please set a valid server_url in {CONFIG_FILE}\n")
        sys.exit(1)
    return cfg


# =============== PRINTING ===============
def print_pdf(pdf_path: Path, printer_name: str = "", copies: int = 1) -> bool:
    """Print silently. Returns True on success.

    Strategy:
      1) If SumatraPDF.exe is bundled next to this script, use it (best silent print).
      2) Else use win32api.ShellExecute "printto" (default printer; may open viewer briefly).
      3) Else os.startfile("print") as last resort.
    """
    pdf_path = str(pdf_path)
    # ---- 1) SumatraPDF (preferred) ----
    if SUMATRA.exists():
        args = [str(SUMATRA), "-silent", "-print-to-default" if not printer_name else "-print-to", ]
        if printer_name:
            args.append(printer_name)
        # Settings: number of copies
        if copies and copies > 1:
            args.extend(["-print-settings", f"{copies}x"])
        args.append(pdf_path)
        try:
            logging.info(f"  → SumatraPDF print: {args}")
            r = subprocess.run(args, capture_output=True, timeout=120)
            if r.returncode == 0:
                return True
            logging.error(f"  ✗ SumatraPDF returned {r.returncode}: {r.stderr.decode(errors='ignore')}")
        except Exception as e:
            logging.exception(f"  ✗ SumatraPDF call failed: {e}")

    # ---- 2) win32api ShellExecute ----
    if HAS_WIN32:
        try:
            printer = printer_name or win32print.GetDefaultPrinter()
            logging.info(f"  → ShellExecute printto: {printer}")
            win32api.ShellExecute(0, "printto", pdf_path, f'"{printer}"', ".", 0)
            time.sleep(8)  # let the spooler accept the job
            return True
        except Exception as e:
            logging.exception(f"  ✗ ShellExecute failed: {e}")

    # ---- 3) os.startfile ----
    try:
        logging.info("  → os.startfile('print')")
        os.startfile(pdf_path, "print")
        time.sleep(8)
        return True
    except Exception as e:
        logging.exception(f"  ✗ os.startfile failed: {e}")
        return False


# =============== API ===============
class Api:
    def __init__(self, cfg):
        self.base = cfg["server_url"].rstrip("/")
        self.s = requests.Session()
        self.s.headers["X-Print-Token"] = cfg["token"]

    def ping(self):
        r = self.s.get(self.base + "/api/finance/print/agent/ping", timeout=15)
        r.raise_for_status()
        return r.json()

    def pending(self, limit=10):
        r = self.s.get(self.base + "/api/finance/print/agent/pending",
                       params={"limit": limit}, timeout=20)
        r.raise_for_status()
        return r.json().get("jobs", [])

    def download(self, job_id, dest: Path):
        r = self.s.get(self.base + f"/api/finance/print/agent/document/{job_id}",
                       stream=True, timeout=60)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(64 * 1024):
                f.write(chunk)
        return dest

    def complete(self, job_id):
        r = self.s.post(self.base + f"/api/finance/print/agent/{job_id}/complete", timeout=15)
        r.raise_for_status()

    def fail(self, job_id, error):
        try:
            self.s.post(self.base + f"/api/finance/print/agent/{job_id}/fail",
                        json={"error": str(error)[:300]}, timeout=15)
        except Exception:
            pass


# =============== MAIN LOOP ===============
def main():
    setup_logging()
    cfg = load_config()
    api = Api(cfg)
    printer = cfg.get("printer") or ""
    copies = max(1, int(cfg.get("copies", 1)))
    interval = max(10, int(cfg.get("poll_seconds", 30)))

    logging.info("=" * 60)
    logging.info("MediAd View Print Agent")
    logging.info(f"  Server:   {cfg['server_url']}")
    logging.info(f"  Printer:  {printer or '(default)'}")
    logging.info(f"  Polling:  every {interval}s")
    logging.info(f"  SumatraPDF: {'YES' if SUMATRA.exists() else 'no (will fall back to win32)'}")
    logging.info("=" * 60)

    # Quick auth check
    try:
        api.ping()
        logging.info("✓ Authenticated with server")
    except Exception as e:
        logging.error(f"✗ Cannot authenticate: {e}")
        logging.error("  Check server_url and token in print_agent.config.json")

    while True:
        try:
            jobs = api.pending(limit=10)
            if jobs:
                logging.info(f"📥 {len(jobs)} job(s) pending")
                for j in jobs:
                    jid = j["id"]
                    kind = j.get("kind", "doc")
                    docno = j.get("doc_number", "")
                    label = f"{kind.upper()} {docno}"
                    logging.info(f"  • {label}  [{jid[:8]}]")
                    try:
                        pdf = DOWNLOADS / f"{kind}_{docno or jid[:8]}.pdf"
                        api.download(jid, pdf)
                        n_copies = max(1, int(j.get("copies", 1)) * copies)
                        ok = print_pdf(pdf, printer_name=printer, copies=n_copies)
                        if ok:
                            api.complete(jid)
                            logging.info(f"  ✓ Printed {label}")
                        else:
                            api.fail(jid, "All print strategies failed")
                            logging.error(f"  ✗ Failed to print {label}")
                    except Exception as e:
                        logging.exception(f"  ✗ Error on job {jid}: {e}")
                        api.fail(jid, str(e))
        except requests.exceptions.RequestException as e:
            logging.warning(f"Network error: {e}")
        except Exception as e:
            logging.exception(f"Loop error: {e}")
        time.sleep(interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
