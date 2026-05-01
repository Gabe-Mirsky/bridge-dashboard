"""FastAPI backend for the Bridge Markets Dashboard.

This app serves the single-page dashboard shell, exposes JSON endpoints that the
browser polls on a schedule, and handles the lightweight GitHub webhook used by
the Oracle auto-deploy flow.
"""

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import time
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import math
import re
from threading import Thread
import time
import json
import os
import io
from datetime import date, timedelta, datetime
import zipfile
from pathlib import Path
import subprocess
import hashlib
import hmac
from urllib.parse import urljoin


app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
DEPLOY_BRANCH = os.getenv("DEPLOY_BRANCH", "refs/heads/main")
DEPLOY_SCRIPT_PATH = Path(
    os.getenv("DEPLOY_SCRIPT_PATH", str(BASE_DIR / "deploy-webhook.sh"))
)
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
DEPLOY_LOG_PATH = Path(
    os.getenv("DEPLOY_LOG_PATH", str(BASE_DIR / "deploy-webhook.log"))
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=BASE_DIR), name="static")

@app.get("/")
def get_index():
    # Cache-bust CSS/JS automatically so wallboard browsers pick up edits
    # without requiring anyone to manually clear browser caches.
    index_path = BASE_DIR / "index.html"
    html = index_path.read_text(encoding="utf-8")

    style_version = (BASE_DIR / "style.css").stat().st_mtime_ns
    script_version = (BASE_DIR / "script.js").stat().st_mtime_ns

    html = html.replace(
        'href="/static/style.css"',
        f'href="/static/style.css?v={style_version}"'
    )
    html = html.replace(
        'src="/static/script.js"',
        f'src="/static/script.js?v={script_version}"'
    )

    return HTMLResponse(html)

def _verify_github_signature(payload: bytes, signature_header: str | None) -> bool:
    # Reject unsigned or incorrectly signed GitHub webhooks before any deploy work.
    if not GITHUB_WEBHOOK_SECRET or not signature_header:
        return False

    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)

def _run_deploy_script() -> dict:
    # Synchronous deploy helper kept mainly for manual debugging.
    if not DEPLOY_SCRIPT_PATH.exists():
        raise FileNotFoundError(f"Deploy script not found: {DEPLOY_SCRIPT_PATH}")

    result = subprocess.run(
        [str(DEPLOY_SCRIPT_PATH)],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )

    stdout_tail = (result.stdout or "").strip()[-4000:]
    stderr_tail = (result.stderr or "").strip()[-4000:]

    return {
        "returncode": result.returncode,
        "stdout": stdout_tail,
        "stderr": stderr_tail,
    }

def _launch_deploy_script() -> None:
    # Production deploys run in the background so GitHub is not blocked waiting
    # for `git pull` and service restart work to finish.
    if not DEPLOY_SCRIPT_PATH.exists():
        raise FileNotFoundError(f"Deploy script not found: {DEPLOY_SCRIPT_PATH}")

    log_handle = open(DEPLOY_LOG_PATH, "a", encoding="utf-8")
    timestamp = datetime.now(timezone.utc).isoformat()
    log_handle.write(f"\n=== Deploy triggered {timestamp} ===\n")
    log_handle.flush()

    subprocess.Popen(
        [str(DEPLOY_SCRIPT_PATH)],
        cwd=str(BASE_DIR),
        stdout=log_handle,
        stderr=log_handle,
        text=True,
        start_new_session=True,
        close_fds=True,
    )

@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
):
    # Only signed push events for the configured branch should trigger deploys.
    payload = await request.body()

    if not _verify_github_signature(payload, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature")

    try:
        body = json.loads(payload.decode("utf-8")) if payload else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    if x_github_event == "ping":
        return {"status": "ok", "message": "GitHub webhook received"}

    if x_github_event != "push":
        return {"status": "ignored", "reason": f"Unsupported event: {x_github_event}"}

    ref = body.get("ref", "")
    if ref != DEPLOY_BRANCH:
        return {"status": "ignored", "reason": f"Push was for {ref or 'unknown ref'}"}

    _launch_deploy_script()

    return {
        "status": "accepted",
        "ref": ref,
        "message": "Deploy started in background",
    }

# =========================================================
# CACHE
# =========================================================

# These short-lived in-memory caches smooth out frequent dashboard polling.
cache = {}
news_cache = {"data": None, "timestamp": 0}
event_watch_cache = {"data": None, "timestamp": 0}
oil_gas_cache = {"data": None, "timestamp": 0}
weather_dashboard_cache = {"data": None, "timestamp": 0}

CACHE_DURATION = 60
EVENT_CACHE_DURATION = 60
OIL_GAS_CACHE_DURATION = 60
WEATHER_CACHE_DURATION = 900

# =========================================================
# GEO CONFIG (Pentagon Distance System)
# =========================================================

PENTAGON_LAT = 38.8719
PENTAGON_LON = -77.0563

def haversine_miles(lat1, lon1, lat2, lon2):
    """Distance helper used by the event-watch / geo logic."""
    R = 3958.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2)
        * math.sin(dlambda / 2) ** 2
    )

    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# Hardcoded stable coordinates avoid depending on live geocoding for fixed places.
PIZZA_COORDS = {
    "ChIJcYireCe3t4kR4d9trEbGYjc": (38.8602396, -77.0559854),
    "ChIJ42QeLXu3t4kRnArvcaz2o3A": (38.8527414, -77.0531408),
    "ChIJS1rpOC-3t4kRsLyM6aftM8k": (38.8551791, -77.049733),
    "ChIJo03BaX-3t4kRbyhPM0rTuqM": (38.8606821, -77.0922272),
    "ChIJrbin_Qm3t4kRVSytw_2DM1g": (38.8806865, -77.089827),
    "ChIJI6ACK7q2t4kRFcPtFhUuYhU": (38.8627267, -77.0853943),
}

# =========================================================
# DOUGHCON SYSTEM
# =========================================================

CURRENT_DOUGHCON = 4  # Manually controlled for now

DOUGHCON_COLORS = {
    1: "#ff0000",  # Extreme
    2: "#ff5c00",
    3: "#ffae00",
    4: "#00c853",  # Calm (current)
    5: "#2196f3"
}

NWS_HEADERS = {
    "User-Agent": "BridgeDashboard/1.0 (Bridge Dashboard Project)",
    "Accept": "application/geo+json"
}

WEATHER_LOCATIONS = {
    "boston": {"city_name": "Boston", "lat": 42.3601, "lon": -71.0589},
    "chicago": {"city_name": "Chicago", "lat": 41.8781, "lon": -87.6298},
    "hartford": {"city_name": "Hartford", "lat": 41.7658, "lon": -72.6734},
}

