"""
Create the pull_registry table in Supabase.
Tries: Management API > Direct DB > prints manual SQL.
"""
import os
import sys
import requests
from urllib.parse import urlparse, unquote
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://reiacekmluvuguqfswac.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJlaWFjZWttbHV2dWd1cWZzd2FjIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MDAxMTE3NywiZXhwIjoyMDg1NTg3MTc3fQ.dAHUSTH5XhAS6WAGFA1YyqBcIFzjGCWWwsRj1jH8ruo")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS public.pull_registry (
    id              uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    intercom_id     text NOT NULL UNIQUE,
    title           text NOT NULL DEFAULT '',
    description     text DEFAULT '',
    state           text DEFAULT 'published',
    url             text DEFAULT '',
    source_updated_at timestamptz,
    pulled_at       timestamptz,
    pull_status     text DEFAULT NULL,
    pull_error      text DEFAULT '',
    content_hash    text DEFAULT '',
    body_html       text DEFAULT '',
    author_id       text DEFAULT '',
    collection_id   text DEFAULT '',
    collection_name text DEFAULT '',
    created_at      timestamptz DEFAULT now(),
    updated_at      timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pull_registry_intercom_id ON pull_registry(intercom_id);
CREATE INDEX IF NOT EXISTS idx_pull_registry_pull_status ON pull_registry(pull_status);
"""

STATEMENTS = [s.strip() for s in SCHEMA_SQL.strip().split(";") if s.strip()]


def check_table_exists():
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    resp = requests.get(
        f"{SUPABASE_URL.rstrip('/')}/rest/v1/pull_registry?select=id&limit=1",
        headers=headers,
        timeout=15,
    )
    return resp.status_code == 200


def create_via_db():
    db_url = os.getenv("SUPABASE_DB_URL", "").strip()
    if not db_url:
        return False
    try:
        from pg8000.native import Connection
    except ImportError:
        print("pg8000 not installed")
        return False
    try:
        u = urlparse(db_url)
        conn = Connection(
            user=unquote(u.username) if u.username else "postgres",
            password=unquote(u.password) if u.password else "",
            host=u.hostname or "localhost",
            port=u.port or 5432,
            database=(u.path or "/postgres").lstrip("/") or "postgres",
        )
        for stmt in STATEMENTS:
            conn.run(stmt)
        conn.close()
        print("pull_registry table created via direct DB connection.")
        return True
    except Exception as e:
        print(f"DB connection error: {e}")
        return False


def create_via_management_api():
    ref = SUPABASE_URL.rstrip("/").split("//")[-1].replace(".supabase.co", "")
    pat = os.getenv("SUPABASE_PAT", "").strip() or os.getenv("SUPABASE_ACCESS_TOKEN", "").strip()
    if not pat:
        return False
    api_url = f"https://api.supabase.com/v1/projects/{ref}/database/query"
    headers = {"Authorization": f"Bearer {pat}", "Content-Type": "application/json"}
    try:
        r = requests.post(api_url, json={"query": SCHEMA_SQL.strip(), "read_only": False}, headers=headers, timeout=30)
        if r.status_code in (200, 201):
            print("pull_registry table created via Management API.")
            return True
        return False
    except Exception:
        return False


def main():
    if check_table_exists():
        print("pull_registry table already exists.")
        return 0

    if create_via_management_api():
        return 0

    if create_via_db():
        return 0

    print("\n=== MANUAL STEP REQUIRED ===")
    print("Run this SQL in Supabase Dashboard > SQL Editor > New Query:\n")
    print(SCHEMA_SQL)
    print("\nThen re-run this script to verify.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
