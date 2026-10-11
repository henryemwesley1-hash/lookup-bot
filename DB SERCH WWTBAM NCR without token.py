#!/usr/bin/env python3
"""
Database Lookup — Discord bot (v9.9)
- Added NCR Blacklists + NCR Punishments
- Fixed CSP DMV / Callsign Roster subject column
- Added FIVEO/CGSN punishment + employment logs
- Google Date(y,m,d) parsing
- Whitespace / CR / LF cleanup on every cell and subject
"""

from __future__ import annotations
import os, re, io, json, time, asyncio, hashlib, logging
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
from difflib import get_close_matches

import aiohttp
import discord
from discord import app_commands
from PIL import Image, ImageDraw, ImageFont

# ============================================================
# LOGGING / CONFIG
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("lookup")

DISCORD_TOKEN = ("token here please")
CACHE_DIR     = Path.home() / ".cache" / "concord_lookup"
CACHE_TTL_SEC = 600
PNG_SCALE     = 2
APP_VERSION   = "9.9 made by pizza :) heyy x "
CLOSE_MATCH_CUTOFF = 0.7

# ============================================================
# SOURCES
# ============================================================
SOURCES = [
    # --- CAR ---
    {"name": "CAR — Punishment History",        "id": "1Cl5ClG77tW49_Ke761z9hI_vbcd1FJ997ejsyrM7XmQ", "gid": "911622686", "cat": "Punishments"},
    {"name": "CAR — Employment Log",            "id": "1Cl5ClG77tW49_Ke761z9hI_vbcd1FJ997ejsyrM7XmQ", "gid": "525585398", "cat": "Employment"},

    # --- Dept of State ---
    {"name": "Dept of State — Trespass List",   "id": "1AqVqsugyfwmSPo5X5jleo9PQqneJIws0tbj5QqXK6Ps", "gid": "738109874", "cat": "Trespass"},
    {"name": "Dept of State — BAR Attorneys",   "id": "1AqVqsugyfwmSPo5X5jleo9PQqneJIws0tbj5QqXK6Ps", "gid": "657949308", "cat": "Attorneys"},
    {"name": "Judicial Services — Warrants",    "id": "1AqVqsugyfwmSPo5X5jleo9PQqneJIws0tbj5QqXK6Ps", "gid": "840132597", "cat": "Warrants"},

    # --- Agency Registry ---
    {"name": "Agency Registry — User Blacklist","id": "16x3Ux484dUBYuNlG5rV059NLkJPZoXKvWe2Qt23d3nU", "gid": "246218428", "cat": "Blacklist"},
    {"name": "Agency Registry — Cert Chart",    "id": "16x3Ux484dUBYuNlG5rV059NLkJPZoXKvWe2Qt23d3nU", "gid": "0",         "cat": "Certifications"},
    {"name": "Agency Registry — Cert Actions",  "id": "16x3Ux484dUBYuNlG5rV059NLkJPZoXKvWe2Qt23d3nU", "gid": "1329957974","cat": "CertActions"},
    {"name": "Agency Registry — Employment Log","id": "16x3Ux484dUBYuNlG5rV059NLkJPZoXKvWe2Qt23d3nU", "gid": "291083282", "cat": "Employment"},

    # --- TES ---
    {"name": "TES — Employee List",             "id": "1fygzPzMZckwboxTkKgyCW-C4v6HhDZ-yimk1xHsMO4w", "gid": "667178005", "cat": "Employment"},
    {"name": "TES — Punishment Log",            "id": "1fygzPzMZckwboxTkKgyCW-C4v6HhDZ-yimk1xHsMO4w", "gid": "679916708", "cat": "Punishments"},
    {"name": "TES — Blacklist Log",             "id": "1fygzPzMZckwboxTkKgyCW-C4v6HhDZ-yimk1xHsMO4w", "gid": "1199486306","cat": "Blacklist"},
    {"name": "TES — Award Log",                 "id": "1fygzPzMZckwboxTkKgyCW-C4v6HhDZ-yimk1xHsMO4w", "gid": "1543576859","cat": "Awards"},

    # --- CANG ---
    {"name": "CANG — Trespass Logs",            "id": "16-BJfO8tfkMeAQLJuMy5Q0tVA5Q7J04LSo9iv_B25N4", "gid": "1540748361","cat": "Trespass"},
    {"name": "CANG — Employee Roster",          "id": "16-BJfO8tfkMeAQLJuMy5Q0tVA5Q7J04LSo9iv_B25N4", "gid": "1812917107","cat": "Employment"},

    # --- Concord Police Callsign Roster (subject override) ---
    {"name": "Concord Police — Callsign Roster","id": "1XkMkAjkqXBBb1dUHAqqXg9wm8L8iadwf1POhtwJke-Y", "gid": "0",         "cat": "Employment", "subj_override": 1},

    # --- FIVEO / CGSN ---
    {"name": "FIVEO/CGSN — Punishment Log",     "id": "1Ra46yCwDbH93Lypd4x1QXlKTZS6BPyel793aXOJVB44", "gid": "276311503", "cat": "Punishments"},
    {"name": "FIVEO/CGSN — Employment Log",     "id": "1Ra46yCwDbH93Lypd4x1QXlKTZS6BPyel793aXOJVB44", "gid": "239792544", "cat": "Employment"},

    # --- NCR ---
    {"name": "NCR — Blacklists",                "id": "1-DHCrrQ7iOYc_G8YXpDDztJzBF8AKvRR6IArR0Gxj_Y", "gid": "886401841", "cat": "Blacklist",   "subj_override": 1},
    {"name": "NCR — Punishments",               "id": "1-DHCrrQ7iOYc_G8YXpDDztJzBF8AKvRR6IArR0Gxj_Y", "gid": "1643677907","cat": "Punishments", "subj_override": 1},
]

CERT_COLUMNS = ["POST", "Instructor", "Heli Pilot", "Scene Cmd", "Plane Pilot"]

def _norm(s: str) -> str:
    return re.sub(r"[\s_\-]+", "", s.strip().lower())

CERT_NORM = {_norm(c): c for c in CERT_COLUMNS}

# ============================================================
# VISUAL LAYER
# ============================================================
TITLE_ICONS = {
    "Overview":       "🔎",
    "Certifications": "🎖️",
    "Attorneys":      "⚖️",
    "Current Roles":  "💼",
    "Cert Actions":   "📛",
    "Punishments":    "🔨",
    "Blacklist":      "🚫",
    "Warrants":       "📜",
    "Trespass":       "🚷",
    "Awards":         "🏆",
    "Former Roles":   "📁",
}

def _status_glyph(status: str) -> str:
    s = (status or "").lower()
    if not s:                                                       return "⚪"
    if any(k in s for k in ("suspend", "probation", "loa", "leave")): return "🟡"
    if any(k in s for k in ("retired", "terminated", "resigned",
                            "removed", "former")):                  return "⚫"
    if any(k in s for k in ("active", "current", "hired")):         return "🟢"
    if any(k in s for k in ("expired", "cleared", "lifted")):       return "✅"
    return "🔵"

_PNG_STATUS_DOT = {
    "🟢": "ACTIVE", "🟡": "PEND", "⚫": "FORMER",
    "✅": "OK", "🔵": "INFO", "⚪": "",
}

def _status_ascii(status: str) -> str:
    g = _status_glyph(status)
    return _PNG_STATUS_DOT.get(g, "")

_NONBMP = re.compile(r"[\U00010000-\U0010FFFF]")
def _strip_nonbmp(s: str) -> str:
    return _NONBMP.sub("", s)

# ============================================================
# AGENCY / ISSUER HELPERS
# ============================================================
AGENCY_HINTS = ("car", "tes", "cco", "cang", "cnjtf", "csfm", "cfws",
                "concord police", "bar", "dept of state", "department of state",
                "fiveo", "cgsn", "ncr", "northern concord rebels")

GENERIC_ISSUERS = {
    "internal affairs", "internal affairs division",
    "directors office", "director's office", "the directors office",
    "director", "directors",
    "command", "high command", "command staff",
    "administration", "car administration",
    "ia",
    "head of state",
}

def _source_agency(rec: dict) -> str:
    src = (rec.get("source") or "").strip()
    for sep in (" — ", " – ", " - ", " | ", ": "):
        if sep in src:
            return src.split(sep, 1)[0].strip()
    return src

def _contains_agency(low: str) -> bool:
    for a in AGENCY_HINTS:
        if a in low.split() or f"{a} " in low or low.startswith(a + " ") or low == a:
            return True
    return False

def _attribute_issuer(issuer: str, rec: dict) -> str:
    issuer = (issuer or "").strip()
    if not issuer:
        return ""
    agency = _source_agency(rec)
    if not agency:
        return issuer
    low = issuer.lower()
    if agency.lower() in low or _contains_agency(low):
        return issuer
    if low in GENERIC_ISSUERS:
        return f"{agency} {issuer}"
    if looks_like_username(issuer):
        return issuer
    return f"{agency} {issuer}"

# ============================================================
# DATE HELPERS
# ============================================================
def NOW_NAIVE() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

def NOW_AWARE() -> datetime:
    return datetime.now(timezone.utc)

DATE_ANY_RE = re.compile(
    r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})|(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})"
)
DATE_GVIZ_RE = re.compile(r"Date\((\d{4}),\s*(\d{1,2}),\s*(\d{1,2})")