NOAA_OUTLOOK_SOURCES = [
    {
        "key": "week",
        "label": "1 Week NOAA",
        "url": "https://www.cpc.ncep.noaa.gov/products/predictions/6-10_day/",
        "image_url": "https://www.cpc.ncep.noaa.gov/products/predictions/610day/610temp.new.gif",
    },
    {
        "key": "month",
        "label": "1 Month NOAA",
        "url": "https://www.cpc.ncep.noaa.gov/products/predictions/30day/",
        "image_url": "https://www.cpc.ncep.noaa.gov/products/predictions/30day/off14_temp.gif",
    },
]

def _direct_get(url, headers=None, timeout=10):
    # Ignore proxy environment variables so weather/NOAA calls behave the same
    # locally and on the Oracle VM.
    session = requests.Session()
    session.trust_env = False
    return session.get(url, headers=headers, timeout=timeout)

# =========================================================
# HENRY HUB FUTURES (ROLLED FRONT + NEXT 6)
# Rule: during the last 7 calendar days of the month, skip the "next-month" contract
# because it is effectively settled/illiquid; start two months out instead.
# Returns: month label, last, change, percent (prefers Yahoo change fields when available)
# =========================================================

from calendar import monthrange

MONTH_CODES = {
    1: "F", 2: "G", 3: "H", 4: "J",
    5: "K", 6: "M", 7: "N", 8: "Q",
    9: "U", 10: "V", 11: "X", 12: "Z"
}

def _add_months(year: int, month: int, add: int) -> tuple[int, int]:
    m = month + add
    y = year + (m - 1) // 12
    m = ((m - 1) % 12) + 1
    return y, m

def _is_last_week_of_month(dt: datetime, days: int = 7) -> bool:
    last_day = monthrange(dt.year, dt.month)[1]
    return dt.day >= (last_day - (days - 1))  # last 7 calendar days inclusive

@app.get("/henry-hub")
def get_henry_hub():
    try:
        now = datetime.now()

        # Normal behavior: "front" is next month.
        # Last-week behavior: skip that next-month contract, start two months out.
        start_offset = 2 if _is_last_week_of_month(now, days=7) else 1

        want = 6
        found = []
        seen = set()

        # Scan forward enough to reliably fill 6 contracts even if Yahoo is missing one
        scan_limit = 18  # months ahead cap

        for step in range(start_offset, start_offset + scan_limit):
            y, m = _add_months(now.year, now.month, step)
            code = MONTH_CODES[m]
            year_code = str(y)[-2:]
            symbol = f"NG{code}{year_code}.NYM"

            if symbol in seen:
                continue
            seen.add(symbol)

            t = yf.Ticker(symbol)
            info = t.info or {}

            price = info.get("regularMarketPrice")
            prev_close = info.get("regularMarketPreviousClose")

            # Prefer Yahoo-provided change fields (more consistent than recompute)
            chg = info.get("regularMarketChange")
            chg_pct = info.get("regularMarketChangePercent")

            if price is None:
                continue

            # Fallback if change fields missing
            if chg is None and prev_close:
                chg = float(price) - float(prev_close)

            if chg_pct is None and prev_close and chg is not None:
                try:
                    chg_pct = (float(chg) / float(prev_close)) * 100
                except Exception:
                    chg_pct = None

            found.append({
                "symbol": symbol.replace(".NYM", ""),                 # e.g., NGJ26
                "month": datetime(y, m, 1).strftime("%b %y").upper(), # e.g., APR 26
                "price": round(float(price), 3),
                "change": round(float(chg), 3) if chg is not None else 0.0,
                "percent": round(float(chg_pct), 2) if chg_pct is not None else 0.0
            })

            if len(found) >= want:
                break

        return {"contracts": found}

    except Exception as e:
        return {"contracts": [], "error": str(e)}


# =========================================================
# ELECTRIC — ISO-NE + MISO + ERCOT
# Persistent Monthly Cache Architecture
# Keeps only current month + prior month
# =========================================================

ELECTRIC_CACHE = {
    "data": None,
    "last_update": None
}

ISO_FILE = "isone_history.json"
MISO_FILE = "miso_history.json"
ERCOT_FILE = "ercot_history.json"
ELECTRIC_DEBUG = True

# ---------------------------------------------------------
# GENERIC LOAD / SAVE
# ---------------------------------------------------------

def _load_json(file):
    """Read a JSON file defensively and fall back to an empty object."""
    if not os.path.exists(file):
        return {}
    try:
        with open(file, "r", encoding="utf-8") as f:
            raw = f.read().strip()
            if not raw:
                return {}
            return json.loads(raw)
    except Exception:
        return {}

def _save_json(file, data):
    """Persist JSON with stable formatting so history files stay diff-friendly."""
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# ---------------------------------------------------------
# MONTH HELPERS
# Electric history files intentionally keep only the current month and the
# immediately prior month. That is all Q1 needs for its MTD-vs-prior-month
# comparison, and it keeps the JSON files small and easy to inspect.
# ---------------------------------------------------------

def _month_str(d):
    return d.strftime("%Y-%m")

def _current_month_start():
    today = date.today()
    return today.replace(day=1)

def _prior_month_start():
    current_start = _current_month_start()
    return (current_start - timedelta(days=1)).replace(day=1)

def _empty_monthly_history(name):
    current_start = _current_month_start()
    prior_start = _prior_month_start()

    current_month = _month_str(current_start)
    prior_month = _month_str(prior_start)

    return {
        "name": name,
        "current_month": current_month,
        "prior_month": prior_month,
        "data": {
            prior_month: {},
            current_month: {}
        }
    }

def _load_or_reset_two_month_history(file, name):
    # Roll stale history files forward to the current/prior month pair while
    # preserving any data already collected for those exact month keys.
    history = _load_json(file)

    if not isinstance(history, dict):
        history = {}

    current_start = _current_month_start()
    prior_start = _prior_month_start()

    current_month = _month_str(current_start)
    prior_month = _month_str(prior_start)

    old_data = history.get("data", {})
    if not isinstance(old_data, dict):
        old_data = {}

    prior_data = old_data.get(prior_month, {})
    current_data = old_data.get(current_month, {})

    if not isinstance(prior_data, dict):
        prior_data = {}

    if not isinstance(current_data, dict):
        current_data = {}

    new_history = {
        "name": name,
        "current_month": current_month,
        "prior_month": prior_month,
        "data": {
            prior_month: prior_data,
            current_month: current_data
        }
    }

    if history != new_history:
        old_current = history.get("current_month") if isinstance(history, dict) else None
        old_prior = history.get("prior_month") if isinstance(history, dict) else None
        _electric_debug(
            f"{name} month rollover/reset from current={old_current}, prior={old_prior} "
            f"to current={current_month}, prior={prior_month}"
        )
        _save_json(file, new_history)

    return new_history

