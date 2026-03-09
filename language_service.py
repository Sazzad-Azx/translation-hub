"""
Language management service.
Stores active target languages in Supabase `target_languages` table.
Falls back to a local JSON file when the table doesn't exist.
Mutates config.TARGET_LANGUAGES so all other services pick up changes.
"""
import os
import json
import requests
from typing import Dict, List
from pathlib import Path

from config import (
    SUPABASE_URL,
    SUPABASE_SERVICE_KEY,
    ALL_AVAILABLE_LANGUAGES,
    DEFAULT_TARGET_LANGUAGES,
    TARGET_LANGUAGES,
)

TABLE = "target_languages"
REST_BASE = f"{SUPABASE_URL.rstrip('/')}/rest/v1" if SUPABASE_URL else ""

# Local JSON fallback – stored next to this file
_LOCAL_FILE = Path(__file__).parent / "active_languages.json"


def _headers(prefer: str = "return=representation") -> Dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


# ── Table helpers ────────────────────────────────────────────────────────

def get_table_sql() -> str:
    return """
CREATE TABLE IF NOT EXISTS target_languages (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _supabase_table_exists() -> bool:
    if not REST_BASE:
        return False
    try:
        r = requests.get(
            f"{REST_BASE}/{TABLE}?select=code&limit=1",
            headers=_headers(),
            timeout=10,
        )
        return r.status_code == 200
    except Exception:
        return False


def table_exists() -> bool:
    return _supabase_table_exists()


def auto_create_table() -> dict:
    sql = get_table_sql()
    db_url = os.getenv("SUPABASE_DB_URL", "")
    if db_url:
        try:
            import pg8000
            import urllib.parse as urlparse
            parsed = urlparse.urlparse(db_url)
            conn = pg8000.connect(
                host=parsed.hostname,
                port=parsed.port or 5432,
                database=parsed.path.lstrip("/"),
                user=parsed.username,
                password=parsed.password,
                ssl_context=True,
            )
            cur = conn.cursor()
            cur.execute(sql)
            conn.commit()
            cur.close()
            conn.close()
            return {"success": True, "method": "pg8000"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    return {"success": False, "error": "SUPABASE_DB_URL not set", "sql": sql}


# ── Local JSON fallback ─────────────────────────────────────────────────

def _load_local() -> Dict[str, str]:
    """Load active languages from local JSON file."""
    if _LOCAL_FILE.exists():
        try:
            data = json.loads(_LOCAL_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                return data
        except Exception:
            pass
    return dict(DEFAULT_TARGET_LANGUAGES)


def _save_local(langs: Dict[str, str]) -> None:
    """Persist active languages to local JSON file."""
    try:
        _LOCAL_FILE.write_text(json.dumps(langs, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# ── Supabase CRUD ────────────────────────────────────────────────────────

def _seed_defaults_supabase() -> None:
    rows = [{"code": c, "name": n, "is_active": True} for c, n in DEFAULT_TARGET_LANGUAGES.items()]
    if not rows:
        return
    h = _headers("return=minimal,resolution=merge-duplicates")
    requests.post(f"{REST_BASE}/{TABLE}", json=rows, headers=h, timeout=15)


def _load_from_supabase() -> Dict[str, str] | None:
    """Try loading from Supabase. Returns None if table doesn't exist."""
    if not REST_BASE:
        return None
    try:
        h = dict(_headers())
        h.pop("Prefer", None)
        r = requests.get(
            f"{REST_BASE}/{TABLE}",
            headers=h,
            params={"select": "code,name", "is_active": "eq.true", "order": "name.asc"},
            timeout=15,
        )
        if r.status_code == 404 or r.status_code == 406:
            return None  # table doesn't exist
        if r.ok:
            rows = r.json()
            if not rows:
                _seed_defaults_supabase()
                return dict(DEFAULT_TARGET_LANGUAGES)
            return {row["code"]: row["name"] for row in rows}
    except Exception:
        pass
    return None


# ── Public API ───────────────────────────────────────────────────────────

def _use_supabase() -> bool:
    """Check if we should use Supabase (table exists) or local fallback."""
    return _supabase_table_exists()


def load_active_languages() -> Dict[str, str]:
    """
    Fetch active languages (Supabase first, local JSON fallback).
    Updates config.TARGET_LANGUAGES in place.
    """
    # Try Supabase
    result = _load_from_supabase()
    if result is not None:
        TARGET_LANGUAGES.clear()
        TARGET_LANGUAGES.update(result)
        _save_local(result)  # keep local in sync
        return result

    # Fallback to local file
    result = _load_local()
    TARGET_LANGUAGES.clear()
    TARGET_LANGUAGES.update(result)
    return result


def add_languages(codes: List[str]) -> dict:
    """Add one or more languages."""
    added = []
    errors = []

    use_sb = _use_supabase()

    for code in codes:
        name = ALL_AVAILABLE_LANGUAGES.get(code)
        if not name:
            errors.append(f"Unknown language code: {code}")
            continue

        if use_sb:
            # Supabase upsert
            row = {"code": code, "name": name, "is_active": True}
            h = _headers("return=representation,resolution=merge-duplicates")
            try:
                r = requests.post(f"{REST_BASE}/{TABLE}", json=row, headers=h, timeout=10)
                if r.ok:
                    added.append(code)
                else:
                    errors.append(f"{code}: {r.text}")
            except Exception as e:
                errors.append(f"{code}: {e}")
        else:
            # Local fallback
            added.append(code)

    if not use_sb and added:
        # Update local file
        current = _load_local()
        for code in added:
            current[code] = ALL_AVAILABLE_LANGUAGES[code]
        _save_local(current)

    # Refresh in-memory dict
    load_active_languages()
    return {"success": True, "added": added, "errors": errors}


def remove_language(code: str) -> dict:
    """Remove (deactivate) a language."""
    use_sb = _use_supabase()

    if use_sb:
        try:
            h = _headers("return=minimal")
            r = requests.patch(
                f"{REST_BASE}/{TABLE}?code=eq.{code}",
                json={"is_active": False},
                headers=h,
                timeout=10,
            )
            if r.status_code not in (200, 204):
                return {"success": False, "error": r.text}
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        # Local fallback
        current = _load_local()
        current.pop(code, None)
        _save_local(current)

    load_active_languages()
    return {"success": True}
