from fastapi import FastAPI
from fastapi.responses import FileResponse
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


app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent

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
    return FileResponse(BASE_DIR / "index.html")

# =========================================================
# CACHE
# =========================================================

cache = {}
news_cache = {"data": None, "timestamp": 0}
event_watch_cache = {"data": None, "timestamp": 0}

CACHE_DURATION = 60
EVENT_CACHE_DURATION = 60

# =========================================================
# GEO CONFIG (Pentagon Distance System)
# =========================================================

PENTAGON_LAT = 38.8719
PENTAGON_LON = -77.0563

def haversine_miles(lat1, lon1, lat2, lon2):
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

# Hardcoded stable coordinates (from Google maps once)
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

ELECTRIC_CACHE = {"data": None}

ISO_FILE = "isone_history.json"
MISO_FILE = "miso_history.json"
ERCOT_FILE = "ercot_history.json"

# ---------------------------------------------------------
# GENERIC LOAD / SAVE
# ---------------------------------------------------------

def _load_json(file):
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
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# ---------------------------------------------------------
# MONTH HELPERS
# File format:
# {
#   "name": "ISONE",
#   "current_month": "2026-03",
#   "prior_month": "2026-02",
#   "data": {
#       "2026-02": {
#           "2026-02-01": 31.22
#       },
#       "2026-03": {
#           "2026-03-01": 44.18
#       }
#   }
# }
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
        _save_json(file, new_history)

    return new_history

def _month_ranges_to_fill():
    today = date.today()
    current_start = _current_month_start()
    prior_start = _prior_month_start()
    prior_end = current_start - timedelta(days=1)

    return [
        (_month_str(prior_start), prior_start, prior_end),
        (_month_str(current_start), current_start, today),
    ]

# ---------------------------------------------------------
# GENERIC CSV / COLUMN HELPERS
# ---------------------------------------------------------

def _clean_col_name(name):
    return re.sub(r"[^a-z0-9]+", "", str(name).strip().lower())

def _find_actual_column(df, aliases):
    alias_set = {_clean_col_name(a) for a in aliases}
    for col in df.columns:
        if _clean_col_name(col) in alias_set:
            return col
    return None

def _find_header_row_by_aliases(text, alias_groups, max_scan_rows=80):
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
                    print(f"ISONE adding day to json: {key}")
                    updated = True
            d += timedelta(days=1)

    if updated:
        history["data"] = data
        _save_json(ISO_FILE, history)

    return history

# =========================================================
# MISO — ILLINOIS HUB
# =========================================================

def fetch_miso_daily_average(d):
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

        df = df[
            df[node_col].astype(str).str.strip().str.upper().eq("ILLINOIS.HUB") &
            df[type_col].astype(str).str.strip().str.upper().eq("HUB") &
            df[value_col].astype(str).str.strip().str.upper().eq("LMP")
        ]

        if df.empty:
            return None

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
                    print(f"MISO adding day to json: {key}")
                    updated = True
            d += timedelta(days=1)

    if updated:
        history["data"] = data
        _save_json(MISO_FILE, history)

    return history

# =========================================================
# ERCOT — FAST VERSION
# =========================================================

def fetch_ercot_daily_average(d):

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

        # find document for THIS DAY
        target = d.strftime("%Y%m%d")

        for doc in docs:

            name = str(doc.get("ConstructedName", ""))

            if target not in name:
                continue

            if "csv" not in name.lower():
                continue

            doc_id = doc["DocID"]

            download_url = f"https://www.ercot.com/misdownload/servlets/mirDownload?doclookupId={doc_id}"

            zip_resp = requests.get(download_url, timeout=30)

            with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as z:

                csv_file = [f for f in z.namelist() if f.endswith(".csv")][0]

                with z.open(csv_file) as f:
                    df = pd.read_csv(f)

            df = df[df["SettlementPoint"] == "HB_NORTH"]

            df["SettlementPointPrice"] = pd.to_numeric(
                df["SettlementPointPrice"], errors="coerce"
            )

            df = df.dropna(subset=["SettlementPointPrice"])

            if df.empty:
                return None

            return float(df["SettlementPointPrice"].mean())

        return None

    except Exception:
        return None


def update_ercot_history():

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
                    print(f"ERCOT adding day to json: {key}")
                    updated = True

            d += timedelta(days=1)

    if updated:
        history["data"] = data
        _save_json(ERCOT_FILE, history)

    return history
# =========================================================
# BUILD ELECTRIC DATA
# =========================================================

def build_electric():
    iso = update_iso_history()
    miso = update_miso_history()
    ercot = update_ercot_history()

    def compute(history, name):
        if not isinstance(history, dict):
            return None

        current_month = history.get("current_month")
        prior_month = history.get("prior_month")
        all_data = history.get("data", {})

        current_data = all_data.get(current_month, {})
        prior_data = all_data.get(prior_month, {})

        current_vals = list(current_data.values())
        prior_vals = list(prior_data.values())

        if not current_vals:
            return None

        current_avg = sum(current_vals) / len(current_vals)
        prior_avg = (sum(prior_vals) / len(prior_vals)) if prior_vals else None

        change = 0
        percent = 0

        if prior_avg is not None and prior_avg != 0:
            change = current_avg - prior_avg
            percent = (change / prior_avg) * 100

        return {
            "name": name,
            "unit": "$/MWh",
            "price": round(current_avg, 2),
            "change": round(change, 2),
            "percent": round(percent, 2),
            "status": "ok"
        }

    markets = []

    for result in [
        compute(iso, "ISO-NE"),
        compute(miso, "MISO"),
        compute(ercot, "ERCOT")
    ]:
        if result:
            markets.append(result)

    return {
        "as_of": datetime.now().isoformat(),
        "aggregation": "MTD average vs Prior Month average",
        "markets": markets
    }

# =========================================================
# BACKGROUND REFRESH (every 10 min)
# =========================================================

def electric_background_worker():
    while True:
        try:
            ELECTRIC_CACHE["data"] = build_electric()
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
ELECTRIC_CACHE = {
    "data": None,
    "last_update": None
}

@app.get("/electric")
def get_electric():

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
# BACKGROUND REFRESH (every 10 min)
# =========================================================

def electric_background_worker():
    while True:
        try:
            ELECTRIC_CACHE["data"] = build_electric()
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
    if ELECTRIC_CACHE["data"] is None:
        ELECTRIC_CACHE["data"] = build_electric()
    return ELECTRIC_CACHE["data"]


# =========================================================
# STOCK DATA
# =========================================================

def fetch_from_yahoo(symbol: str):
    ticker = yf.Ticker(symbol)
    info = ticker.info

    price = info.get("regularMarketPrice")
    prev_close = info.get("regularMarketPreviousClose")

    if price is None or prev_close is None or prev_close == 0:
        return {"price": 0, "change": 0}

    change = ((price - prev_close) / prev_close) * 100
    return {"price": float(price), "change": float(change)}

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
        return {"price": 0, "change": 0}

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

LOW_SIGNAL_TERMS = ["lifestyle", "how to", "best places", "travel", "top 10"]

STOPWORDS = {
    "the","a","an","and","or","but","to","of","in","on",
    "with","at","by","from","as","is","are","was","were",
    "be","been","being","this","that","these","those",
}

WORD_RE = re.compile(r"[a-z0-9']+")

def headline_score(title: str) -> int:
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