def _month_ranges_to_fill():
    # Backfill the prior month plus the current month up through today.
    today = date.today()
    current_start = _current_month_start()
    prior_start = _prior_month_start()
    prior_end = current_start - timedelta(days=1)

    return [
        (_month_str(prior_start), prior_start, prior_end),
        (_month_str(current_start), current_start, today),
    ]

def _electric_debug(message):
    # Centralized debug hook so temporary electric logging can be disabled in
    # one place after the feed issues are stable again.
    if ELECTRIC_DEBUG:
        print(f"[electric-debug] {message}")

# ---------------------------------------------------------
# GENERIC CSV / COLUMN HELPERS
# ---------------------------------------------------------

def _clean_col_name(name):
    # Normalize third-party CSV headers whose capitalization and punctuation drift.
    return re.sub(r"[^a-z0-9]+", "", str(name).strip().lower())

def _find_actual_column(df, aliases):
    # Match a real dataframe column against a list of expected header aliases.
    alias_set = {_clean_col_name(a) for a in aliases}
    for col in df.columns:
        if _clean_col_name(col) in alias_set:
            return col
    return None

def _find_header_row_by_aliases(text, alias_groups, max_scan_rows=80):
    # Some market exports prepend metadata rows before the real CSV header.
    lines = text.splitlines()

    for i, line in enumerate(lines[:max_scan_rows]):
        if not line or not line.strip():
            continue

        candidates = []

        for delim in [",", "\t"]:
            parts = [p.strip().strip('"') for p in line.split(delim)]
            candidates.append([_clean_col_name(p) for p in parts])

        for cells in candidates:
            matched_all = True
            for group in alias_groups:
                group_clean = {_clean_col_name(x) for x in group}
                if not any(cell in group_clean for cell in cells):
                    matched_all = False
                    break
            if matched_all:
                return i

    return None

def _load_csv_with_dynamic_header(text, alias_groups):
    # Try a few parse strategies after locating the likely header row so the
    # parser can survive minor upstream format changes.
    header_row = _find_header_row_by_aliases(text, alias_groups)
    if header_row is None:
        raise ValueError("Could not locate header row")

    sliced = "\n".join(text.splitlines()[header_row:])

    candidates = []

    try:
        df_comma = pd.read_csv(io.StringIO(sliced), sep=",", engine="python")
        df_comma.columns = [str(c).strip() for c in df_comma.columns]
        candidates.append(df_comma)
    except Exception:
        pass

    try:
        df_tab = pd.read_csv(io.StringIO(sliced), sep="\t", engine="python")
        df_tab.columns = [str(c).strip() for c in df_tab.columns]
        candidates.append(df_tab)
    except Exception:
        pass

    if not candidates:
        raise ValueError("Could not parse CSV after locating header row")

    def score_df(df):
        score = 0
        cleaned_cols = {_clean_col_name(c) for c in df.columns}
        for group in alias_groups:
            group_clean = {_clean_col_name(x) for x in group}
            if cleaned_cols & group_clean:
                score += 1
        score += min(len(df.columns), 200) / 1000.0
        return score

    return max(candidates, key=score_df)

# =========================================================
# ISO-NE — INTERNAL HUB
# =========================================================

def fetch_isone_daily_average(d):
    # ISO-NE publishes hourly rows for the requested day; average them into one
    # hub value so Q1 can show a clean month-to-date comparison.
    ymd = d.strftime("%Y%m%d")
    url = f"http://www.iso-ne.com/histRpts/da-lmp/WW_DALMP_ISO_{ymd}.csv"

    try:
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return None

        lines = r.text.splitlines()
        values = []

        for line in lines:
            clean = line.replace('"', '')
            if not clean.startswith("D,"):
                continue

            parts = clean.split(",")
            if len(parts) < 7:
                continue

            location_name = parts[4].strip()
            location_type = parts[5].strip()

            if location_type == "HUB" and location_name == ".H.INTERNAL_HUB":
                try:
                    values.append(float(parts[6]))
                except Exception:
                    continue

        if not values:
            return None

        return sum(values) / len(values)

    except Exception:
        return None

def update_iso_history():
    # Fill any missing days in the rolling two-month ISO-NE history window.
    history = _load_or_reset_two_month_history(ISO_FILE, "ISONE")
    data = history["data"]
    updated = False

    for month_key, start_date, end_date in _month_ranges_to_fill():
        if month_key not in data or not isinstance(data[month_key], dict):
            data[month_key] = {}

        d = start_date
        while d <= end_date:
            key = d.isoformat()
            if key not in data[month_key]:
                val = fetch_isone_daily_average(d)
                if val is not None:
                    data[month_key][key] = round(val, 5)
                    _electric_debug(f"ISONE added {key} = {round(val, 5)}")
                    updated = True
                else:
                    _electric_debug(f"ISONE missing {key}")
            d += timedelta(days=1)

    if updated:
        history["data"] = data
        _save_json(ISO_FILE, history)
        _electric_debug(
            f"ISONE history saved with months {history['prior_month']} and {history['current_month']}"
        )

    return history

# =========================================================
# MISO — ILLINOIS HUB
# =========================================================

def fetch_miso_daily_average(d):
    # MISO file headers and row labels drift over time, so this parser is
    # intentionally tolerant about where it finds Illinois Hub / LMP values.
    ymd = d.strftime("%Y%m%d")
    url = f"https://docs.misoenergy.org/marketreports/{ymd}_da_expost_lmp.csv"

    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return None

        df = _load_csv_with_dynamic_header(
            r.text,
            alias_groups=[
                ["Node", "CPNode", "Pricing Node", "Location"],
                ["Type"],
                ["Value"],
            ]
        )

        node_col = _find_actual_column(df, ["Node", "CPNode", "Pricing Node", "Location"])
        type_col = _find_actual_column(df, ["Type"])
        value_col = _find_actual_column(df, ["Value"])

        if node_col is None or type_col is None or value_col is None:
            return None

        base_df = df[
            df[node_col].astype(str).str.strip().str.upper().eq("ILLINOIS.HUB") &
            df[type_col].astype(str).str.strip().str.upper().eq("HUB")
        ]

        if base_df.empty:
            return None

        value_series = base_df[value_col].astype(str).str.strip().str.upper()
        lmp_df = base_df[
            value_series.eq("LMP") |
            value_series.str.contains("LMP", na=False) |
            value_series.str.contains("EXPOST", na=False)
        ]

        df = lmp_df if not lmp_df.empty else base_df

        hour_cols = [
            c for c in df.columns
            if re.fullmatch(r"HE\d{1,2}", str(c).strip(), flags=re.IGNORECASE)
        ]

        if not hour_cols:
            hour_cols = [c for c in df.columns if _clean_col_name(c).startswith("he")]

        if not hour_cols:
            return None

        values = df[hour_cols].values.flatten()
        values = pd.to_numeric(values, errors="coerce")
        values = values[~pd.isna(values)]

        if len(values) == 0:
            return None

        return float(values.mean())

    except Exception:
        return None