def parse_date(s: str):
    if not s:
        return None
    # Google Date(y,m,d) — month is 0-indexed
    m = DATE_GVIZ_RE.search(s)
    if m:
        try:
            return _bound(datetime(int(m.group(1)), int(m.group(2)) + 1, int(m.group(3))))
        except Exception:
            pass

    m = DATE_ANY_RE.search(s)
    if not m:
        return None
    try:
        if m.group(1):
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            a, b, y = int(m.group(4)), int(m.group(5)), int(m.group(6))
            if y < 100:
                y += 2000
            try:
                return _bound(datetime(y, a, b))
            except ValueError:
                y, mo, d = y, b, a
        return _bound(datetime(y, mo, d))
    except Exception:
        return None

def _bound(dt: datetime):
    if dt.year < 2000 or dt.year > NOW_NAIVE().year + 5:
        return None
    return dt

EXPIRY_HINTS = ("expiration", "expiry", "expires", "end date", "trespass end",
                "date end", "date lifted", "date removed")

def is_expired(rec: dict) -> bool:
    cached = rec.get("_expired_cache")
    if cached is not None:
        return cached
    now = NOW_NAIVE()
    subj_col = rec.get("subj_col")
    result = False
    for i, h in enumerate(rec["headers"]):
        if i == subj_col:
            continue
        if any(k in str(h).lower() for k in EXPIRY_HINTS):
            v = rec["row"][i] if i < len(rec["row"]) else ""
            dt = parse_date(v) if v else None
            if dt and dt < now:
                result = True
                break
    rec["_expired_cache"] = result
    return result

# ============================================================
# FIELD LOOKUP
# ============================================================
def field(rec: dict, *names: str, exclude=None) -> str:
    exclude_set = set(exclude or ())
    subj_col = rec.get("subj_col")
    if subj_col is not None:
        exclude_set.add(subj_col)
    subj_norm = _norm(rec.get("subject") or "")

    def val(i):
        return rec["row"][i] if i < len(rec["row"]) else ""

    for n in names:
        n_low = n.lower().strip()
        for i, h in enumerate(rec["headers"]):
            if i in exclude_set:
                continue
            if str(h).strip().lower() == n_low:
                v = val(i)
                if not v:
                    continue
                if _norm(v) == subj_norm:
                    continue
                return v

    for n in names:
        n_low = n.lower()
        for i, h in enumerate(rec["headers"]):
            if i in exclude_set:
                continue
            if n_low in str(h).lower():
                v = val(i)
                if not v:
                    continue
                if _norm(v) == subj_norm:
                    continue
                return v
    return ""

def sheet_link(rec: dict, label: str = "source") -> str:
    return (f"[{label}](https://docs.google.com/spreadsheets/d/"
            f"{rec['sheet_id']}/edit#gid={rec['gid']})")

# ============================================================
# USERNAME DETECTION
# ============================================================
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,32}$")
DATE_RE     = re.compile(r"^\d{1,4}[/\-.]\d{1,2}[/\-.]\d{1,4}")

def looks_like_username(v: str) -> bool:
    if not v or not (3 <= len(v) <= 32):
        return False
    if " " in v or not USERNAME_RE.match(v):
        return False
    if DATE_RE.match(v):
        return False
    if re.fullmatch(r"\d+(\.\d+)?", v):
        return False
    if not re.search(r"[A-Za-z]", v):
        return False
    if re.fullmatch(r"(username|date|status|agency|type|duration|property|"
                    r"reason|notes?|administrator|rank|title|certification|"
                    r"punishment|award|issued by|verdict|current status)",
                    v, re.I):
        return False
    return True

# ============================================================
# BLACKLIST ACTIVE DETECTION
# ============================================================
RESOLVED_BL_STATUS = (
    "removed", "lifted", "repealed", "overturned", "expired",
    "resolved", "nullified", "rescinded", "cleared", "reversed",
)
RESOLVED_BL_APPEAL = ("granted", "successful", "reversed", "overturned")

def _is_active_blacklist(r: dict) -> bool:
    status = (field(r, "Status") or "").strip().lower()
    appeal = (field(r, "Appeal Status") or "").strip().lower()
    for kw in RESOLVED_BL_STATUS:
        if kw in status:
            return False
    for kw in RESOLVED_BL_APPEAL:
        if kw in appeal:
            return False
    now = NOW_NAIVE()
    subj_col = r.get("subj_col")
    for i, h in enumerate(r["headers"]):
        if i == subj_col:
            continue
        hl = str(h).lower()
        if any(k in hl for k in ("expiration", "expires", "date end",
                                 "date lifted", "date removed", "end date")):
            v = r["row"][i] if i < len(r["row"]) else ""
            dt = parse_date(v) if v else None
            if dt and dt < now:
                return False
    return True

# ============================================================
# HTTP + DISK CACHE
# ============================================================
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _cache_path(sheet_id, gid):
    return CACHE_DIR / f"{hashlib.sha1(f'{sheet_id}:{gid}'.encode()).hexdigest()}.json"

async def fetch_gviz(session, sheet_id, gid):
    path = _cache_path(sheet_id, gid)
    now = time.time()
    if path.exists() and now - path.stat().st_mtime < CACHE_TTL_SEC:
        try:
            return json.loads(path.read_text())
        except Exception:
            log.warning("cache parse fail: %s", path.name)

    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq"
    last_err = None
    for attempt in range(3):
        try:
            async with session.get(url,
                                   params={"tqx": "out:json", "gid": gid},
                                   timeout=aiohttp.ClientTimeout(total=25)) as r:
                if r.status in (429, 500, 502, 503, 504):
                    last_err = f"HTTP {r.status}"
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                r.raise_for_status()
                text = await r.text()
            start, end = text.find("{"), text.rfind("}")
            if start == -1 or end == -1:
                raise ValueError("Unexpected GViz response")
            data = json.loads(text[start:end + 1])
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data))
            tmp.replace(path)
            return data
        except Exception as e:
            last_err = e
            await asyncio.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"fetch failed after retries: {last_err}")

# ============================================================
# EXTRACT
# ============================================================
KEYWORDS = [
    "Trespass Start Date", "Trespass End Date", "Date Issued", "Date Certified",
    "Date Served", "Date Appealed", "Date End", "Expiration Date",
    "Case Number", "Control Number", "Username", "Defendant", "Plaintiff",
    "Plantiff", "Administrator", "Issued By", "Served By", "Agency", "Status",
    "Type", "Duration", "Property", "Reason", "Appeal Status", "Able to Appeal",
    "Certification", "Rank", "Title", "Job Type", "Jurisdiction",
    "Consecutive Terms", "Selection", "Division", "Offenses", "Award",
    "Punishment", "Notes", "Callsign", "Verdict", "Current Status",
    "Issued Date", "DC ID", "RBLX ID",
]

def scrub_header(label: str) -> str:
    if not label or not label.strip():
        return "—"
    h = re.sub(r"\s+", " ", label.replace("\n", " ")).strip()
    if len(h) <= 40:
        return h
    low = h.lower()
    if "username" in low:
        return "Username"
    matches = [kw for kw in KEYWORDS if kw.lower() in low]
    return max(matches, key=len) if matches else h[-30:].strip()

def _dedupe_headers(headers: list) -> list:
    seen = {}
    out = []
    for i, h in enumerate(headers):
        name = h.strip() or f"Column {i+1}"
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 1
        out.append(name)
    return out

def _is_garbage_row(row, cap=500) -> bool:
    return any(len(c) > cap for c in row if isinstance(c, str))

def _is_header_like(row) -> bool:
    ne = [c for c in row if c and c.strip()]
    if len(ne) < 3:
        return False
    shortish = sum(1 for c in ne if 0 < len(c) < 50)
    numeric = sum(1 for c in ne if re.match(r"^[\d/.\-]+$", c))
    return shortish >= 3 and numeric == 0

def extract(data):
    tbl = data.get("table") or {}
    cols = tbl.get("cols") or []
    raw  = tbl.get("rows") or []
    labels = [(c.get("label") or "").strip() for c in cols]

    # --- Row conversion with whitespace normalization ---
    rows = []
    for r in raw:
        cells = []
        for c in (r.get("c") or []):
            if not c:
                cells.append("")
                continue
            v = c.get("f") if c.get("f") is not None else c.get("v")
            if v is None:
                cells.append("")
                continue
            # Normalize: strip \r, \n, tabs, collapse whitespace, trim
            s = str(v).replace("\r", " ").replace("\n", " ")
            s = re.sub(r"\s+", " ", s).strip()
            cells.append(s)
        rows.append(cells)

    width = max([len(labels)] + [len(r) for r in rows] + [0])
    labels += [""] * (width - len(labels))
    rows = [r + [""] * (width - len(r)) for r in rows]

    if not any(labels) or sum(1 for h in labels if h) < width // 2:
        for i, r in enumerate(rows[:15]):
            if _is_header_like(r):
                labels, rows = r, rows[:i] + rows[i + 1:]
                break

    headers = [scrub_header(h) or f"Col {i+1}" for i, h in enumerate(labels)]
    headers = _dedupe_headers(headers)
    rows = [r for r in rows if not _is_garbage_row(r)]
    return headers, rows

# ============================================================
# SUBJECT COLUMN DETECTION
# ============================================================
COLMAP_PATH = CACHE_DIR / "colmap.json"

def _load_colmap() -> dict:
    try:
        return json.loads(COLMAP_PATH.read_text())
    except Exception:
        return {}

