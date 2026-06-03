# MediAd View — Windows Print Agent

This small program runs in the background on your Windows PC and **automatically prints invoices, contracts and deposits** that the MediAd View server queues for printing.

It is needed because the MediAd View server runs in the cloud and cannot talk directly to your USB printer. The agent acts as a bridge.

---

## ⚡ Quick Install (Windows)

1. **Install Python 3.10 or newer**
   Download from <https://www.python.org/downloads/> and during installation **check the box "Add Python to PATH"**.

2. **Install required Python packages**
   Open *Command Prompt* (`cmd`) and run:
   ```bat
   pip install requests pywin32
   ```

3. **Download SumatraPDF (free PDF viewer used for silent printing)**
   <https://www.sumatrapdfreader.org/download-free-pdf-viewer> → choose the **portable .exe (64-bit)**.
   Save `SumatraPDF.exe` **in the same folder as `print_agent.py`**.

4. **Get your agent token from MediAd View**
   In the web app, go to **Finance → Settings → Print Agent**, copy the token shown there.

5. **Configure**
   Run `start-print-agent.bat` once. It will create a file `print_agent.config.json`. Open it in Notepad and paste:
   ```json
   {
     "server_url": "https://www.mediadview.com",
     "token": "PASTE-YOUR-TOKEN-HERE",
     "printer": "",
     "poll_seconds": 30,
     "copies": 1
   }
   ```
   - `server_url`: your MediAd View domain (no trailing slash)
   - `token`: copy from Finance → Settings → Print Agent
   - `printer`: leave empty `""` to use Windows default; or put the exact printer name shown in Windows (e.g. `"HP LaserJet 4520"`).
   - `poll_seconds`: how often the agent asks the server for new jobs (30s is fine).
   - `copies`: extra copies per document (1 = single sheet).

6. **Start the agent**
   Double-click `start-print-agent.bat`. A black console window will open and you should see:
   ```
   ✓ Authenticated with server
   ```

7. **Make it run automatically when Windows starts**
   - Press `Win + R`, type `shell:startup`, press Enter.
   - Right-click → **New → Shortcut** → browse to `start-print-agent.bat` → Finish.
   - Done. Every time the PC boots, the agent will start.

---

## 🔍 How it works

- Every 30 seconds the agent calls the MediAd View server: *"any pending print jobs?"*
- When a new invoice is auto-generated (day 1 of each month at 11:00 AM Eastern), the server queues it.
- The agent downloads the PDF and sends it silently to your default printer using SumatraPDF.
- The job is then marked **printed** in the dashboard (Finance → Print Queue).

## 🧪 Test the flow

1. In the web app, open any Invoice → click **"Send to Printer"** (this enqueues it).
2. Within 30 seconds the agent prints it.
3. Open `print_agent.log` (next to the script) to see activity.

## 🛠 Troubleshooting

| Issue | Fix |
|---|---|
| `Cannot authenticate` | Wrong `token` or `server_url`. Check Finance → Settings → Print Agent. |
| Nothing prints, no errors | Make sure `SumatraPDF.exe` is in the same folder. Check that the default printer works from Notepad. |
| Prints come out blank | Update your printer driver. Try changing `"printer"` to the exact name shown in Windows. |
| Agent stops when I close the console | Set it to start with Windows (step 7 above) and don't close the window — minimize it instead. |

## 📁 Files in this folder

- `print_agent.py` — the agent (Python script)
- `start-print-agent.bat` — launches the agent
- `print_agent.config.json` — your settings
- `print_agent.log` — activity log
- `SumatraPDF.exe` — silent PDF printer (you download this)
- `downloads/` — temporary folder for the downloaded PDFs
