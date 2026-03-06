"""
Run supabase_article_translations.sql once to create article_translations table.
Uses SUPABASE_DB_URL (direct Postgres) if set; otherwise prints instructions for SQL Editor.
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote
from dotenv import load_dotenv

load_dotenv()

MIGRATION_SQL = (Path(__file__).parent / "supabase_article_translations.sql").read_text()


def _parse_db_url(db_url: str) -> dict:
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
    db_url = os.getenv("SUPABASE_DB_URL", "").strip()
    if not db_url:
        print("SUPABASE_DB_URL is not set. Run the migration manually:")
        print("  1. Open Supabase Dashboard > SQL Editor")
        print("  2. Paste contents of supabase_article_translations.sql")
        print("  3. Click Run")
        return 1
    try:
        from pg8000.native import Connection
    except ImportError:
        print("Installing pg8000...")
        os.system(f'"{sys.executable}" -m pip install pg8000 -q')
        try:
            from pg8000.native import Connection
        except ImportError:
            print("Install pg8000: python -m pip install pg8000")
            return 1
    try:
        kwargs = _parse_db_url(db_url)
        conn = Connection(**kwargs)
        for stmt in MIGRATION_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt and not stmt.startswith("--"):
                conn.run(stmt)
        conn.close()
        print("article_translations table created (or already exists).")
        return 0
    except Exception as e:
        print("Error:", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
