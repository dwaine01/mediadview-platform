"""widgets_routes.py -- the 2 /widgets/{widget_id}/* rendering routes:
render (type-specific inline HTML/CSS/JS for player display) and weather
(server-side OpenWeatherMap proxy so the API key never reaches clients).

Fase 2B-10b of the modularization plan (see docs/REFACTOR_FASE2_PLAN.md).
Pure relocation: identical paths, methods, decorators and logic, registered
on a router with prefix="/api" so the final routes match api_router exactly
as before. No behavior change.

Dependency notes:
  - _esc is threaded in: it stays defined in server.py because it's already
    threaded into create_menus_routes(...) (Fase 2B-1) -- same shared-helper
    pattern as _bump_playlist_screens, just one phase later for this
    particular caller.
  - db (database.py) is imported directly, same precedent as every prior
    phase.
  - _safe_iframe, _safe_css_color, _safe_js_str, _safe_yt_id and the
    in-memory _weather_cache / _WEATHER_CACHE_TTL_S move here fully:
    grep-verified across every file in backend/ (not just server.py) that
    none has any call site outside this exact line range.
  - html as html_lib, json and re are imported directly (stdlib), same as
    server.py's own top-level imports.
  - logger: server.py's `logger = logging.getLogger(__name__)` is NOT
    threaded here. Each module getting its own `logging.getLogger(__name__)`
    is the idiomatic pattern (it's how server.py itself does it) and
    behaves identically at runtime -- the only difference is the logger's
    `name` shows "widgets_routes" instead of "server" in log output, which
    is arguably clearer. Flagged explicitly since it's the one line in this
    phase that isn't a byte-for-byte relocation of executable logic.
  - security_headers.py's CSP audit docstring mentions render_widget() by
    name as a source of inline <script>/<style> blocks (a pre-existing,
    unrelated tech-debt item, not a code dependency) -- checked, it's a
    comment describing behavior, not an import; moving the function changes
    nothing about that audit finding since the URL and behavior are
    unchanged.
  - Same reindent()/protected_rows() docstring-continuation defect flagged
    in Fase 2B-9 showed up again here: widget_weather_proxy's docstring is
    the only multi-line one in this batch, and it got the same explicit,
    count()==1-verified, round-trip-aware manual fix instead of carrying
    the defect forward a second time.
"""
import html as html_lib
import json
import logging
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from database import db

logger = logging.getLogger(__name__)

def _safe_iframe(v: str) -> str:
    """Only https:// or http:// allowed for iframe src — never javascript:, data:."""
    s = str(v or "").strip()
    if s.lower().startswith("https://") or s.lower().startswith("http://"):
        return html_lib.escape(s, quote=True)
    return "about:blank"

def _safe_css_color(v: str, default: str = "#000000") -> str:
    """Accept only CSS hex colours (#RGB, #RRGGBB, #RRGGBBAA). Rejects anything else."""
    s = str(v or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3}(?:[0-9a-fA-F]{2})?)?", s):
        return s
    return default

def _safe_js_str(v) -> str:
    """Return a JSON-encoded string literal safe for JS string context (includes quotes).
    Use when the value goes directly into a <script> block as a quoted string."""
    return json.dumps(str(v or ""))

def _safe_yt_id(v: str) -> str:
    """Validate a YouTube video ID (alphanumeric, underscore, hyphen; 1-20 chars)."""
    s = str(v or "")
    return s if re.fullmatch(r"[a-zA-Z0-9_\-]{1,20}", s) else ""

# ── In-memory weather cache (SEC-003: API key never exposed to clients) ───────
_weather_cache: dict = {}   # widget_id -> {"data": {...}, "ts": float}
_WEATHER_CACHE_TTL_S = 600  # 10 minutes