def update_miso_history():
    # Fill any missing days in the rolling two-month MISO history window.
    history = _load_or_reset_two_month_history(MISO_FILE, "MISO")
    data = history["data"]
    updated = False

    for month_key, start_date, end_date in _month_ranges_to_fill():
        if month_key not in data or not isinstance(data[month_key], dict):
            data[month_key] = {}

        d = start_date
        while d <= end_date:
            key = d.isoformat()
            if key not in data[month_key]:
                val = fetch_miso_daily_average(d)
                if val is not None:
                    data[month_key][key] = round(val, 5)
                    _electric_debug(f"MISO added {key} = {round(val, 5)}")
                    updated = True
                else:
                    _electric_debug(f"MISO missing {key}")
            d += timedelta(days=1)

    if updated:
        history["data"] = data
        _save_json(MISO_FILE, history)
        _electric_debug(
            f"MISO history saved with months {history['prior_month']} and {history['current_month']}"
        )

    return history

# =========================================================
# ERCOT — FAST VERSION
# =========================================================

def fetch_ercot_daily_average(d):
    # ERCOT publishes a doc listing plus downloadable ZIP/CSV files. We select
    # likely candidates, filter to the requested date, then average HB_NORTH.

    try:

        index_url = "https://www.ercot.com/misapp/servlets/IceDocListJsonWS?reportTypeId=12331"
        r = requests.get(index_url, timeout=20)
        payload = r.json()

        doc_groups = payload["ListDocsByRptTypeRes"]["DocumentList"]

        docs = []

        for group in doc_groups:
            doc = group.get("Document")
            if isinstance(doc, list):
                docs.extend(doc)
            elif isinstance(doc, dict):
                docs.append(doc)

        target = d.strftime("%Y%m%d")
        target_iso = d.isoformat()
        target_us = f"{d.month}/{d.day}/{d.year}"

        preferred_docs = []
        fallback_docs = []

        for doc in docs:
            name = str(doc.get("ConstructedName", ""))
            file_name = str(doc.get("FileName", ""))
            combined = f"{name} {file_name}".lower()

            if ".csv" in combined or ".zip" in combined or "csv" in combined:
                fallback_docs.append(doc)
                if target in combined or target_iso in combined or target_us in combined:
                    preferred_docs.append(doc)

        candidate_docs = preferred_docs if preferred_docs else fallback_docs[:20]

        for doc in candidate_docs:
            doc_id = doc.get("DocID")
            if not doc_id:
                continue

            download_url = f"https://www.ercot.com/misdownload/servlets/mirDownload?doclookupId={doc_id}"
            zip_resp = requests.get(download_url, timeout=30)

            with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as z:
                csv_candidates = [f for f in z.namelist() if f.lower().endswith(".csv")]
                if not csv_candidates:
                    continue

                csv_file = csv_candidates[0]

                with z.open(csv_file) as f:
                    df = pd.read_csv(f)

            if "SettlementPoint" not in df.columns or "SettlementPointPrice" not in df.columns:
                continue

            date_col = None
            for candidate in ("DeliveryDate", "OperatingDate", "TradeDate"):
                if candidate in df.columns:
                    date_col = candidate
                    break

            if date_col is not None:
                parsed_dates = pd.to_datetime(df[date_col], errors="coerce")
                df = df[parsed_dates.dt.date == d]

            df = df[df["SettlementPoint"].astype(str).str.strip().str.upper().eq("HB_NORTH")]
            df["SettlementPointPrice"] = pd.to_numeric(df["SettlementPointPrice"], errors="coerce")
            df = df.dropna(subset=["SettlementPointPrice"])

            if df.empty:
                continue

            return float(df["SettlementPointPrice"].mean())

        return None

    except Exception:
        return None


def update_ercot_history():
    # Fill any missing days in the rolling two-month ERCOT history window.

    history = _load_or_reset_two_month_history(ERCOT_FILE, "ERCOT")

    data = history["data"]

    updated = False

    for month_key, start_date, end_date in _month_ranges_to_fill():

        if month_key not in data:
            data[month_key] = {}

        d = start_date

        while d <= end_date:

            key = d.isoformat()

            if key not in data[month_key]:

                val = fetch_ercot_daily_average(d)

                if val is not None:
                    data[month_key][key] = round(val, 5)
                    _electric_debug(f"ERCOT added {key} = {round(val, 5)}")
                    updated = True
                else:
                    _electric_debug(f"ERCOT missing {key}")

            d += timedelta(days=1)

    if updated:
        history["data"] = data
        _save_json(ERCOT_FILE, history)
        _electric_debug(
            f"ERCOT history saved with months {history['prior_month']} and {history['current_month']}"
        )

    return history
# =========================================================
# BUILD ELECTRIC DATA
# =========================================================

def build_electric():
    # Build the exact payload shape expected by script.js. Keep each market
    # present even when a source is unavailable so the UI does not jump around.
    _electric_debug("Starting electric rebuild")
    iso = update_iso_history()
    miso = update_miso_history()
    ercot = update_ercot_history()

    def compute(history, name, hub):
        # Convert raw daily history into the month-to-date average and
        # prior-month comparison displayed in Q1.
        if not isinstance(history, dict):
            return {
                "name": name,
                "iso": name,
                "hub": hub,
                "unit": "$/MWh",
                "price": None,
                "change": None,
                "percent": None,
                "status": "unavailable"
            }

        current_month = history.get("current_month")
        prior_month = history.get("prior_month")
        all_data = history.get("data", {})

        current_data = all_data.get(current_month, {})
        prior_data = all_data.get(prior_month, {})

        current_vals = list(current_data.values())
        prior_vals = list(prior_data.values())

        if not current_vals:
            return {
                "name": name,
                "iso": name,
                "hub": hub,
                "unit": "$/MWh",
                "price": None,
                "change": None,
                "percent": None,
                "status": "unavailable"
            }

        current_avg = sum(current_vals) / len(current_vals)
        prior_avg = (sum(prior_vals) / len(prior_vals)) if prior_vals else None

        change = 0
        percent = 0

        if prior_avg is not None and prior_avg != 0:
            change = current_avg - prior_avg
            percent = (change / prior_avg) * 100

        return {
            "name": name,
            "iso": name,
            "hub": hub,
            "unit": "$/MWh",
            "price": round(current_avg, 2),
            "change": round(change, 2),
            "percent": round(percent, 2),
            "status": "ok"
        }

    markets = [
        compute(iso, "ISO-NE", "Internal Hub"),
        compute(miso, "MISO", "Illinois Hub"),
        compute(ercot, "ERCOT", "HB North")
    ]

    return {
        "as_of": datetime.now().isoformat(),
        "aggregation": "MTD average vs Prior Month average",
        "markets": markets
    }

