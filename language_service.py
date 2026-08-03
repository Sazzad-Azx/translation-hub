"""
Language management service.
Stores active target languages in Supabase `automation_settings` table
under the key 'active_languages' (as JSON in last_run_message).
Falls back to a local JSON file for local development.
Mutates config.TARGET_LANGUAGES so all other services pick up changes.
"""
import os
import json
import requests
from typing import Dict, List, Optional
from pathlib import Path

import product_context
from config import (
    ALL_AVAILABLE_LANGUAGES,
    DEFAULT_TARGET_LANGUAGES,
    TARGET_LANGUAGES,
)

TABLE = "automation_settings"
LANG_KEY = "active_languages"
REST_BASE = product_context.LazyStr(product_context.supabase_rest_base)

# Local JSON fallback – stored next to this file (for local dev)
_LOCAL_FILE = Path(__file__).parent / "active_languages.json"


def _headers(prefer: str = "return=representation") -> Dict[str, str]:
    return product_context.supabase_headers({"Prefer": prefer})


# ── Kept for backward compat with app.py routes ─────────────────────────
def get_table_sql() -> str:
    return "-- No separate table needed. Uses automation_settings with key='active_languages'."

def table_exists() -> bool:
    return True  # We use automation_settings which already exists

def auto_create_table() -> dict:
    return {"success": True, "message": "Uses existing automation_settings table."}


# ── Supabase helpers (automation_settings row) ───────────────────────────

def _read_supabase() -> Optional[Dict[str, str]]:
    """Read the active_languages row from automation_settings."""
    if not REST_BASE:
        return None
    try:
        h = dict(_headers())
        h.pop("Prefer", None)
        r = requests.get(
            f"{REST_BASE}/{TABLE}",
            headers=h,
            params={"select": "last_run_message", "key": f"eq.{LANG_KEY}"},
            timeout=15,
        )
        if not r.ok:
            return None
        rows = r.json()
        if not rows:
            return None  # Row doesn't exist yet
        raw = rows[0].get("last_run_message", "")
        if not raw:
            return None
        data = json.loads(raw)
        if isinstance(data, dict) and data:
            return data
    except Exception:
        pass
    return None


def _write_supabase(langs: Dict[str, str]) -> bool:
    """Write the active_languages row in automation_settings (PATCH if exists, POST if not)."""
    if not REST_BASE:
        return False
    msg = json.dumps(langs, ensure_ascii=False)
    try:
        # Try PATCH first (update existing row)
        h = _headers("return=minimal")
        r = requests.patch(
            f"{REST_BASE}/{TABLE}?key=eq.{LANG_KEY}",
            json={"last_run_message": msg},
            headers=h,
            timeout=15,
        )
        if r.status_code in (200, 204):
            # PATCH returns 200/204 even if 0 rows matched — check via Content-Range or just verify
            # If the row existed, we're done. If not, fall through to POST.
            # Quick check: read it back
            existing = _read_supabase()
            if existing is not None:
                return True

        # Row doesn't exist — INSERT
        payload = {
            "key": LANG_KEY,
            "enabled": True,
            "last_run_message": msg,
        }
        h2 = _headers("return=minimal")
        r2 = requests.post(f"{REST_BASE}/{TABLE}", json=payload, headers=h2, timeout=15)
        return r2.status_code in (200, 201, 204)
    except Exception:
        return False


# ── Local JSON fallback (for local dev) ──────────────────────────────────

def _load_local() -> Dict[str, str]:
    if _LOCAL_FILE.exists():
        try:
            data = json.loads(_LOCAL_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                return data
        except Exception:
            pass
    return dict(DEFAULT_TARGET_LANGUAGES)


def _save_local(langs: Dict[str, str]) -> None:
    try:
        _LOCAL_FILE.write_text(json.dumps(langs, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# ── Public API ───────────────────────────────────────────────────────────

def load_active_languages() -> Dict[str, str]:
    """
    Fetch active languages. Tries Supabase first, then local file.
    Seeds defaults if nothing stored yet.
    Updates config.TARGET_LANGUAGES in place.
    """
    # Try Supabase
    result = _read_supabase()
    if result is not None:
        TARGET_LANGUAGES.clear()
        TARGET_LANGUAGES.update(result)
        _save_local(result)
        return result

    # No row in Supabase yet – try local file
    result = _load_local()

    # Seed to Supabase so future requests find it
    if REST_BASE:
        _write_supabase(result)

    TARGET_LANGUAGES.clear()
    TARGET_LANGUAGES.update(result)
    return result


def add_languages(codes: List[str]) -> dict:
    """Add one or more languages."""
    added = []
    errors = []

    # Load current
    current = _read_supabase()
    if current is None:
        current = _load_local()

    for code in codes:
        name = ALL_AVAILABLE_LANGUAGES.get(code)
        if not name:
            errors.append(f"Unknown language code: {code}")
            continue
        current[code] = name
        added.append(code)

    # Persist
    if not _write_supabase(current):
        _save_local(current)

    # Refresh in-memory
    TARGET_LANGUAGES.clear()
    TARGET_LANGUAGES.update(current)
    _save_local(current)

    return {"success": True, "added": added, "errors": errors}


def remove_language(code: str) -> dict:
    """Remove a language."""
    current = _read_supabase()
    if current is None:
        current = _load_local()

    if code not in current:
        return {"success": False, "error": f"Language {code} not found"}

    del current[code]

    if not _write_supabase(current):
        _save_local(current)

    TARGET_LANGUAGES.clear()
    TARGET_LANGUAGES.update(current)
    _save_local(current)

    return {"success": True}