def _save_colmap(d: dict):
    try:
        tmp = COLMAP_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(d))
        tmp.replace(COLMAP_PATH)
    except Exception:
        pass

COLMAP = _load_colmap()

def _validate_col(headers, rows, idx):
    if idx is None or idx >= len(headers):
        return False
    if not re.search(r"username", str(headers[idx]), re.I):
        sample = [r[idx] for r in rows[:30] if idx < len(r) and r[idx]]
        if not sample:
            return False
        hits = sum(1 for v in sample if looks_like_username(v))
        return hits >= max(2, len(sample) // 3)
    return True

def detect_subject_col(headers, rows, cache_key=None, override=None):
    if override is not None:
        return override
    if cache_key and cache_key in COLMAP:
        idx = COLMAP[cache_key]
        if _validate_col(headers, rows, idx):
            return idx

    chosen = None
    for i, h in enumerate(headers):
        if re.search(r"username", str(h), re.I):
            chosen = i
            break
    if chosen is None and rows:
        scores = [0] * len(headers)
        for r in rows:
            for i in range(min(len(headers), len(r))):
                if looks_like_username(r[i]):
                    scores[i] += 1
        if any(scores):
            chosen = max(range(len(scores)), key=lambda i: scores[i])

    if cache_key is not None:
        COLMAP[cache_key] = chosen
        _save_colmap(COLMAP)
    return chosen

# ============================================================
# DATABASE
# ============================================================
class Database:
    def __init__(self, records, *, loaded_at=None):
        self.records   = tuple(records)
        self.loaded_at = loaded_at if loaded_at is not None else time.time()
        idx = defaultdict(list)
        for r in self.records:
            if r["subject"]:
                idx[_norm(r["subject"])].append(r)
        self.by_subj = {k: tuple(v) for k, v in idx.items()}
        self.subjects = tuple(sorted({r["subject"] for r in self.records if r["subject"]}))

    def get(self, username: str):
        return self.by_subj.get(_norm(username), ())

async def build_database():
    async with aiohttp.ClientSession(
            headers={"User-Agent": f"DatabaseLookup/{APP_VERSION}"}) as session:
        tasks = [fetch_gviz(session, s["id"], s["gid"]) for s in SOURCES]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    records = []
    status = {}
    for src, res in zip(SOURCES, results):
        if isinstance(res, Exception):
            log.warning("load ✗ %s: %r", src["name"], res)
            status[src["name"]] = f"error: {res.__class__.__name__}"
            continue
        try:
            headers, rows = extract(res)
            cache_key = f"{src['id']}:{src['gid']}"
            override = src.get("subj_override")
            subj = detect_subject_col(headers, rows, cache_key, override)
            count = 0
            unattributed = 0
            for row in rows:
                if not any(c.strip() for c in row):
                    continue
                raw_subj = (row[subj]
                            if (subj is not None and subj < len(row)) else "")
                # Aggressive cleanup for stray CR/LF/tabs/zero-width chars
                subject = re.sub(r"[\r\n\t\u200b\u200c\u200d]+", "",
                                 str(raw_subj)).strip()
                if not subject:
                    unattributed += 1
                    continue
                records.append({
                    "source": src["name"], "cat": src["cat"],
                    "sheet_id": src["id"], "gid": src["gid"],
                    "headers": headers, "row": row,
                    "subject": subject, "subj_col": subj,
                })
                count += 1
            msg = f"ok ({count} rows"
            if unattributed:
                msg += f", {unattributed} unattributed"
            msg += ")"
            status[src["name"]] = msg
        except Exception as e:
            log.exception("parse ✗ %s", src["name"])
            status[src["name"]] = f"error: {e.__class__.__name__}"

    db = Database(records)
    log.info("db loaded: %d records · %d subjects", len(db.records), len(db.subjects))
    return db, status

# ============================================================
# OVERVIEW
# ============================================================
INACTIVE_STATUS = ("retired", "terminated", "removed", "resigned")

def _role_date(r):
    return parse_date(field(r, "Date", "Date Issued", "Date Certified"))

def _role_agency(r):
    return (field(r, "Agency") or field(r, "Division")
            or field(r, "Job Type") or "?").strip()

def _split_employment(records):
    by_agency = {}
    for r in records:
        agency = _role_agency(r)
        key = _norm(agency) or agency.lower()
        dt = _role_date(r)
        cur = by_agency.get(key)
        if cur is None:
            by_agency[key] = r
            continue
        cur_dt = _role_date(cur)
        if dt and (not cur_dt or dt > cur_dt):
            by_agency[key] = r

    current, former = [], []
    for r in by_agency.values():
        status = field(r, "Status").lower()
        (former if any(s in status for s in INACTIVE_STATUS) else current).append(r)
    return current, former

def build_overview(username: str, db: Database) -> dict:
    mine = list(db.get(username))

    ov = {
        "username": username,
        "is_attorney": False,
        "current_roles": [], "former_roles": [],
        "certs": (),
        "cert_punishments": [],
        "punishments": [],
        "blacklists": [],
        "active_blacklists": [],
        "warrants": [], "trespass": [], "awards": [],
        "other": [],
        "records": mine,
        "total_sources": len({r["source"] for r in mine}),
        "total_records": len(mine),
    }

    certs_set = set()
    employment_rows = []

    for r in mine:
        cat = r["cat"]
        if cat == "Attorneys":
            ov["is_attorney"] = True
        elif cat == "Employment":
            employment_rows.append(r)
        elif cat == "Certifications":
            if "chart" in r["source"].lower():
                for i, h in enumerate(r["headers"]):
                    hn = _norm(str(h))
                    if hn in CERT_NORM:
                        v = r["row"][i] if i < len(r["row"]) else ""
                        if v.strip().lower() in ("true", "yes", "1", "y", "✅"):
                            certs_set.add(CERT_NORM[hn])
        elif cat == "CertActions":
            ov["cert_punishments"].append(r)
        elif cat == "Punishments":
            ov["punishments"].append(r)
        elif cat == "Blacklist":
            ov["blacklists"].append(r)
            if _is_active_blacklist(r):
                ov["active_blacklists"].append(r)
        elif cat == "Warrants":    ov["warrants"].append(r)
        elif cat == "Trespass":    ov["trespass"].append(r)
        elif cat == "Awards":      ov["awards"].append(r)
        else:                      ov["other"].append(r)

    ov["current_roles"], ov["former_roles"] = _split_employment(employment_rows)

    ordered = [c for c in CERT_COLUMNS if c in certs_set]
    for c in certs_set:
        if c not in ordered:
            ordered.append(c)
    ov["certs"] = tuple(ordered)

    for k in ("punishments", "cert_punishments", "blacklists", "warrants",
              "trespass", "awards", "current_roles", "former_roles"):
        ov[k].sort(key=_date_sort_key, reverse=True)

    return ov

def _date_sort_key(rec):
    dt = parse_date(field(rec, "Date Issued", "Date", "Date Certified",
                          "Date Served", "Date Appealed",
                          "Expiration Date", "Trespass End Date",
                          "Issued Date"))
    return dt.timestamp() if dt else 0.0

def summary_line(ov: dict) -> str:
    parts = []
    if ov["is_attorney"]:
        parts.append("BAR Attorney")
    agencies = []
    for r in ov["current_roles"]:
        a = field(r, "Agency") or field(r, "Division") or field(r, "Job Type")
        if a and a not in agencies:
            agencies.append(a)
    for a in agencies[:3]:
        parts.append(a)
    if ov["active_blacklists"]:
        kinds = []
        for r in ov["active_blacklists"]:
            k = field(r, "Status") or "Blacklist"
            if k not in kinds:
                kinds.append(k)
        parts.append("BL: " + " / ".join(kinds))
    if ov["cert_punishments"]:
        parts.append(f"{len(ov['cert_punishments'])} Cert Action(s)")
    if ov["punishments"]:
        parts.append(f"{len(ov['punishments'])} Punishment(s)")
    if ov["warrants"]: parts.append(f"{len(ov['warrants'])} Warrant(s)")
    if ov["trespass"]: parts.append(f"{len(ov['trespass'])} Trespass")
    return " · ".join(parts) if parts else "No notable records"

# ============================================================
# FORMATTERS
# ============================================================
def _fmt_role(r):
    agency = field(r, "Agency") or field(r, "Division") or field(r, "Job Type")
    rank   = field(r, "Rank") or field(r, "Title")
    status = field(r, "Status")
    date   = field(r, "Date")
    parts = [p for p in [agency, rank, status, date] if p]
    body = " · ".join(parts) if parts else "—"
    return body + f" · {sheet_link(r, '📄')}"

def _fmt_cert_punish(r):
    status = field(r, "Status")
    cert   = field(r, "Certification")
    date   = field(r, "Date Issued", "Date")
    by     = _attribute_issuer(field(r, "Administrator", "Issued By"), r)
    parts = []
    if status: parts.append(f"`{status}`")
    if cert:   parts.append(cert)
    if date:   parts.append(date)
    if by:     parts.append(f"by {by}")
    body = " · ".join(parts) if parts else "—"
    return body + f" · {sheet_link(r, '📄')}"

def _fmt_punish(r):
    status = field(r, "Punishment", "Status")
    agency = field(r, "Agency") or _source_agency(r)
    rank   = field(r, "Rank")
    date   = field(r, "Date Issued", "Date")
    by     = _attribute_issuer(field(r, "Administrator", "Issued By"), r)
    parts = []
    if status: parts.append(f"`{status}`")
    if agency: parts.append(f"from **{agency}**")
    if rank:   parts.append(rank)
    if date:   parts.append(date)
    if by:     parts.append(f"by {by}")
    body = " · ".join(parts) if parts else "—"
    return body + f" · {sheet_link(r, '📄')}"

def _fmt_blacklist(r):
    kind   = field(r, "Status") or "Blacklist"
    reason = field(r, "Reason")
    date   = field(r, "Date Issued", "Issued Date")
    appeal = field(r, "Appeal Status")
    able   = field(r, "Able to Appeal")
    by     = _attribute_issuer(field(r, "Administrator", "Issued By"), r)
    parts = [f"`{kind}`"]
    if reason: parts.append(reason)
    if date and date.lower() != "tbd": parts.append(date)
    if appeal: parts.append(f"appeal: {appeal}")
    if able and able.lower() not in ("n/a", "none", ""):
        parts.append(f"until {able}")
    if by:     parts.append(f"by {by}")
    return " · ".join(parts) + f" · {sheet_link(r, '📄')}"

def _fmt_warrant(r):
    offenses = field(r, "Offenses")
    case     = field(r, "Case Number")
    tag      = " ⚠ EXPIRED" if is_expired(r) else ""
    parts = []
    if offenses: parts.append(offenses[:120] + tag)
    elif tag:    parts.append("—" + tag)
    if case: parts.append(f"`{case}`")
    return " · ".join(parts) + f" · {sheet_link(r, '📄')}"

def _fmt_trespass(r):
    type_ = field(r, "Type", "Trespass Type") or "Trespass"
    end   = field(r, "Expiration Date", "Trespass End Date")
    prop  = field(r, "Property")
    tag   = " ⚠ EXPIRED" if is_expired(r) else ""
    parts = [f"`{type_}`{tag}"]
    if prop: parts.append(prop)
    if end:  parts.append(f"ends {end}")
    return " · ".join(parts) + f" · {sheet_link(r, '📄')}"

def _fmt_award(r):
    award = field(r, "Award")
    date  = field(r, "Date Issued")
    by    = _attribute_issuer(field(r, "Administrator", "Issued By"), r)
    parts = []
    if award: parts.append(f"**{award}**")
    if date:  parts.append(date)
    if by:    parts.append(f"by {by}")
    return " · ".join(parts) + f" · {sheet_link(r, '📄')}"

# ============================================================
# SECTION SPECS / COLORS
# ============================================================
EMBED_COLOR = {
    "Overview":      0x6f99be,
    "Certifications":0xc9b169,
    "Attorneys":     0x6faabb,
    "Current Roles": 0x7eae8f,
    "Former Roles":  0x919aa5,
    "Cert Actions":  0xc9a765,
    "Punishments":   0xc97777,
    "Blacklist":     0xc97777,
    "Warrants":      0xc29470,
    "Trespass":      0xc9a765,
    "Awards":        0xc9b169,
}

SECTION_SPECS = [
    ("certs",            "Certifications", None,             "CERTIFICATIONS"),
    ("is_attorney",      "Attorneys",      None,             "ATTORNEY"),
    ("current_roles",    "Current Roles",  _fmt_role,        "CURRENT ROLES"),
    ("cert_punishments", "Cert Actions",   _fmt_cert_punish, "CERT ACTIONS"),
    ("punishments",      "Punishments",    _fmt_punish,      "PUNISHMENTS"),
    ("blacklists",       "Blacklist",      _fmt_blacklist,   "BLACKLISTS"),
    ("warrants",         "Warrants",       _fmt_warrant,     "WARRANTS"),
    ("trespass",         "Trespass",       _fmt_trespass,    "TRESPASS"),
    ("awards",           "Awards",         _fmt_award,       "AWARDS"),
    ("former_roles",     "Former Roles",   _fmt_role,        "FORMER ROLES"),
]

# ============================================================
# EMBED HELPERS
# ============================================================
def fit(text: str, limit: int = 1024) -> str:
    if len(text) <= limit:
        return text
    lines, kept, total = text.split("\n"), [], 0
    for ln in lines:
        if total + len(ln) + 1 > limit - 40:
            kept.append(f"…and {len(lines) - len(kept)} more")
            break
        kept.append(ln)
        total += len(ln) + 1
    return "\n".join(kept)

def _esc(s: str) -> str:
    return discord.utils.escape_markdown(str(s))

def _bl_warning_lines(ov):
    out = []
    for r in ov["active_blacklists"]:
        kind   = field(r, "Status") or "Blacklist"
        reason = field(r, "Reason")
        date   = field(r, "Date Issued", "Issued Date")
        appeal = field(r, "Appeal Status")
        src    = _source_agency(r)
        parts = [f"**{_esc(kind)}**"]
        if src:    parts.append(f"*{_esc(src)}*")
        if reason: parts.append(_esc(reason))
        if date and date.lower() != "tbd": parts.append(f"`{date}`")
        if appeal: parts.append(f"appeal: *{_esc(appeal)}*")
        out.append("> " + " · ".join(parts))
    return out

def _source_lines(ov):
    seen, lines = set(), []
    for r in ov["records"]:
        key = (r["sheet_id"], r["gid"])
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"• {sheet_link(r, r['source'])}")
    return lines