def electric_background_worker():
    # Refresh electric data in the background so the endpoint can usually return
    # immediately without blocking on three external market fetches.
    while True:
        try:
            ELECTRIC_CACHE["data"] = build_electric()
            ELECTRIC_CACHE["last_update"] = datetime.now()
            print("Electric cache refreshed.")
        except Exception as e:
            print("Electric refresh error:", e)
        time.sleep(600)

@app.on_event("startup")
def start_electric_background():
    Thread(target=electric_background_worker, daemon=True).start()

# =========================================================
# API ENDPOINT (instant)
# =========================================================

@app.get("/electric")
def get_electric():
    # Safety net: if the background worker has not refreshed recently, rebuild
    # on demand instead of serving stale month data forever.
    now = datetime.now()

    if (
        ELECTRIC_CACHE["data"] is None or
        ELECTRIC_CACHE["last_update"] is None or
        (now - ELECTRIC_CACHE["last_update"]).seconds > 3600
    ):
        ELECTRIC_CACHE["data"] = build_electric()
        ELECTRIC_CACHE["last_update"] = now
    return ELECTRIC_CACHE["data"]


# =========================================================
# STOCK DATA
# =========================================================

def fetch_from_yahoo(symbol: str):
    # Try the cleanest Yahoo response first, then fall back through alternate
    # yfinance shapes so Q2 and Q3 can stay populated when one path is sparse.
    ticker = yf.Ticker(symbol)
    info = ticker.info or {}

    price = info.get("regularMarketPrice")
    prev_close = info.get("regularMarketPreviousClose")

    if price is None or prev_close in (None, 0):
        fast_info = getattr(ticker, "fast_info", {}) or {}
        price = price if price is not None else fast_info.get("lastPrice")
        prev_close = prev_close if prev_close not in (None, 0) else fast_info.get("previousClose")

    if price is None or prev_close in (None, 0):
        history = ticker.history(period="5d", interval="1d")
        if history is not None and not history.empty:
            closes = history["Close"].dropna().tolist()
            if closes:
                price = closes[-1]
                if len(closes) >= 2:
                    prev_close = closes[-2]

    if price is None or prev_close in (None, 0):
        raise ValueError(f"Missing quote data for {symbol}")

    change_dollar = float(price) - float(prev_close)
    change = (change_dollar / float(prev_close)) * 100
    return {
        "price": float(price),
        "change": float(change),
        "change_dollar": float(change_dollar),
    }

@app.get("/quote/{symbol}")
def get_quote(symbol: str):
    now = time.time()

    if symbol in cache and now - cache[symbol]["timestamp"] < CACHE_DURATION:
        return cache[symbol]["data"]

    try:
        data = fetch_from_yahoo(symbol)
        cache[symbol] = {"data": data, "timestamp": now}
        return data
    except Exception:
        cached = cache.get(symbol)
        if cached:
            return cached["data"]
        return {"price": 0, "change": 0}

def _format_nws_updated(value):
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(ZoneInfo("America/New_York")).strftime("%b %d %I:%M %p ET")
    except Exception:
        return value

def _temperature_display(period):
    temp = period.get("temperature")
    unit = period.get("temperatureUnit") or "F"
    if temp is None:
        return "--"
    return f"{temp}\N{DEGREE SIGN}{unit}"

def _normalize_period_name(name: str):
    label = str(name or "").strip()
    if not label:
        return ""
    if label.lower().startswith("this "):
        return "Today"
    return label

def _normalize_forecast_period(period):
    return {
        "name": _normalize_period_name(period.get("name", "")),
        "is_daytime": bool(period.get("isDaytime")),
        "temperature": period.get("temperature"),
        "temperature_display": _temperature_display(period),
        "short_forecast": period.get("shortForecast", ""),
        "summary": period.get("shortForecast", ""),
        "detail": period.get("detailedForecast", ""),
        "wind": " ".join(
            part for part in [period.get("windSpeed", ""), period.get("windDirection", "")]
            if part
        ).strip(),
    }

def _fetch_nws_city_forecast(city_name, lat, lon):
    # Two-step NWS lookup: coordinates -> forecast URL -> normalized daily rows.
    points_url = f"https://api.weather.gov/points/{lat},{lon}"

    points_resp = _direct_get(points_url, headers=NWS_HEADERS, timeout=10)
    points_resp.raise_for_status()
    points_data = points_resp.json()
    forecast_url = points_data.get("properties", {}).get("forecast")

    if not forecast_url:
        raise ValueError(f"No forecast URL returned for {city_name}")

    forecast_resp = _direct_get(forecast_url, headers=NWS_HEADERS, timeout=10)
    forecast_resp.raise_for_status()
    forecast_data = forecast_resp.json()

    periods = forecast_data.get("properties", {}).get("periods", [])
    normalized = [_normalize_forecast_period(period) for period in periods]
    daytime_only = [period for period in normalized if period["is_daytime"]][:7]
    if not daytime_only:
        daytime_only = normalized[:7]
    extended_daily = [period for period in normalized if period["is_daytime"]][:8]
    if not extended_daily:
        extended_daily = normalized[:8]

    return {
        "city": city_name,
        "updated": _format_nws_updated(forecast_data.get("properties", {}).get("updated")),
        "current": normalized[0] if normalized else None,
        "days": daytime_only,
        "extended": extended_daily,
    }

def _extract_first_match(text, patterns):
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None

def _extract_img_candidates(html: str):
    candidates = []
    for match in re.finditer(r"<img\b([^>]+)>", html, flags=re.IGNORECASE | re.DOTALL):
        tag = match.group(1)
        src_match = re.search(r'src=["\']([^"\']+)["\']', tag, flags=re.IGNORECASE)
        if not src_match:
            continue

        src = src_match.group(1).strip()
        alt_match = re.search(r'alt=["\']([^"\']*)["\']', tag, flags=re.IGNORECASE)
        title_match = re.search(r'title=["\']([^"\']*)["\']', tag, flags=re.IGNORECASE)
        label = " ".join(
            value for value in [
                alt_match.group(1).strip() if alt_match else "",
                title_match.group(1).strip() if title_match else "",
            ]
            if value
        ).lower()

        candidates.append({"src": src, "label": label})

    return candidates

