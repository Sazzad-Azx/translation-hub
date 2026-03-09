"""
Automation Service – manages scheduled automation tasks.

Stores settings in Supabase `automation_settings` table.
Currently supports:
  - auto_sync_pull: Automatically "Sync Source List" every 24h at ~00:00 UTC
"""
import os
import requests
from datetime import datetime, timezone
from typing import Dict, Optional

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY

REST_BASE = f"{SUPABASE_URL.rstrip('/')}/rest/v1" if SUPABASE_URL else ""
TABLE = "automation_settings"

SETUP_SQL = """
CREATE TABLE IF NOT EXISTS public.automation_settings (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    key             text NOT NULL UNIQUE,
    enabled         boolean NOT NULL DEFAULT false,
    last_run_at     timestamptz,
    last_run_status text DEFAULT '',
    last_run_message text DEFAULT '',
    next_run_at     timestamptz,
    created_at      timestamptz DEFAULT now(),
    updated_at      timestamptz DEFAULT now()
);
""".strip()

# ─── Helpers ──────────────────────────────────────────────────────

def _headers(prefer: str = "") -> Dict[str, str]:
    if not SUPABASE_SERVICE_KEY:
        raise ValueError("SUPABASE_SERVICE_KEY must be set")
    h = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def table_exists() -> bool:
    """Check if the automation_settings table exists in Supabase."""
    if not REST_BASE:
        return False
    try:
        r = requests.get(
            f"{REST_BASE}/{TABLE}?select=id&limit=1",
            headers=_headers(),
            timeout=10,
        )
        return r.status_code == 200
    except Exception:
        return False


def _ensure_row(key: str) -> Dict:
    """Get or create a settings row for the given key."""
    try:
        r = requests.get(
            f"{REST_BASE}/{TABLE}?key=eq.{key}&select=*",
            headers=_headers(),
            timeout=10,
        )
        if r.status_code == 200 and r.json():
            return r.json()[0]
    except Exception:
        pass

    # Row doesn't exist – create it
    row = {
        "key": key,
        "enabled": False,
        "last_run_at": None,
        "last_run_status": "",
        "last_run_message": "",
        "next_run_at": None,
    }
    try:
        r = requests.post(
            f"{REST_BASE}/{TABLE}",
            headers=_headers(prefer="return=representation"),
            json=row,
            timeout=10,
        )
        if r.status_code in (200, 201) and r.json():
            data = r.json()
            return data[0] if isinstance(data, list) else data
    except Exception:
        pass
    return row


def _compute_next_run() -> str:
    """Compute the next UTC midnight as ISO string."""
    now = datetime.now(timezone.utc)
    # Next midnight = today + 1 day at 00:00
    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if tomorrow <= now:
        from datetime import timedelta
        tomorrow += timedelta(days=1)
    return tomorrow.isoformat()


# ─── Public API ───────────────────────────────────────────────────

def get_settings(key: str = "auto_sync_pull") -> Dict:
    """Get automation settings for a given key."""
    if not table_exists():
        return {
            "key": key,
            "enabled": False,
            "table_exists": False,
            "last_run_at": None,
            "last_run_status": "",
            "last_run_message": "",
            "next_run_at": None,
        }
    row = _ensure_row(key)
    row["table_exists"] = True
    return row


def set_enabled(key: str, enabled: bool) -> Dict:
    """Toggle automation on or off."""
    if not table_exists():
        return {"success": False, "error": "Table does not exist"}

    _ensure_row(key)  # Make sure row exists

    update = {
        "enabled": enabled,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if enabled:
        update["next_run_at"] = _compute_next_run()
    else:
        update["next_run_at"] = None

    try:
        r = requests.patch(
            f"{REST_BASE}/{TABLE}?key=eq.{key}",
            headers=_headers(prefer="return=representation"),
            json=update,
            timeout=10,
        )
        if r.status_code in (200, 204):
            data = r.json() if r.text else []
            row = data[0] if isinstance(data, list) and data else {}
            return {"success": True, "settings": row}
        return {"success": False, "error": f"Update failed: {r.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def record_run(key: str, status: str, message: str) -> None:
    """Record the result of an automation run."""
    now = datetime.now(timezone.utc).isoformat()
    update = {
        "last_run_at": now,
        "last_run_status": status,
        "last_run_message": message,
        "next_run_at": _compute_next_run(),
        "updated_at": now,
    }
    try:
        requests.patch(
            f"{REST_BASE}/{TABLE}?key=eq.{key}",
            headers=_headers(),
            json=update,
            timeout=10,
        )
    except Exception as e:
        print(f"[automation] record_run error: {e}", flush=True)


def get_logs(key: str = "auto_sync_pull", limit: int = 20) -> list:
    """
    Get recent automation run logs.
    For now, we store the last run in the settings row.
    Returns a list with a single entry (expandable in the future).
    """
    row = get_settings(key)
    if row.get("last_run_at"):
        return [{
            "key": key,
            "ran_at": row["last_run_at"],
            "status": row.get("last_run_status", ""),
            "message": row.get("last_run_message", ""),
        }]
    return []


def run_auto_sync(intercom_client) -> Dict:
    """
    Execute the automatic sync (same as Pull > Sync Source List).
    Called by the cron endpoint.
    """
    from pull_service import sync_source_list, table_exists as pull_table_exists

    key = "auto_sync_pull"

    # Check if automation is enabled
    settings = get_settings(key)
    if not settings.get("enabled"):
        return {"success": False, "skipped": True, "reason": "Auto-sync is disabled"}

    # Check pull_registry table
    if not pull_table_exists():
        record_run(key, "error", "pull_registry table does not exist")
        return {"success": False, "error": "pull_registry table does not exist"}

    # Execute sync
    try:
        result = sync_source_list(intercom_client)
        synced = result.get("synced", 0)
        total = result.get("total", 0)
        message = f"Synced {synced} articles (total: {total})"
        record_run(key, "success", message)
        return {"success": True, "synced": synced, "total": total, "message": message}
    except Exception as e:
        error_msg = str(e)
        record_run(key, "error", error_msg)
        return {"success": False, "error": error_msg}


def auto_create_table() -> Dict:
    """Auto-create the automation_settings table."""
    if table_exists():
        return {"success": True, "message": "Table already exists."}

    db_url = os.getenv("SUPABASE_DB_URL", "").strip()
    if db_url:
        try:
            from urllib.parse import urlparse, unquote
            from pg8000.native import Connection
            u = urlparse(db_url)
            conn = Connection(
                user=unquote(u.username) if u.username else "postgres",
                password=unquote(u.password) if u.password else "",
                host=u.hostname or "localhost",
                port=u.port or 5432,
                database=(u.path or "/postgres").lstrip("/") or "postgres",
            )
            for stmt in [s.strip() for s in SETUP_SQL.split(";") if s.strip()]:
                conn.run(stmt)
            conn.close()
            return {"success": True, "method": "pg8000"}
        except Exception as e:
            print(f"[automation] pg8000 error: {e}", flush=True)

    return {
        "success": False,
        "error": "Could not auto-create table. Please run the SQL manually.",
        "sql": SETUP_SQL,
    }