def _latest_date(records):
    best = None
    for r in records:
        for name in ("Date Issued", "Date", "Date Certified", "Date Served",
                     "Expiration Date", "Trespass End Date", "Issued Date"):
            dt = parse_date(field(r, name))
            if dt and (best is None or dt > best):
                best = dt
            break
    return best.strftime("%Y-%m-%d") if best else None

def _all_activity_rows(ov):
    return (ov["punishments"] + ov["cert_punishments"] + ov["blacklists"]
            + ov["warrants"] + ov["trespass"] + ov["current_roles"]
            + ov["awards"])

# ============================================================
# OVERVIEW EMBED
# ============================================================
def overview_embed(ov, *, failed_sources: int = 0, total_sources: int = 0) -> discord.Embed:
    has_bl = bool(ov["active_blacklists"])

    e = discord.Embed(
        title=f"{TITLE_ICONS['Overview']}  Database Lookup — {_esc(ov['username'])}",
        color=0xd44a4a if has_bl else EMBED_COLOR["Overview"],
        timestamp=NOW_AWARE(),
    )
    e.set_author(name="Concord Records")

    desc: list[str] = []

    if has_bl:
        desc.extend(_bl_warning_lines(ov))

    pills: list[str] = []
    if ov["is_attorney"]:
        pills.append("⚖️ `BAR Attorney`")
    agencies: list[str] = []
    for r in ov["current_roles"]:
        a = field(r, "Agency") or field(r, "Division") or field(r, "Job Type")
        if a and a not in agencies:
            agencies.append(a)
    if agencies:
        pills.append("🟢 " + " · ".join(f"`{_esc(a)}`" for a in agencies[:4]))
    if ov["cert_punishments"]:
        pills.append(f"📛 `{len(ov['cert_punishments'])} cert action(s)`")
    if ov["punishments"]:
        pills.append(f"🔨 `{len(ov['punishments'])} punishment(s)`")
    if pills:
        if desc: desc.append("")
        desc.extend(pills)

    if not desc:
        desc.append(f"*{ov['total_records']} record(s) across "
                    f"{ov['total_sources']} source(s)*")

    e.description = "\n".join(desc)

    latest = _latest_date(_all_activity_rows(ov))
    e.add_field(name="📊  Records", value=f"**{ov['total_records']}**", inline=True)
    e.add_field(name="📁  Sources", value=f"**{ov['total_sources']}**", inline=True)
    e.add_field(name="🕐  Latest",  value=f"**{latest or '—'}**",     inline=True)

    if ov["certs"]:
        e.add_field(
            name=f"{TITLE_ICONS['Certifications']}  Certifications",
            value="  ".join(f"`{_esc(c)}`" for c in ov["certs"]),
            inline=False,
        )

    if ov["current_roles"]:
        lines = []
        for r in ov["current_roles"]:
            a = field(r, "Agency") or field(r, "Division") or field(r, "Job Type")
            rank   = field(r, "Rank") or field(r, "Title")
            status = field(r, "Status")
            date   = field(r, "Date")
            g = _status_glyph(status)
            line = f"{g} **{_esc(a or '—')}**"
            tail = []
            if rank:   tail.append(_esc(rank))
            if status: tail.append(f"`{_esc(status)}`")
            if date:   tail.append(date)
            if tail: line += "  ·  " + " · ".join(tail)
            lines.append(line)
        e.add_field(name=f"{TITLE_ICONS['Current Roles']}  Current Roles  ·  {len(ov['current_roles'])}",
                    value=fit("\n".join(lines)), inline=False)

    if ov["cert_punishments"]:
        lines = []
        for r in ov["cert_punishments"]:
            status = field(r, "Status"); cert = field(r, "Certification")
            date   = field(r, "Date Issued", "Date")
            by     = _attribute_issuer(field(r, "Administrator", "Issued By"), r)
            parts = []
            if status: parts.append(f"**{_esc(status)}**")
            if cert:   parts.append(_esc(cert))
            if date:   parts.append(f"`{date}`")
            if by:     parts.append(f"by {_esc(by)}")
            lines.append("• " + ("  ·  ".join(parts) if parts else "—"))
        e.add_field(name=f"{TITLE_ICONS['Cert Actions']}  Cert Actions  ·  {len(ov['cert_punishments'])}",
                    value=fit("\n".join(lines)), inline=False)

    if ov["punishments"]:
        lines = []
        for r in ov["punishments"]:
            status = field(r, "Punishment", "Status")
            agency = field(r, "Agency") or _source_agency(r)
            date   = field(r, "Date Issued", "Date")
            by     = _attribute_issuer(field(r, "Administrator", "Issued By"), r)
            parts = []
            if status: parts.append(f"🔴 **{_esc(status)}**")
            if agency: parts.append(f"from `{_esc(agency)}`")
            if date:   parts.append(f"`{date}`")
            if by:     parts.append(f"by {_esc(by)}")
            lines.append("• " + ("  ·  ".join(parts) if parts else "—"))
        e.add_field(name=f"{TITLE_ICONS['Punishments']}  Punishments  ·  {len(ov['punishments'])}",
                    value=fit("\n".join(lines)), inline=False)

    if ov["blacklists"]:
        label = "Blacklist (all)" if ov["active_blacklists"] else "Blacklist History"
        lines = []
        for r in ov["blacklists"]:
            kind   = field(r, "Status") or "Blacklist"
            reason = field(r, "Reason")
            date   = field(r, "Date Issued", "Issued Date")
            appeal = field(r, "Appeal Status")
            by     = _attribute_issuer(field(r, "Administrator", "Issued By"), r)
            src    = _source_agency(r)
            active = _is_active_blacklist(r)
            g = "🚫" if active else "✅"
            parts = [f"{g} **{_esc(kind)}**"]
            if src:    parts.append(f"*{_esc(src)}*")
            if reason: parts.append(_esc(reason))
            if date and date.lower() != "tbd": parts.append(f"`{date}`")
            if appeal: parts.append(f"appeal: *{_esc(appeal)}*")
            if by:     parts.append(f"by {_esc(by)}")
            lines.append("• " + "  ·  ".join(parts))
        e.add_field(name=f"{TITLE_ICONS['Blacklist']}  {label}  ·  {len(ov['blacklists'])}",
                    value=fit("\n".join(lines)), inline=False)

    if ov["warrants"]:
        lines = []
        for r in ov["warrants"]:
            offenses = field(r, "Offenses"); case = field(r, "Case Number")
            g = "✅" if is_expired(r) else "⚠️"
            body = _esc((offenses or "—")[:120])
            line = f"• {g} {body}"
            if case: line += f"  ·  `{_esc(case)}`"
            lines.append(line)
        e.add_field(name=f"{TITLE_ICONS['Warrants']}  Warrants  ·  {len(ov['warrants'])}",
                    value=fit("\n".join(lines)), inline=False)

    if ov["trespass"]:
        lines = []
        for r in ov["trespass"]:
            type_ = field(r, "Type", "Trespass Type") or "Trespass"
            end   = field(r, "Expiration Date", "Trespass End Date")
            prop  = field(r, "Property")
            g = "✅" if is_expired(r) else "🚷"
            parts = [f"{g} **{_esc(type_)}**"]
            if prop: parts.append(_esc(prop))
            if end:  parts.append(f"ends `{end}`")
            lines.append("• " + "  ·  ".join(parts))
        e.add_field(name=f"{TITLE_ICONS['Trespass']}  Trespass  ·  {len(ov['trespass'])}",
                    value=fit("\n".join(lines)), inline=False)

    if ov["awards"]:
        lines = []
        for r in ov["awards"]:
            award = field(r, "Award"); date = field(r, "Date Issued")
            if not award: continue
            line = f"🏆 **{_esc(award)}**"
            if date: line += f"  ·  `{date}`"
            lines.append("• " + line)
        if lines:
            e.add_field(name=f"{TITLE_ICONS['Awards']}  Awards  ·  {len(ov['awards'])}",
                        value=fit("\n".join(lines)), inline=False)

    if ov["former_roles"]:
        seen, lines = set(), []
        for r in ov["former_roles"]:
            a = field(r, "Agency") or "?"
            s = field(r, "Status") or "former"
            key = f"{a} ({s})"
            if key in seen: continue
            seen.add(key)
            lines.append(f"⚫ `{_esc(a)}`  ·  *{_esc(s)}*")
        e.add_field(name=f"{TITLE_ICONS['Former Roles']}  Former Roles  ·  {len(seen)}",
                    value=fit("\n".join(lines)), inline=False)

    src_lines = _source_lines(ov)
    if src_lines:
        e.add_field(name=f"📎  Sources  ·  {len(src_lines)}",
                    value=fit("\n".join(src_lines)), inline=False)

    footer_bits = []
    if total_sources and failed_sources:
        footer_bits.append(f"⚠ {failed_sources}/{total_sources} sources failed")
    footer_bits.append(f"v{APP_VERSION}")
    e.set_footer(text="Database Lookup  ·  " + "  ·  ".join(footer_bits))
    return e