def _select_noaa_image_url(base_url: str, html: str, source_key: str, fallback_url: str | None):
    candidates = _extract_img_candidates(html)
    filtered = []

    for candidate in candidates:
        src = candidate["src"]
        label = candidate["label"]
        src_lower = src.lower()

        if not any(ext in src_lower for ext in (".png", ".gif", ".jpg", ".jpeg", ".webp")):
            continue
        if any(skip in src_lower for skip in ("logo", "icon", "usa.gov", "weather.gov", "noaa", "nws")):
            continue

        score = 0

        if source_key == "week":
            if any(term in src_lower for term in ("610", "6-10", "6_10", "6to10")):
                score += 4
            if "temp" in src_lower or "temperature" in src_lower:
                score += 5
            if "precip" in src_lower:
                score -= 3
            if "temperature" in label:
                score += 3
        elif source_key == "month":
            if any(term in src_lower for term in ("30day", "30_day", "off", "month")):
                score += 4
            if "temp" in src_lower or "temperature" in src_lower:
                score += 5
            if "precip" in src_lower:
                score -= 3
            if "temperature" in label:
                score += 3

        score += max(0, len(src))
        filtered.append((score, urljoin(base_url, src)))

    if filtered:
        filtered.sort(key=lambda item: item[0], reverse=True)
        return filtered[0][1]

    return fallback_url

def _fetch_noaa_outlook(source):
    # NOAA outlook pages are semi-structured HTML, so pick the most likely image
    # and return only the metadata Q4 needs to render it.
    response = _direct_get(
        source["url"],
        headers={"User-Agent": NWS_HEADERS["User-Agent"]},
        timeout=10
    )
    response.raise_for_status()
    html = response.text

    if source["key"] == "week":
        valid = _extract_first_match(html, [r"Valid:\s*([^<\r\n]+)"])
        issued = _extract_first_match(html, [r"Updated:\s*([^<\r\n]+)"])
        summary = "6-10 day national temperature and precipitation outlook."
    elif source["key"] == "month":
        valid = "30-day national outlook"
        issued = _extract_first_match(html, [r"Issued:\s*([^<\r\n]+)"])
        summary = "Official 30-day NOAA outlook for temperature and precipitation."
    else:
        valid = _extract_first_match(html, [r"0\.5 Month Outlook for\s*([^<\r\n]+)"])
        issued = "Issued monthly near mid-month"
        summary = "Official CPC seasonal outlooks and longer-lead national guidance."

    image_url = _select_noaa_image_url(
        source["url"],
        html,
        source["key"],
        source.get("image_url")
    )

    return {
        "label": source["label"],
        "url": source["url"],
        "image_url": image_url,
        "valid": valid,
        "issued": issued,
        "summary": summary,
    }

@app.get("/weather-dashboard")
def get_weather_dashboard():
    # Bundle city forecasts plus longer-range NOAA outlooks into one payload so
    # Q4 can rotate views without multiple endpoint round trips.
    now = time.time()

    if (
        weather_dashboard_cache["data"]
        and now - weather_dashboard_cache["timestamp"] < WEATHER_CACHE_DURATION
    ):
        return weather_dashboard_cache["data"]

    try:
        boston = _fetch_nws_city_forecast(**WEATHER_LOCATIONS["boston"])
        chicago = _fetch_nws_city_forecast(**WEATHER_LOCATIONS["chicago"])
        hartford = _fetch_nws_city_forecast(**WEATHER_LOCATIONS["hartford"])
        outlooks = [_fetch_noaa_outlook(source) for source in NOAA_OUTLOOK_SOURCES]

        data = {
            "regional": {
                "cities": [boston, chicago],
            },
            "hartford": hartford,
            "outlooks": outlooks,
        }

        weather_dashboard_cache["data"] = data
        weather_dashboard_cache["timestamp"] = now
        return data

    except Exception as e:
        return {
            "regional": {"cities": []},
            "hartford": {"current": None, "extended": []},
            "outlooks": [],
            "error": str(e),
        }

# =========================================================
# NEWS SYSTEM
# =========================================================

CNBC_FEEDS = [
    "https://www.cnbc.com/id/15839135/device/rss/rss.html",
    "https://www.cnbc.com/id/20910258/device/rss/rss.html",
    "https://www.cnbc.com/id/19854910/device/rss/rss.html",
    "https://www.cnbc.com/id/10000113/device/rss/rss.html",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
]

NY_TZ = ZoneInfo("America/New_York")
MAX_AGE_HOURS = 6
MIN_SCORE = 3
SIMILARITY_THRESHOLD = 0.1

STRONG_KEYWORDS = {
    "fed": 5, "federal reserve": 5, "interest rate": 5,
    "inflation": 4, "cpi": 4, "pce": 4, "gdp": 4,
    "jobs": 4, "unemployment": 4, "treasury": 4,
    "bond": 4, "yield": 4, "oil": 4,
    "tariff": 5, "supreme court": 5, "scotus": 5,
    "sanctions": 4, "bidding war": 5, "investing": 5, "taxes": 5,
    "acquire": 5,
    "acquisition": 5,
    "merger": 5,
    "buyout": 5,
    "takeover": 5,
    "bid": 4,
    "deal": 4
}

MARKET_TERMS = {
    "stock": 3, "stocks": 3, "futures": 3,
    "market": 3, "markets": 3,
    "dow": 3, "nasdaq": 3, "s&p": 3,
    "wall street": 3, "rally": 3, "selloff": 3,
    "earnings": 3, "revenue": 2, "guidance": 2,
    "china": 2,
}

LOW_SIGNAL_TERMS = ["lifestyle", "how to", "best places", "travel", "top 10", "watchlist"]

STOPWORDS = {
    "the","a","an","and","or","but","to","of","in","on",
    "with","at","by","from","as","is","are","was","were",
    "be","been","being","this","that","these","those",
}

WORD_RE = re.compile(r"[a-z0-9']+")

def headline_score(title: str) -> int:
    # Lightweight keyword scoring tuned for market-moving business headlines.
    lower = title.lower()
    score = 0
    for word, weight in STRONG_KEYWORDS.items():
        if word in lower:
            score += weight
    for word, weight in MARKET_TERMS.items():
        if word in lower:
            score += weight
    for bad in LOW_SIGNAL_TERMS:
        if bad in lower:
            score -= 4
    return score

