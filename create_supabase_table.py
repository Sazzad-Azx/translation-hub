"""
Create the intercom_articles table in Supabase (Option A).
Uses either: (1) SUPABASE_DB_URL + pg8000, or (2) SUPABASE_PAT + Management API run SQL.
"""
import os
import sys
from urllib.parse import urlparse, unquote
from dotenv import load_dotenv
load_dotenv()

# SQL to create the table (same as supabase_schema.sql)
SCHEMA_SQL = """
create table if not exists public.intercom_articles (
  id uuid primary key default gen_random_uuid(),
  intercom_id text not null unique,
  title text not null,
  description text,
  body text,
  collection_id text,
  collection_name text,
  state text,
  synced_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_intercom_articles_intercom_id on public.intercom_articles(intercom_id);
create index if not exists idx_intercom_articles_collection_name on public.intercom_articles(collection_name);
"""

MANAGEMENT_API_BASE = "https://api.supabase.com/v1"


def _project_ref_from_url(url: str) -> str:
    """Extract project ref from SUPABASE_URL (e.g. https://xxx.supabase.co -> xxx)."""
    if not url:
        return ""
    u = urlparse(url if "://" in url else "https://" + url)
    host = (u.hostname or u.path or "").strip()
    if host.endswith(".supabase.co"):
        return host.replace(".supabase.co", "")
    return ""


def _create_table_via_management_api() -> bool:
    """Create table via Supabase Management API POST .../database/query. Uses SUPABASE_PAT or SUPABASE_SERVICE_KEY."""
    import requests
    url = (
        os.getenv("SUPABASE_URL", "").strip()
        or "https://reiacekmluvuguqfswac.supabase.co"
    )
    ref = _project_ref_from_url(url)
    if not ref:
        return False
    # Management API requires a Personal Access Token (not the project service_role key)
    pat = (
        os.getenv("SUPABASE_PAT", "").strip()
        or os.getenv("SUPABASE_ACCESS_TOKEN", "").strip()
    )
    if not pat:
        return False
    api_url = f"{MANAGEMENT_API_BASE}/projects/{ref}/database/query"
    headers = {"Authorization": f"Bearer {pat}", "Content-Type": "application/json"}
    # Management API may accept one statement; send create table and indexes in one query (separate statements)
    body = {"query": SCHEMA_SQL.strip(), "read_only": False}
    try:
        r = requests.post(api_url, json=body, headers=headers, timeout=30)
        if r.status_code in (200, 201):
            print("Table public.intercom_articles created (or already exists) via Management API.")
            return True
        # If endpoint returns 404/501 (beta), fall back to DB URL
        if r.status_code == 404 or (r.status_code == 403 and "partner" in (r.text or "").lower()):
            return False
        print(f"Management API returned {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:
        print(f"Management API error: {e}")
        return False


def _parse_db_url(db_url: str) -> dict:
    """Parse postgresql://user:pass@host:port/dbname into pg8000 kwargs."""
    u = urlparse(db_url)
    if u.scheme not in ("postgresql", "postgres"):
        raise ValueError("URL must be postgresql://...")
    host = u.hostname or "localhost"
    port = u.port or 5432
    database = (u.path or "/postgres").lstrip("/") or "postgres"
    user = unquote(u.username) if u.username else "postgres"
    password = unquote(u.password) if u.password else ""
    return {"user": user, "password": password, "host": host, "port": port, "database": database}


def main():
    # Option A1: Create via Management API (no DB password needed)
    if _create_table_via_management_api():
        return 0

    # Option A2: Create via direct DB connection (SUPABASE_DB_URL)
    db_url = os.getenv("SUPABASE_DB_URL", "").strip()
    if not db_url:
        print("SUPABASE_DB_URL and SUPABASE_PAT are not set.")
        print("Option A - Use DB connection: Add to .env: SUPABASE_DB_URL=\"postgresql://postgres.[ref]:[PASSWORD]@...\" (from Dashboard > Database > Connection string URI)")
        print("Option A - Or use PAT: Add to .env: SUPABASE_PAT=your_personal_access_token (from https://supabase.com/dashboard/account/tokens)")
        print("Option B - Run SQL manually: Supabase Dashboard > SQL Editor > New query, then run supabase_schema.sql")
        return 1
    try:
        from pg8000.native import Connection
    except ImportError:
        print("Install pg8000: python -m pip install pg8000")
        return 1
    try:
        kwargs = _parse_db_url(db_url)
        conn = Connection(**kwargs)
        # Run each statement (pg8000 may not run multi-statement in one call)
        for stmt in SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.run(stmt)
        conn.close()
        print("Table public.intercom_articles created (or already exists).")
        return 0
    except Exception as e:
        print("Error:", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