# ============================================================
# SECTION EMBEDS
# ============================================================
def section_embed(name, fields, ov, label=None) -> discord.Embed:
    icon  = TITLE_ICONS.get(name, "📄")
    title = f"{icon}  {_esc(ov['username'])} — {label or name}"
    e = discord.Embed(title=title, color=EMBED_COLOR.get(name, 0x6f99be),
                      timestamp=NOW_AWARE())
    for f in fields:
        e.add_field(name=f["name"], value=fit(f["value"]), inline=False)
    return e

def build_sections(ov):
    secs = []
    for key, title, fmt, _code in SECTION_SPECS:
        val = ov.get(key)
        if key == "certs":
            if not ov["certs"]:
                continue
            secs.append((title, [{"name": "Certs",
                                  "value": ", ".join(_esc(c) for c in ov["certs"])}]))
        elif key == "is_attorney":
            if not ov["is_attorney"]:
                continue
            secs.append((title, [{"name": "Attorney",
                                  "value": "Bar-certified attorney (Dept. of State)"}]))
        elif key == "former_roles":
            if not ov["former_roles"]:
                continue
            seen, lines = set(), []
            for r in ov["former_roles"]:
                k = f"{field(r,'Agency') or '?'} ({field(r,'Status') or 'former'})"
                if k in seen:
                    continue
                seen.add(k)
                lines.append(f"• {_esc(k)} · {sheet_link(r,'📄')}")
            secs.append((title, [{"name": "Former", "value": "\n".join(lines)}]))
        else:
            if not val:
                continue
            lines = [f"• {fmt(r)}" for r in val]
            secs.append((title, [{"name": title, "value": "\n".join(lines)}]))
    return secs

def paginate(ov, *, failed_sources: int = 0, total_sources: int = 0):
    pages = [("Overview",
              overview_embed(ov, failed_sources=failed_sources,
                             total_sources=total_sources))]
    for name, fields in build_sections(ov):
        chunk, size = [], 0
        chunks = []
        for f in fields:
            if size + len(f["value"]) > 3500 or len(chunk) >= 6:
                chunks.append(chunk); chunk, size = [], 0
            chunk.append(f)
            size += len(f["value"])
        if chunk:
            chunks.append(chunk)
        total = len(chunks)
        for i, ch in enumerate(chunks, 1):
            label = name if total == 1 else f"{name} ({i}/{total})"
            pages.append((label, section_embed(name, ch, ov, label=label)))
    return pages

# ============================================================
# PNG
# ============================================================
BG     = (18, 22, 29)
BORDER = (49, 57, 68)
TEXT   = (226, 230, 236)
MUTED  = (151, 160, 172)
ACCENT = (111, 153, 190)
WARN   = (201, 119, 119)
WARN_BG= (46, 22, 22)

STAT_BG     = (24, 29, 38)
STAT_BORDER = (55, 65, 78)
STAT_LABEL  = (151, 160, 172)

SECTION_COLORS = {
    "CERTIFICATIONS": (201, 177, 105),
    "CURRENT ROLES":  (126, 174, 143),
    "ATTORNEY":       (111, 170, 187),
    "CERT ACTIONS":   (201, 167, 101),
    "PUNISHMENTS":    (201, 119, 119),
    "BLACKLISTS":     (201, 119, 119),
    "WARRANTS":       (194, 148, 112),
    "TRESPASS":       (201, 167, 101),
    "AWARDS":         (201, 177, 105),
    "FORMER ROLES":   (145, 154, 165),
}

_FONT_CACHE: dict = {}