def tokenize(title: str):
    words = WORD_RE.findall(title.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}

def jaccard_overlap(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a | b), 1)

@app.get("/news")
def get_news():
    # Pull recent CNBC RSS items, score them, dedupe near-duplicates, and keep
    # the strongest few for Q4's headline rotation.
    now = time.time()

    if news_cache["data"] and now - news_cache["timestamp"] < CACHE_DURATION:
        return news_cache["data"]

    try:
        all_items = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
        today = datetime.now(NY_TZ)
        date_path = f"/{today.year}/{today.month:02d}/{today.day:02d}/"

        for feed_url in CNBC_FEEDS:
            response = requests.get(feed_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            response.raise_for_status()
            root = ET.fromstring(response.content)

            for item in root.findall(".//item"):
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                pub = item.findtext("pubDate", "").strip()

                if not title or not link or not pub:
                    continue
                if date_path not in link:
                    continue

                try:
                    dt = parsedate_to_datetime(pub)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                except:
                    continue

                if dt < cutoff:
                    continue

                score = headline_score(title)
                if score >= MIN_SCORE:
                    all_items.append({"title": title, "url": link, "dt": dt, "score": score})

        unique = {item["url"]: item for item in all_items}
        items = list(unique.values())
        items.sort(key=lambda x: (x["score"], x["dt"]), reverse=True)

        chosen = []
        for item in items:
            if len(chosen) >= 3:
                break
            if any(jaccard_overlap(tokenize(item["title"]), tokenize(c["title"])) >= SIMILARITY_THRESHOLD for c in chosen):
                continue
            chosen.append(item)

        chosen.sort(key=lambda x: x["dt"], reverse=True)

        headlines = []
        for item in chosen:
            et_dt = item["dt"].astimezone(NY_TZ)
            headlines.append({
                "title": item["title"],
                "url": item["url"],
                "time": et_dt.strftime("%I:%M %p").lstrip("0")
            })

        data = {"source": "CNBC (6H Macro Weighted)", "headlines": headlines}
        news_cache["data"] = data
        news_cache["timestamp"] = now
        return data

    except Exception as e:
        return {"source": "CNBC", "headlines": [], "error": str(e)}

# =========================================================
# EVENT WATCH
# =========================================================

PIZZINT_DASHBOARD_API = "https://www.pizzint.watch/api/dashboard-data"
PIZZINT_DOOMSDAY_API = "https://www.pizzint.watch/api/neh-index/doomsday"

@app.get("/event-watch")
def get_event_watch():
    # Event Watch is a custom panel whose logic lives here because it mixes feed
    # data, date handling, and domain-specific ranking rules.
    now = time.time()

    if event_watch_cache["data"] and now - event_watch_cache["timestamp"] < EVENT_CACHE_DURATION:
        return event_watch_cache["data"]

    try:
        headers = {"User-Agent": "Mozilla/5.0"}

        dash_url = f"{PIZZINT_DASHBOARD_API}?_t={int(time.time() * 1000)}"

        dash_resp = requests.get(
            dash_url,
            headers=headers,
            timeout=10
        )
        dash_resp.raise_for_status()
        dash_payload = dash_resp.json()
        doughcon_level = dash_payload.get("defcon_level")

        places_data = dash_payload.get("data", [])
        events = dash_payload.get("events", [])

        # Build distance map from stable coordinates
        distance_map = {}
        for place in places_data:
            pid = place.get("place_id")
            if pid in PIZZA_COORDS:
                lat, lon = PIZZA_COORDS[pid]
                dist = haversine_miles(lat, lon, PENTAGON_LAT, PENTAGON_LON)
                distance_map[pid] = round(dist, 2)

        sorted_spikes = sorted(
            events,
            key=lambda x: x.get("percentage_of_usual", 0),
            reverse=True
        )

        top_spikes = [
            {
                "place": s.get("place_name"),
                "percentage": s.get("percentage_of_usual"),
                "minutes_ago": s.get("minutes_ago"),
                "magnitude": s.get("spike_magnitude"),
                "distance": distance_map.get(s.get("place_id"))
            }
            for s in sorted_spikes[:2]
        ]

        doom_url = f"{PIZZINT_DOOMSDAY_API}?_t={int(time.time() * 1000)}"

        doom_resp = requests.get(
            doom_url,
            headers=headers,
            timeout=10
        )
        doom_resp.raise_for_status()
        doom_payload = doom_resp.json()

        # Your sample shows {"markets":[...]}
        markets = doom_payload.get("data") or doom_payload.get("markets") or doom_payload

        sorted_markets = sorted(markets, key=lambda x: x.get("price", 0), reverse=True)

        top_three = []
        for m in sorted_markets[:3]:
            slug = m.get("slug") or m.get("market_slug")
            label = m.get("label") or m.get("name") or m.get("title")

            # Prefer label (human readable), fallback to slug
            title = label or slug or "Unknown Event"
            title_source = "label" if label else ("slug" if slug else "fallback")

            top_three.append({
                "slug": slug,
                "label": label,
                "title": title,
                "title_source": title_source,
                "region": m.get("region"),
                "price": m.get("price"),
                "image": m.get("image"),
                # keep extra fields available if you ever want them later
                "tokenId": m.get("tokenId"),
                "eventId": m.get("eventId"),
                "endDate": m.get("endDate"),
                "volume": m.get("volume"),
                "volume_24h": m.get("volume_24h"),
            })

        data = {
            "source": "pizzint.watch",
            "doughcon": doughcon_level,
            "spike": top_spikes,
            "top_markets": top_three,
        }
        event_watch_cache["data"] = data
        event_watch_cache["timestamp"] = now
        return data

    except Exception as e:
        return {"error": str(e), "source": "pizzint.watch"}

# =========================================================
# OIL / GAS BOARD
# =========================================================

EIA_GAS_DIESEL_URL = "https://www.eia.gov/petroleum/gasdiesel/"

def _extract_eia_text_lines(raw_html: str):
    # The EIA page is not a clean API, so reduce the HTML to text fragments that
    # are easier to pattern-match for weekly U.S. averages.
    cleaned = re.sub(r"(?is)<script.*?</script>", " ", raw_html)
    cleaned = re.sub(r"(?is)<style.*?</style>", " ", cleaned)
    cleaned = re.sub(r"(?s)<[^>]+>", "\n", cleaned)
    cleaned = cleaned.replace("\xa0", " ")

    lines = []
    for line in cleaned.splitlines():
        normalized = re.sub(r"\s+", " ", line).strip()
        if normalized:
            lines.append(normalized)
    return lines

def _extract_us_average_from_lines(lines, heading_text: str):
    text = "\n".join(lines)

    pattern = re.compile(
        rf"{re.escape(heading_text)}.*?"
        rf"((?:\d{{2}}/\d{{2}}/\d{{2}}\s+){{2,}}\d{{2}}/\d{{2}}/\d{{2}}).*?"
        rf"U\.S\.\s+((?:-?\d+\.\d+\s+){{2,}}-?\d+\.\d+)",
        re.DOTALL
    )

    match = pattern.search(text)
    if not match:
        return None

    dates = re.findall(r"\b\d{2}/\d{2}/\d{2}\b", match.group(1))
    values = re.findall(r"-?\d+\.\d+", match.group(2))

    if len(dates) < 2 or len(values) < 2:
        return None

    latest_value = float(values[len(dates) - 1])
    prior_value = float(values[len(dates) - 2])
    delta_value = latest_value - prior_value
    delta_pct = 0.0 if prior_value == 0 else (delta_value / prior_value) * 100

    return {
        "date": dates[-1],
        "value": round(latest_value, 3),
        "prior_value": round(prior_value, 3),
        "delta_value": round(delta_value, 3),
        "delta_pct": round(delta_pct, 2)
    }

def fetch_retail_fuel_averages():
    # Pull both gasoline and diesel from the same weekly EIA page so Q3 can
    # render a single consistent "retail fuels" card.
    response = requests.get(
        EIA_GAS_DIESEL_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15
    )
    response.raise_for_status()

    lines = _extract_eia_text_lines(response.text)
    gasoline = _extract_us_average_from_lines(lines, "U.S. Regular Gasoline Prices")
    diesel = _extract_us_average_from_lines(lines, "U.S. On-Highway Diesel Fuel Prices")

    if gasoline is None or diesel is None:
        raise ValueError("Unable to parse EIA U.S. fuel averages")

    return {"gasoline": gasoline, "diesel": diesel}

def fetch_market_quote(symbol: str):
    # Shared futures/commodity quote loader for Q3's WTI and Brent cards.
    ticker = yf.Ticker(symbol)
    info = ticker.info or {}

    price = info.get("regularMarketPrice")
    prev_close = info.get("regularMarketPreviousClose")
    change = info.get("regularMarketChange")
    change_pct = info.get("regularMarketChangePercent")

    if price is None:
        raise ValueError(f"Missing price for {symbol}")

    if change is None and prev_close not in (None, 0):
        change = float(price) - float(prev_close)

    if change_pct is None and change is not None and prev_close not in (None, 0):
        change_pct = (float(change) / float(prev_close)) * 100

    contract_source = " ".join(
        str(info.get(key, "")).strip()
        for key in ("shortName", "longName", "symbol", "displayName")
        if info.get(key)
    )
    contract_month = None
    month_match = re.search(
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4}\b",
        contract_source,
        re.IGNORECASE
    )
    if month_match:
        raw_month = month_match.group(0)
        parsed_month = datetime.strptime(raw_month[:3], "%b")
        year_match = re.search(r"(\d{2,4})$", raw_month)
        if year_match:
            raw_year = year_match.group(1)
            year = int(raw_year)
            if len(raw_year) == 2:
                year += 2000
            contract_month = f"{parsed_month.strftime('%b')} {str(year)[-2:]}"

    if contract_month is None:
        quote_type = str(info.get("quoteType", "")).lower()
        expire_epoch = info.get("expireDate") or info.get("expirationDate")
        if quote_type == "future" and expire_epoch:
            try:
                expiry_dt = datetime.fromtimestamp(int(expire_epoch), tz=timezone.utc)
                contract_month = expiry_dt.strftime("%b %y")
            except Exception:
                pass

    return {
        "price": float(price),
        "change": float(change) if change is not None else 0.0,
        "change_pct": float(change_pct) if change_pct is not None else 0.0,
        "contract_month": contract_month
    }