def create_widgets_routes(_esc):
    router = APIRouter(prefix="/api", tags=["Widgets"])

    @router.get("/widgets/{widget_id}/render", response_class=HTMLResponse)
    async def render_widget(widget_id: str):
        """Render widget as full HTML page for player display."""
        w = await db.widgets.find_one({"id": widget_id})
        if not w: raise HTTPException(status_code=404, detail="Widget not found")
        cfg = w.get("config", {})
        wt = w.get("widget_type")

        base_style = "body{margin:0;font-family:'Inter',Arial,sans-serif;background:#000;color:#fff;display:flex;align-items:center;justify-content:center;min-height:100vh;overflow:hidden}"

        if wt == "weather":
            # SEC-003 FIX: city is HTML-escaped; API key NEVER emitted to client.
            # The widget fetches weather from our server-side proxy endpoint.
            city_raw = cfg.get("city", "New York")
            city_escaped = _esc(city_raw)
            proxy_url = f"/api/widgets/{html_lib.escape(widget_id, quote=True)}/weather"
            html = f"""<html><head><style>{base_style}.w{{text-align:center}}.temp{{font-size:120px;font-weight:900}}.city{{font-size:28px;color:#94a3b8}}.desc{{font-size:22px;color:#22d3ee;margin-top:8px}}</style></head><body><div class="w"><div class="city">{city_escaped}</div><div class="temp" id="temp">--°</div><div class="desc" id="desc">Loading...</div></div><script>
        fetch({_safe_js_str(proxy_url)})
        .then(function(r){{return r.json()}})
        .then(function(d){{if(d.temp!==undefined){{document.getElementById('temp').textContent=Math.round(d.temp)+'°F';document.getElementById('desc').textContent=d.desc||''}}else{{document.getElementById('desc').textContent='Unavailable'}}}})
        .catch(function(){{document.getElementById('desc').textContent={_safe_js_str(city_raw)}}});
        </script></body></html>"""

        elif wt == "clock":
            # SEC-003 FIX: fmt allowed only "12h"/"24h"; bg validated as CSS colour.
            fmt_raw = cfg.get("format", "12h")
            fmt = "12h" if fmt_raw not in ("12h", "24h") else fmt_raw
            bg = _safe_css_color(cfg.get("bg_color", "#000000"), default="#000000")
            html = f"""<html><head><style>{base_style}body{{background:{bg}}}.c{{text-align:center}}.time{{font-size:140px;font-weight:900;letter-spacing:-4px}}.date{{font-size:32px;color:#64748b;margin-top:8px}}</style></head><body><div class="c"><div class="time" id="t"></div><div class="date" id="d"></div></div><script>
        function u(){{var n=new Date(),h=n.getHours(),m=String(n.getMinutes()).padStart(2,'0'),ap='';
        if({_safe_js_str(fmt)}==='12h'){{ap=h>=12?' PM':' AM';h=h%12||12}}
        document.getElementById('t').textContent=h+':'+m+ap;
        document.getElementById('d').textContent=n.toLocaleDateString('en-US',{{weekday:'long',month:'long',day:'numeric',year:'numeric'}})}}
        u();setInterval(u,1000);
        </script></body></html>"""

        elif wt == "ticker":
            # SEC-003 FIX: text HTML-escaped; speed coerced to int; bg validated.
            text = _esc(cfg.get("text", "Welcome to MediAd View Digital Signage Platform"))
            try:
                speed = max(10, min(300, int(cfg.get("speed", 80))))
            except (ValueError, TypeError):
                speed = 80
            bg = _safe_css_color(cfg.get("bg_color", "#111827"), default="#111827")
            html = f"""<html><head><style>body{{margin:0;background:{bg};display:flex;align-items:center;height:100vh;overflow:hidden}}.t{{white-space:nowrap;font-size:48px;font-weight:700;color:#22d3ee;font-family:Arial,sans-serif;animation:scroll {speed}s linear infinite}}@keyframes scroll{{0%{{transform:translateX(100vw)}}100%{{transform:translateX(-100%)}}}}</style></head><body><div class="t">{text}</div></body></html>"""

        elif wt == "qrcode":
            # SEC-003 FIX: label HTML-escaped; url JSON-encoded for JS string context.
            url_raw = cfg.get("url", "https://mediadview.com")
            # Only allow https/http for QR code target
            url_safe_js = _safe_js_str(url_raw if url_raw.lower().startswith(("https://", "http://")) else "https://mediadview.com")
            label = _esc(cfg.get("label", "Scan Me"))
            html = f"""<html><head><script src="https://cdn.jsdelivr.net/npm/qrcode-generator@1.4.4/qrcode.min.js"></script><style>{base_style}.q{{text-align:center}}.label{{font-size:28px;color:#22d3ee;margin-top:20px}}</style></head><body><div class="q"><div id="qr"></div><div class="label">{label}</div></div><script>
        var q=qrcode(0,'M');q.addData({url_safe_js});q.make();
        document.getElementById('qr').innerHTML=q.createSvgTag(8,0);
        document.querySelector('svg').style.width='300px';document.querySelector('svg').style.height='300px';
        </script></body></html>"""

        elif wt == "countdown":
            # SEC-003 FIX: title HTML-escaped; target date validated + JSON-encoded for JS.
            title = _esc(cfg.get("title", "Coming Soon"))
            target_raw = cfg.get("target_date", "2026-12-31T00:00:00")
            # Validate ISO date format (YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD)
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2})?", str(target_raw)):
                target_raw = "2099-12-31T00:00:00"
            target_js = _safe_js_str(target_raw)
            html = f"""<html><head><style>{base_style}.c{{text-align:center}}.title{{font-size:36px;color:#22d3ee;margin-bottom:30px}}.nums{{display:flex;gap:20px;justify-content:center}}.n{{background:#111827;padding:20px 30px;border-radius:16px;border:1px solid #1e293b}}.n .v{{font-size:72px;font-weight:900}}.n .l{{font-size:14px;color:#64748b}}</style></head><body><div class="c"><div class="title">{title}</div><div class="nums"><div class="n"><div class="v" id="d">0</div><div class="l">Days</div></div><div class="n"><div class="v" id="h">0</div><div class="l">Hours</div></div><div class="n"><div class="v" id="m">0</div><div class="l">Minutes</div></div><div class="n"><div class="v" id="s">0</div><div class="l">Seconds</div></div></div></div><script>
        function u(){{var t=new Date({target_js})-new Date();if(t<0)t=0;var d=Math.floor(t/86400000),h=Math.floor(t%86400000/3600000),m=Math.floor(t%3600000/60000),s=Math.floor(t%60000/1000);
        document.getElementById('d').textContent=d;document.getElementById('h').textContent=h;document.getElementById('m').textContent=m;document.getElementById('s').textContent=s}}u();setInterval(u,1000);
        </script></body></html>"""

        elif wt == "slides":
            # SEC-003 FIX: iframe src validated (https/http only).
            url = _safe_iframe(cfg.get("url", ""))
            html = f"""<html><head><style>body{{margin:0}}iframe{{width:100vw;height:100vh;border:none}}</style></head><body><iframe src="{url}" allowfullscreen></iframe></body></html>"""

        elif wt == "youtube":
            # SEC-003 FIX: video_id strictly validated (alphanumeric + _ -).
            video_id = _safe_yt_id(cfg.get("video_id", ""))
            if video_id:
                embed_url = f"https://www.youtube.com/embed/{video_id}?autoplay=1&mute=1&loop=1&playlist={video_id}&controls=0"
                html = f"""<html><head><style>body{{margin:0;background:#000}}iframe{{width:100vw;height:100vh;border:none}}</style></head><body><iframe src="{embed_url}" allowfullscreen allow="autoplay"></iframe></body></html>"""
            else:
                html = "<html><body style='background:#000;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh'>Invalid video ID</body></html>"

        elif wt == "webpage":
            # SEC-003 FIX: iframe src validated (https/http only).
            url = _safe_iframe(cfg.get("url", "https://google.com"))
            html = f"""<html><head><style>body{{margin:0}}iframe{{width:100vw;height:100vh;border:none}}</style></head><body><iframe src="{url}"></iframe></body></html>"""

        elif wt == "menu":
            # SEC-003 FIX: title and item fields HTML-escaped.
            title = _esc(cfg.get("title", "Today's Menu"))
            items = cfg.get("items", [{"name": "Burger", "price": "$12"}, {"name": "Pizza", "price": "$15"}, {"name": "Salad", "price": "$10"}])
            items_html = "".join([
                f'<div class="item"><span>{_esc(i.get("name",""))}</span><span class="dots"></span><span class="p">{_esc(str(i.get("price","")))}</span></div>'
                for i in items
            ])
            html = f"""<html><head><style>{base_style}body{{background:#0a0f1a}}.m{{width:80%;max-width:600px}}.title{{font-size:48px;font-weight:900;color:#22d3ee;text-align:center;margin-bottom:40px}}.item{{display:flex;align-items:baseline;font-size:28px;padding:16px 0;border-bottom:1px solid #1e293b}}.dots{{flex:1;border-bottom:2px dotted #334155;margin:0 12px}}.p{{color:#22d3ee;font-weight:700}}</style></head><body><div class="m"><div class="title">{title}</div>{items_html}</div></body></html>"""

        elif wt == "calendar":
            html = f"""<html><head><style>{base_style}body{{background:#0a0f1a}}.cal{{text-align:center;width:90%}}.month{{font-size:36px;font-weight:700;color:#22d3ee;margin-bottom:20px}}.grid{{display:grid;grid-template-columns:repeat(7,1fr);gap:4px}}.hd{{font-size:14px;color:#64748b;padding:8px}}.day{{font-size:20px;padding:12px;border-radius:8px}}.day.today{{background:#6366f1;color:#fff;font-weight:700}}</style></head><body><div class="cal"><div class="month" id="mon"></div><div class="grid" id="gr"></div></div><script>
        var n=new Date(),y=n.getFullYear(),m=n.getMonth();
        document.getElementById('mon').textContent=n.toLocaleDateString('en-US',{{month:'long',year:'numeric'}});
        var days=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
        var h=days.map(d=>'<div class="hd">'+d+'</div>').join('');
        var first=new Date(y,m,1).getDay(),last=new Date(y,m+1,0).getDate();
        var cells='';for(var i=0;i<first;i++)cells+='<div class="day"></div>';
        for(var d=1;d<=last;d++)cells+='<div class="day'+(d===n.getDate()?' today':'')+'">'+d+'</div>';
        document.getElementById('gr').innerHTML=h+cells;
        </script></body></html>"""

        else:
            # SEC-003 FIX: widget type HTML-escaped in fallback message.
            wt_safe = _esc(wt or "unknown")
            html = f"<html><body style='background:#000;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh'>Unknown widget type: {wt_safe}</body></html>"

        return HTMLResponse(content=html)

    @router.get("/widgets/{widget_id}/weather")
    async def widget_weather_proxy(widget_id: str):
        """SEC-003 — Server-side weather proxy.
        The OpenWeatherMap API key is read from the DB config and NEVER sent to clients.
        Results are cached in-memory for 10 minutes to reduce upstream calls.
        """
        import time

        import httpx as _httpx
        w = await db.widgets.find_one({"id": widget_id, "widget_type": "weather"})
        if not w:
            raise HTTPException(status_code=404, detail="Weather widget not found")

        cfg = w.get("config", {})
        api_key = cfg.get("api_key", "")
        city = str(cfg.get("city", "New York"))

        if not api_key:
            return {"temp": None, "desc": "No API key configured", "city": city}

        # Check cache
        cached = _weather_cache.get(widget_id)
        now_ts = time.time()
        if cached and (now_ts - cached["ts"]) < _WEATHER_CACHE_TTL_S:
            return cached["data"]

        try:
            async with _httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={"q": city, "appid": api_key, "units": "imperial"},
                )
                resp.raise_for_status()
                ow = resp.json()
            result = {
                "city": city,
                "temp": round(ow.get("main", {}).get("temp", 0)),
                "desc": (ow.get("weather") or [{}])[0].get("description", ""),
            }
        except Exception as exc:
            logger.warning("Weather proxy failed for widget %s: %s", widget_id, exc)
            result = {"city": city, "temp": None, "desc": "Unavailable"}

        _weather_cache[widget_id] = {"data": result, "ts": now_ts}
        return result

    return router