def _font(size: int, bold: bool = False):
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    paths = []
    if os.name == "nt":
        paths += [f"C:/Windows/Fonts/segoeu{'b' if bold else ''}.ttf",
                  f"C:/Windows/Fonts/arial{'bd' if bold else ''}.ttf"]
    paths += [
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold
            else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf" if bold
            else "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for p in paths:
        try:
            f = ImageFont.truetype(p, size)
            _FONT_CACHE[key] = f
            return f
        except Exception:
            continue
    f = ImageFont.load_default()
    _FONT_CACHE[key] = f
    return f

def _wrap_hanging(draw, text, font, max_w, indent=0):
    text = _strip_nonbmp(text)
    avail = max_w - indent
    if avail <= 10:
        avail = max_w
    words = text.split()
    lines, cur = [], ""
    for w in words:
        probe = (cur + " " + w).strip()
        if draw.textlength(probe, font=font) <= avail:
            cur = probe
        else:
            if cur:
                lines.append(cur); cur = w
            else:
                lines.append(w); cur = ""
    if cur:
        lines.append(cur)
    return lines or [""]

# --- PNG row formatters ---
def _png_role(r):
    agency = field(r, "Agency") or field(r, "Division") or field(r, "Job Type")
    rank   = field(r, "Rank") or field(r, "Title")
    status = field(r, "Status")
    date   = field(r, "Date")
    g = _status_ascii(status)
    parts = [p for p in [agency, rank, status, date] if p]
    body = "   ·   ".join(parts) if parts else "—"
    return (f"{g}   " if g else "") + body

def _png_cert_punish(r):
    status = field(r, "Status")
    cert   = field(r, "Certification")
    date   = field(r, "Date Issued", "Date")
    by     = _attribute_issuer(field(r, "Administrator", "Issued By"), r)
    parts = []
    if status: parts.append(status)
    if cert:   parts.append(cert)
    if date:   parts.append(date)
    if by:     parts.append(f"by {by}")
    return "   ·   ".join(parts) if parts else "—"

def _png_punish(r):
    status = field(r, "Punishment", "Status")
    agency = field(r, "Agency") or _source_agency(r)
    rank   = field(r, "Rank")
    date   = field(r, "Date Issued", "Date")
    by     = _attribute_issuer(field(r, "Administrator", "Issued By"), r)
    parts = []
    if status: parts.append(status)
    if agency: parts.append(f"from {agency}")
    if rank:   parts.append(rank)
    if date:   parts.append(date)
    if by:     parts.append(f"by {by}")
    return "   ·   ".join(parts) if parts else "—"

def _png_blacklist(r):
    kind   = field(r, "Status") or "Blacklist"
    reason = field(r, "Reason")
    date   = field(r, "Date Issued", "Issued Date")
    appeal = field(r, "Appeal Status")
    by     = _attribute_issuer(field(r, "Administrator", "Issued By"), r)
    src    = _source_agency(r)
    active = _is_active_blacklist(r)
    g = "ACTIVE" if active else "RESOLVED"
    parts = [f"[{g}] {kind}"]
    if src:    parts.append(src)
    if reason: parts.append(reason)
    if date and date.lower() != "tbd": parts.append(date)
    if appeal: parts.append(f"appeal: {appeal}")
    if by:     parts.append(f"by {by}")
    return "   ·   ".join(parts)

def _png_warrant(r):
    offenses = field(r, "Offenses")
    case     = field(r, "Case Number")
    tag      = "   [EXPIRED]" if is_expired(r) else ""
    line = (offenses or "—") + tag
    if case: line += f"   ·   {case}"
    return line

def _png_trespass(r):
    type_ = field(r, "Type", "Trespass Type") or "Trespass"
    end   = field(r, "Expiration Date", "Trespass End Date")
    prop  = field(r, "Property")
    tag   = "   [EXPIRED]" if is_expired(r) else ""
    parts = [type_ + tag]
    if prop: parts.append(prop)
    if end:  parts.append(f"ends {end}")
    return "   ·   ".join(parts)

def _png_award(r):
    award = field(r, "Award")
    date  = field(r, "Date Issued")
    by    = _attribute_issuer(field(r, "Administrator", "Issued By"), r)
    parts = []
    if award: parts.append(award)
    if date:  parts.append(date)
    if by:    parts.append(f"by {by}")
    return "   ·   ".join(parts) if parts else "—"

def _build_plan(ov):
    plan = [("title", ov["username"], f"Database Lookup · v{APP_VERSION}")]

    if ov["active_blacklists"]:
        lines = []
        for r in ov["active_blacklists"]:
            kind   = field(r, "Status") or "Blacklist"
            reason = field(r, "Reason")
            date   = field(r, "Date Issued", "Issued Date")
            appeal = field(r, "Appeal Status")
            src    = _source_agency(r)
            parts = [f"{kind}"]
            if src:    parts.append(src)
            if reason: parts.append(reason)
            if date and date.lower() != "tbd": parts.append(f"({date})")
            if appeal: parts.append(f"appeal: {appeal}")
            lines.append("   ·   ".join(parts))
        plan.append(("warn", "ACTIVE BLACKLIST", lines))

    latest = _latest_date(_all_activity_rows(ov)) or "—"
    plan.append(("spacer", 22))
    plan.append(("stats", [
        ("", "Records", str(ov["total_records"])),
        ("", "Sources", str(ov["total_sources"])),
        ("", "Latest",  latest),
    ]))
    plan.append(("spacer", 26))

    plan.append(("summary", summary_line(ov)))
    plan.append(("spacer", 30))

    section_counts = {}
    for key, _title, _fmt, code in SECTION_SPECS:
        if key == "certs":         n = len(ov["certs"])
        elif key == "is_attorney": n = 1 if ov["is_attorney"] else 0
        else:                      n = len(ov.get(key) or [])
        if n: section_counts[code] = n
    max_n = max(section_counts.values()) if section_counts else 1

    def add_section(code, entries, style="normal", icon=""):
        plan.append(("sec", code, style, section_counts.get(code, 0), max_n, icon))
        plan.append(("rule",))
        for e in entries:
            plan.append(("rec", e, style))
        plan.append(("spacer", 22))

    if ov["certs"]:
        add_section("CERTIFICATIONS", [", ".join(ov["certs"])])
    if ov["is_attorney"]:
        add_section("ATTORNEY", ["Bar-certified attorney — Dept. of State"])
    if ov["current_roles"]:
        add_section("CURRENT ROLES",
                    [_png_role(r) for r in ov["current_roles"]])
    if ov["cert_punishments"]:
        add_section("CERT ACTIONS",
                    [_png_cert_punish(r) for r in ov["cert_punishments"]])
    if ov["punishments"]:
        add_section("PUNISHMENTS",
                    [_png_punish(r) for r in ov["punishments"]])
    if ov["blacklists"]:
        add_section("BLACKLISTS",
                    [_png_blacklist(r) for r in ov["blacklists"]])
    if ov["warrants"]:
        add_section("WARRANTS",
                    [_png_warrant(r) for r in ov["warrants"]])
    if ov["trespass"]:
        add_section("TRESPASS",
                    [_png_trespass(r) for r in ov["trespass"]])
    if ov["awards"]:
        add_section("AWARDS",
                    [_png_award(r) for r in ov["awards"]])
    if ov["former_roles"]:
        seen, entries = set(), []
        for r in ov["former_roles"]:
            a = field(r, "Agency") or "?"
            s = field(r, "Status") or "former"
            k = f"{a}   [{s}]"
            if k in seen: continue
            seen.add(k); entries.append(k)
        add_section("FORMER ROLES", entries, style="muted")

    return plan

def build_png(ov) -> io.BytesIO:
    S = PNG_SCALE
    W, PAD = 1400, 60
    PAD_S = PAD * S
    W_S = W * S
    CONTENT_W = W_S - 2 * PAD_S
    BAR_W, BAR_H = 140 * S, 8 * S
    STAT_H = 96 * S

    f_h1   = _font(34 * S, bold=True)
    f_meta = _font(14 * S)
    f_sec  = _font(13 * S, bold=True)
    f_body = _font(16 * S)
    f_rec  = _font(16 * S)
    f_warn = _font(18 * S, bold=True)
    f_foot = _font(12 * S)
    f_statv= _font(28 * S, bold=True)
    f_stat = _font(13 * S)

    plan = _build_plan(ov)

    tmp = Image.new("RGB", (10, 10))
    d = ImageDraw.Draw(tmp)
    heights, wrapped_cache = [], []
    for item in plan:
        kind = item[0]
        if kind == "title":
            _, t, m = item
            h = d.textbbox((0, 0), _strip_nonbmp(t), font=f_h1)[3] + 6 * S
            h += d.textbbox((0, 0), _strip_nonbmp(m), font=f_meta)[3] + 4 * S
            wrapped_cache.append(None)
        elif kind == "warn":
            _, title, lines = item
            h = d.textbbox((0, 0), _strip_nonbmp(title), font=f_warn)[3] + 16 * S
            wrapped_lines = [_wrap_hanging(d, ln, f_body, CONTENT_W - 40 * S)
                             for ln in lines]
            for wl in wrapped_lines:
                h += len(wl) * (d.textbbox((0, 0), "Ag", font=f_body)[3] + 6 * S)
            h += 16 * S
            wrapped_cache.append(wrapped_lines)
        elif kind == "stats":
            h = STAT_H
            wrapped_cache.append(None)
        elif kind == "summary":
            h = d.textbbox((0, 0), _strip_nonbmp(item[1]), font=f_body)[3] + 4 * S
            wrapped_cache.append(None)
        elif kind == "summary_dim":
            h = d.textbbox((0, 0), _strip_nonbmp(item[1]), font=f_meta)[3] + 2 * S
            wrapped_cache.append(None)
        elif kind == "sec":
            code = item[1]
            h = max(d.textbbox((0, 0), _strip_nonbmp(code), font=f_sec)[3] + 8 * S,
                    BAR_H + 6 * S)
            wrapped_cache.append(None)
        elif kind == "rule":
            h = 10 * S; wrapped_cache.append(None)
        elif kind == "spacer":
            h = item[1] * S; wrapped_cache.append(None)
        elif kind in ("rec", "plain"):
            _, text, _ = item
            indent = 22 * S if kind == "rec" else 0
            wrapped = _wrap_hanging(d, text, f_rec, CONTENT_W, indent=indent)
            wrapped_cache.append(wrapped)
            lh = d.textbbox((0, 0), "Ag", font=f_rec)[3] + 8 * S
            h = len(wrapped) * lh
        else:
            h = 0; wrapped_cache.append(None)
        heights.append(h)

    total_h = PAD_S * 2 + sum(heights)

    img = Image.new("RGB", (W_S, total_h), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (W_S, 2 * S)], fill=ACCENT)

    y = PAD_S
    for item, h, wrapped in zip(plan, heights, wrapped_cache):
        kind = item[0]

        if kind == "title":
            _, t, m = item
            t = _strip_nonbmp(t); m = _strip_nonbmp(m)
            t_h = d.textbbox((0, 0), t, font=f_h1)[3]
            draw.text((PAD_S, y), t, font=f_h1, fill=TEXT)
            draw.text((PAD_S, y + t_h + 6 * S), m, font=f_meta, fill=MUTED)

        elif kind == "warn":
            _, title, _lines = item
            x0, y0 = PAD_S, y
            x1, y1 = W_S - PAD_S, y + h
            draw.rounded_rectangle([(x0, y0), (x1, y1)], radius=8 * S,
                                   fill=WARN_BG, outline=WARN, width=2 * S)
            ty = y0 + 14 * S
            draw.text((x0 + 24 * S, ty), "!  " + _strip_nonbmp(title),
                      font=f_warn, fill=WARN)
            ty += d.textbbox((0, 0), title, font=f_warn)[3] + 14 * S
            for wl in wrapped or []:
                for ln in wl:
                    draw.text((x0 + 28 * S, ty), ln, font=f_body, fill=TEXT)
                    ty += d.textbbox((0, 0), "Ag", font=f_body)[3] + 6 * S

        elif kind == "stats":
            _, cards = item
            n = len(cards)
            gap = 20 * S
            total_w = W_S - 2 * PAD_S
            cw = (total_w - gap * (n - 1)) // n
            ch = h
            for i, (_icon, label, value) in enumerate(cards):
                cx = PAD_S + i * (cw + gap)
                cy = y
                draw.rounded_rectangle([(cx, cy), (cx + cw, cy + ch)],
                                       radius=12 * S, fill=STAT_BG,
                                       outline=STAT_BORDER, width=S)
                value = _strip_nonbmp(value)
                vh = d.textbbox((0, 0), value, font=f_statv)[3]
                draw.text((cx + 20 * S, cy + 16 * S), value,
                          font=f_statv, fill=TEXT)
                label = _strip_nonbmp(label)
                draw.text((cx + 20 * S, cy + 16 * S + vh + 8 * S), label,
                          font=f_stat, fill=STAT_LABEL)

        elif kind == "summary":
            draw.text((PAD_S, y), _strip_nonbmp(item[1]),
                      font=f_body, fill=TEXT)

        elif kind == "summary_dim":
            draw.text((PAD_S, y), _strip_nonbmp(item[1]),
                      font=f_meta, fill=MUTED)

        elif kind == "sec":
            _, code, style, count, max_n, _icon = item
            col = MUTED if style == "muted" else SECTION_COLORS.get(code, ACCENT)
            dot_r = 6 * S
            cy_dot = y + (h // 2) - dot_r
            draw.ellipse([(PAD_S, cy_dot), (PAD_S + dot_r * 2, cy_dot + dot_r * 2)],
                         fill=col)
            draw.text((PAD_S + dot_r * 2 + 12 * S, y),
                      _strip_nonbmp(code), font=f_sec, fill=col)
            if count and max_n:
                bx = W_S - PAD_S - BAR_W
                by = y + (h - BAR_H) // 2
                draw.rectangle([(bx, by), (bx + BAR_W, by + BAR_H)],
                               fill=(30, 36, 46))
                frac = count / max_n
                fw = int(BAR_W * frac)
                if fw > 0:
                    draw.rectangle([(bx, by), (bx + fw, by + BAR_H)], fill=col)
                label = f"{count}"
                lw = d.textlength(label, font=f_meta)
                lh2 = d.textbbox((0, 0), "0", font=f_meta)[3]
                draw.text((bx - 10 * S - lw, y + (h - lh2) // 2 - 2 * S),
                          label, font=f_meta, fill=MUTED)

        elif kind == "rule":
            draw.line([(PAD_S, y + 4 * S), (W_S - PAD_S, y + 4 * S)],
                      fill=BORDER, width=S)

        elif kind == "spacer":
            pass

        elif kind in ("rec", "plain"):
            _, text, style = item
            body_col = MUTED if style == "muted" else TEXT
            indent = 22 * S if kind == "rec" else 0
            lh = d.textbbox((0, 0), "Ag", font=f_rec)[3] + 8 * S
            for i, ln in enumerate(wrapped):
                if i == 0 and kind == "rec":
                    draw.text((PAD_S, y), "•", font=f_rec, fill=body_col)
                draw.text((PAD_S + indent, y), ln, font=f_rec, fill=body_col)
                y += lh
            continue

        y += h

    foot = f"Database Lookup v{APP_VERSION}  ·  public GViz endpoints  ·  {NOW_NAIVE():%Y-%m-%d %H:%M} UTC"
    draw.text((PAD_S, total_h - PAD_S - 8 * S), _strip_nonbmp(foot),
              font=f_foot, fill=MUTED)

    total_h_rounded = ((total_h + S - 1) // S) * S
    img = img.resize((W, total_h_rounded // S), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    buf.seek(0)
    return buf

# ============================================================
# PLAIN TEXT
# ============================================================
def build_plain(ov) -> str:
    W = 60
    def rule(ch="-"): return ch * W

    L: list[str] = []

    L.append("+" + "-" * (W - 2) + "+")
    title = f"  DATABASE LOOKUP - {ov['username']}"
    L.append("|" + title.ljust(W - 2)[:W - 2] + "|")
    L.append("+" + "-" * (W - 2) + "+")

    if ov["active_blacklists"]:
        L.append("")
        L.append("!" + "=" * (W - 2) + "!")
        L.append("|" + "  ACTIVE BLACKLIST".ljust(W - 2)[:W - 2] + "|")
        L.append("!" + "=" * (W - 2) + "!")
        for r in ov["active_blacklists"]:
            parts = []
            parts.append(field(r, "Status") or "Blacklist")
            src = _source_agency(r)
            if src: parts.append(src)
            if field(r, "Reason"):        parts.append(field(r, "Reason"))
            d = field(r, "Date Issued", "Issued Date")
            if d and d.lower() != "tbd":  parts.append(d)
            if field(r, "Appeal Status"): parts.append(f"appeal: {field(r, 'Appeal Status')}")
            L.append("  * " + " | ".join(parts))

    L.append("")
    L.append(f"  {summary_line(ov)}")
    latest = _latest_date(_all_activity_rows(ov))
    tail = (f"  Records: {ov['total_records']}   Sources: {ov['total_sources']}")
    if latest:
        tail += f"   Latest: {latest}"
    L.append(tail)

    def add(title, rows, code):
        if not rows:
            return
        L.append("")
        L.append(rule())
        L.append(f"  [{title}]")
        L.append(rule())
        for r in rows:
            L.append("  * " + r)

    if ov["certs"]:
        L.append("")
        L.append(rule())
        L.append("  [CERTIFICATIONS]")
        L.append(rule())
        L.append("  " + ", ".join(ov["certs"]))
    if ov["is_attorney"]:
        add("ATTORNEY", ["Bar-certified attorney - Dept. of State"], "ATTORNEY")

    add("CURRENT ROLES", [
        _status_ascii(field(r, "Status")).ljust(7)
        + " | ".join(p for p in [
            field(r, "Agency") or field(r, "Division") or field(r, "Job Type"),
            field(r, "Rank") or field(r, "Title"),
            field(r, "Status"),
            field(r, "Date"),
        ] if p)
        for r in ov["current_roles"]
    ], "CURRENT ROLES")

    add("CERT ACTIONS", [
        " | ".join(p for p in [
            field(r, "Status"),
            field(r, "Certification"),
            field(r, "Date Issued", "Date"),
            (f"by {_attribute_issuer(field(r, 'Administrator', 'Issued By'), r)}"
             if _attribute_issuer(field(r, "Administrator", "Issued By"), r) else ""),
        ] if p)
        for r in ov["cert_punishments"]
    ], "CERT ACTIONS")

    add("PUNISHMENTS", [
        " | ".join(p for p in [
            field(r, "Punishment", "Status"),
            f"from {field(r, 'Agency') or _source_agency(r)}",
            field(r, "Rank"),
            field(r, "Date Issued", "Date"),
            (f"by {_attribute_issuer(field(r, 'Administrator', 'Issued By'), r)}"
             if _attribute_issuer(field(r, "Administrator", "Issued By"), r) else ""),
        ] if p)
        for r in ov["punishments"]
    ], "PUNISHMENTS")

    bl_label = "BLACKLIST (ALL)" if ov["active_blacklists"] else "BLACKLIST HISTORY"
    add(bl_label, [
        ("ACTIVE  " if _is_active_blacklist(r) else "RESOLVED")
        + " | " + " | ".join(p for p in [
            field(r, "Status") or "Blacklist",
            _source_agency(r),
            field(r, "Reason"),
            (field(r, "Date Issued", "Issued Date")
             if field(r, "Date Issued", "Issued Date").lower() != "tbd" else ""),
            (f"appeal: {field(r, 'Appeal Status')}"
             if field(r, "Appeal Status") else ""),
            (f"by {_attribute_issuer(field(r, 'Administrator', 'Issued By'), r)}"
             if _attribute_issuer(field(r, "Administrator", "Issued By"), r) else ""),
        ] if p)
        for r in ov["blacklists"]
    ], "BLACKLIST")

    add("WARRANTS", [
        ("EXPIRED " if is_expired(r) else "ACTIVE  ")
        + (field(r, "Offenses") or "—")
        + (f" | case {field(r, 'Case Number')}" if field(r, "Case Number") else "")
        for r in ov["warrants"]
    ], "WARRANTS")

    add("TRESPASS", [
        ("EXPIRED " if is_expired(r) else "ACTIVE  ")
        + " | ".join(p for p in [
            field(r, "Type", "Trespass Type") or "Trespass",
            field(r, "Property"),
            (f"ends {field(r, 'Expiration Date', 'Trespass End Date')}"
             if field(r, "Expiration Date", "Trespass End Date") else ""),
        ] if p)
        for r in ov["trespass"]
    ], "TRESPASS")

    add("AWARDS", [
        " | ".join(p for p in [
            field(r, "Award") or "Award",
            (field(r, "Date Issued") if field(r, "Date Issued") else ""),
        ] if p)
        for r in ov["awards"]
    ], "AWARDS")

    add("FORMER ROLES", [
        _status_ascii(field(r, "Status")).ljust(7)
        + " | ".join(p for p in [
            field(r, "Agency") or field(r, "Division") or field(r, "Job Type"),
            field(r, "Rank") or field(r, "Title"),
            field(r, "Status"),
            field(r, "Date"),
        ] if p)
        for r in ov["former_roles"]
    ], "FORMER ROLES")

    L.append("")
    L.append(rule("="))
    L.append(f"  Generated {NOW_NAIVE():%Y-%m-%d %H:%M} UTC  ·  v{APP_VERSION}")
    return "\n".join(L)

async def send_plain(interaction: discord.Interaction, ov):
    body = build_plain(ov)
    CH = 1900 - 8
    chunks, cur = [], ""
    for ln in body.split("\n"):
        while len(ln) > CH:
            head, ln = ln[:CH], ln[CH:]
            if cur:
                chunks.append(cur); cur = ""
            chunks.append(head)
        if len(cur) + len(ln) + 1 > CH:
            if cur:
                chunks.append(cur)
            cur = ln
        else:
            cur = (cur + "\n" + ln) if cur else ln
    if cur:
        chunks.append(cur)
    for c in chunks:
        await interaction.followup.send(f"```\n{c}\n```")
    srcs = _source_lines(ov)
    if srcs:
        await interaction.followup.send("**Sources**\n" + "\n".join(srcs[:15]))

# ============================================================
# PAGINATION
# ============================================================
class LookupView(discord.ui.View):
    def __init__(self, pages, author_id: int):
        super().__init__(timeout=300)
        self.pages = pages
        self.idx = 0
        self.author_id = author_id
        self._sync()

    def _sync(self):
        self.idx = max(0, min(self.idx, len(self.pages) - 1))
        self.prev.disabled = self.idx == 0
        self.next.disabled = self.idx >= len(self.pages) - 1
        self.counter.label = f"{self.idx + 1} / {len(self.pages)}"

    async def interaction_check(self, itx: discord.Interaction) -> bool:
        if itx.user.id != self.author_id:
            await itx.response.send_message("Not your lookup.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            await self.message.edit(view=self)
        except Exception:
            pass

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, row=0)
    async def prev(self, itx, _):
        self.idx = max(0, self.idx - 1); self._sync()
        await itx.response.edit_message(embed=self.pages[self.idx][1], view=self)

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.secondary,
                       disabled=True, row=0)
    async def counter(self, itx, _): pass

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, row=0)
    async def next(self, itx, _):
        self.idx = min(len(self.pages) - 1, self.idx + 1); self._sync()
        await itx.response.edit_message(embed=self.pages[self.idx][1], view=self)

# ============================================================
# DISCORD CLIENT
# ============================================================
class LookupBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.db: Database | None = None
        self.last_status: dict[str, str] = {}
        self._reload_lock = asyncio.Lock()

    async def setup_hook(self):
        self.db, self.last_status = await build_database()
        synced = await self.tree.sync()
        log.info("commands synced globally: %s",
                 ", ".join(f"/{c.name}" for c in synced))

    async def reload_db(self, *, clear_disk_cache: bool = False):
        async with self._reload_lock:
            if clear_disk_cache:
                for p in CACHE_DIR.glob("*.json"):
                    try:
                        p.unlink()
                    except Exception:
                        pass
            new_db, status = await build_database()
            self.db = new_db
            self.last_status = status
            return status

client = LookupBot()

def _failed_source_count():
    return sum(1 for v in client.last_status.values() if not v.startswith("ok"))

# ---------- /lookup ----------
@client.tree.command(name="lookup",
                     description="Look up a Concord username across every database")
@app_commands.checks.cooldown(3, 30, key=lambda i: i.user.id)
@app_commands.describe(username="The username to look up",
                       output="embed, png, or text")
@app_commands.choices(output=[
    app_commands.Choice(name="Embed (paginated)", value="embed"),
    app_commands.Choice(name="PNG dashboard",     value="png"),
    app_commands.Choice(name="Plain text",        value="text"),
])
async def lookup(interaction: discord.Interaction,
                 username: str,
                 output: app_commands.Choice[str] = None):
    await interaction.response.defer(thinking=True)
    db = interaction.client.db
    if db is None:
        await interaction.followup.send("Database is still loading, try again in a moment.")
        return

    ov = build_overview(username, db)
    failed = _failed_source_count()
    total_src = len(interaction.client.last_status)

    if ov["total_records"] == 0:
        near = get_close_matches(username.lower(), list(db.subjects),
                                 n=3, cutoff=CLOSE_MATCH_CUTOFF)
        if near:
            lines = []
            for s in near:
                rows = db.get(s)
                src0 = rows[0]["source"] if rows else "?"
                lines.append(f"• `{s}` — {len(rows)} record(s) — top source: {src0}")
            body = "Did you mean:\n" + "\n".join(lines)
        else:
            body = f"❌ No records for `{_esc(username)}`."
        if failed:
            body += f"\n\n⚠ {failed}/{total_src} sources failed to load — try `/refresh`."
        await interaction.followup.send(body)
        return

    mode = output.value if output else "embed"

    if mode == "png":
        buf = await asyncio.to_thread(build_png, ov)
        fname = f"database_lookup_{re.sub(r'[^A-Za-z0-9_-]', '_', username)}.png"
        await interaction.followup.send(file=discord.File(buf, fname))
    elif mode == "text":
        await send_plain(interaction, ov)
        if failed:
            await interaction.followup.send(
                f"⚠ {failed}/{total_src} sources failed to load.", ephemeral=True)
    else:
        pages = paginate(ov, failed_sources=failed, total_sources=total_src)
        view = LookupView(pages, interaction.user.id) if len(pages) > 1 else None
        await interaction.followup.send(embed=pages[0][1], view=view)

@lookup.autocomplete("username")
async def lookup_username_ac(interaction: discord.Interaction, current: str):
    db = interaction.client.db
    if db is None:
        return []
    cur = current.lower()
    matches = [s for s in db.subjects if cur in s.lower()][:25]
    return [app_commands.Choice(name=m, value=m) for m in matches]

@lookup.error
async def lookup_error(interaction: discord.Interaction,
                       error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        msg = f"Slow down — retry in {error.retry_after:.1f}s"
    else:
        log.exception("lookup error")
        msg = "⚠ Something went wrong. Try again or contact an admin."
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)

# ---------- /refresh ----------
@client.tree.command(name="refresh",
                     description="Reload all sources (also clears disk cache)")
@app_commands.default_permissions(manage_guild=True)
async def refresh(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    status = await interaction.client.reload_db(clear_disk_cache=True)

    ok   = [k for k, v in status.items() if v.startswith("ok")]
    errs = [(k, v) for k, v in status.items() if not v.startswith("ok")]
    lines = [f"✅ Reloaded — {len(interaction.client.db.records)} records across "
             f"{len(ok)}/{len(status)} sources."]
    if errs:
        lines.append("")
        lines.append("**Errors:**")
        for k, v in errs[:8]:
            lines.append(f"• `{k}` → {v}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)

# ---------- /stats ----------
@client.tree.command(name="stats",
                     description="Show database stats")
@app_commands.default_permissions(manage_guild=True)
async def stats(interaction: discord.Interaction):
    db = interaction.client.db
    if db is None:
        await interaction.response.send_message("DB not loaded yet.", ephemeral=True)
        return
    cats = defaultdict(int)
    for r in db.records:
        cats[r["cat"]] += 1
    body = "\n".join(f"`{k}`: {v}" for k, v in sorted(cats.items()))
    failed = _failed_source_count()
    total_src = len(interaction.client.last_status)
    e = discord.Embed(title="📊  Database stats",
                      description=(f"**Records:** {len(db.records)}\n"
                                   f"**Subjects:** {len(db.subjects)}\n"
                                   f"**Sources OK:** {total_src - failed}/{total_src}\n\n"
                                   f"**By category**\n{body}"),
                      color=EMBED_COLOR["Overview"],
                      timestamp=NOW_AWARE())
    e.set_footer(text=f"loaded {int(time.time() - db.loaded_at)}s ago · v{APP_VERSION}")
    await interaction.response.send_message(embed=e, ephemeral=True)

# ============================================================
# MAIN
# ============================================================
def main():
    if not DISCORD_TOKEN:
        print("ERROR: set DISCORD_TOKEN env var first.")
        return
    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    main()