@app.get("/oil-gas-board")
def get_oil_gas_board():
    # Combine retail fuel averages with live futures so Q3 can refresh from one
    # compact payload instead of coordinating several frontend calls.
    now = time.time()

    if oil_gas_cache["data"] and now - oil_gas_cache["timestamp"] < OIL_GAS_CACHE_DURATION:
        return oil_gas_cache["data"]

    try:
        retail = fetch_retail_fuel_averages()
        wti = fetch_market_quote("CL=F")
        brent = fetch_market_quote("BZ=F")
        spread_value = wti["price"] - brent["price"]
        spread_change = wti["change"] - brent["change"]
        front_month_note = (
            f"Day over day | Month Ahead: {wti['contract_month']}"
            if wti.get("contract_month")
            else "Day over day | Month Ahead"
        )

        data = {
            "left_column": [
                {
                    "label": "Avg Gas Price",
                    "meta": f"U.S. average retail gasoline | EIA week of {retail['gasoline']['date']}",
                    "value": f"${retail['gasoline']['value']:.3f}",
                    "change": retail["gasoline"]["delta_value"],
                    "changeText": f"${retail['gasoline']['delta_value']:+.3f} ({retail['gasoline']['delta_pct']:+.2f}%)"
                },
                {
                    "label": "Avg Diesel Price",
                    "meta": f"U.S. average on-highway diesel | EIA week of {retail['diesel']['date']}",
                    "value": f"${retail['diesel']['value']:.3f}",
                    "change": retail["diesel"]["delta_value"],
                    "changeText": f"${retail['diesel']['delta_value']:+.3f} ({retail['diesel']['delta_pct']:+.2f}%)"
                }
            ],
            "right_column": [
                {
                    "label": "Crude Oil",
                    "meta": "WTI benchmark",
                    "value": f"${wti['price']:.2f}",
                    "change": wti["change"],
                    "changeText": f"${wti['change']:+.2f} ({wti['change_pct']:+.2f}%)"
                },
                {
                    "label": "Brent Oil",
                    "meta": "International benchmark",
                    "value": f"${brent['price']:.2f}",
                    "change": brent["change"],
                    "changeText": f"${brent['change']:+.2f} ({brent['change_pct']:+.2f}%)"
                },
                {
                    "label": "WTI - Brent Spread",
                    "meta": "Current differential",
                    "value": f"${spread_value:+.2f}",
                    "change": spread_change,
                    "changeText": f"${spread_change:+.2f}"
                }
            ],
            "right_card_note": front_month_note,
        }

        oil_gas_cache["data"] = data
        oil_gas_cache["timestamp"] = now
        return data

    except Exception as e:
        return {"error": str(e)}
