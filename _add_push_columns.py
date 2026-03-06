"""Add pushed_at and push_error columns to article_translations via Supabase Management API."""
import requests
from config import SUPABASE_URL, SUPABASE_SERVICE_KEY

# Extract project ref from URL (e.g., https://reiacekmluvuguqfswac.supabase.co -> reiacekmluvuguqfswac)
project_ref = SUPABASE_URL.replace('https://', '').split('.')[0]
print(f'Project ref: {project_ref}')

# Try using the Supabase SQL API endpoint (management API style)
sql = """
ALTER TABLE public.article_translations ADD COLUMN IF NOT EXISTS pushed_at timestamptz DEFAULT NULL;
ALTER TABLE public.article_translations ADD COLUMN IF NOT EXISTS push_error text DEFAULT '';
"""

# Method: Use the database/query endpoint from the supabase management API
# This requires the service role key to work with the SQL query endpoint
base = SUPABASE_URL.rstrip('/')
h = {
    'apikey': SUPABASE_SERVICE_KEY,
    'Authorization': f'Bearer {SUPABASE_SERVICE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=minimal',
}

# Try the pgrest approach: create a simple function that does it
create_fn_sql = """
CREATE OR REPLACE FUNCTION add_push_columns()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  BEGIN
    ALTER TABLE public.article_translations ADD COLUMN pushed_at timestamptz DEFAULT NULL;
  EXCEPTION WHEN duplicate_column THEN
    NULL;
  END;
  BEGIN
    ALTER TABLE public.article_translations ADD COLUMN push_error text DEFAULT '';
  EXCEPTION WHEN duplicate_column THEN
    NULL;
  END;
END;
$$;
"""

# Can't run DDL through REST API without a function.
# Let's try a different approach: direct PostgreSQL connection if available.
import os
db_url = os.getenv('SUPABASE_DB_URL', '')
if db_url:
    print(f'Found SUPABASE_DB_URL, trying direct connection...')
    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("ALTER TABLE public.article_translations ADD COLUMN IF NOT EXISTS pushed_at timestamptz DEFAULT NULL")
        cur.execute("ALTER TABLE public.article_translations ADD COLUMN IF NOT EXISTS push_error text DEFAULT ''")
        cur.close()
        conn.close()
        print('SUCCESS via direct DB connection!')
    except ImportError:
        print('psycopg2 not installed. Trying psycopg2-binary...')
        import subprocess
        subprocess.run(['pip', 'install', 'psycopg2-binary'], check=True)
        import psycopg2
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("ALTER TABLE public.article_translations ADD COLUMN IF NOT EXISTS pushed_at timestamptz DEFAULT NULL")
        cur.execute("ALTER TABLE public.article_translations ADD COLUMN IF NOT EXISTS push_error text DEFAULT ''")
        cur.close()
        conn.close()
        print('SUCCESS via direct DB connection!')
    except Exception as e:
        print(f'Direct DB connection failed: {e}')
else:
    print('No SUPABASE_DB_URL set.')

# Alternative: use Supabase HTTP SQL endpoint (not REST)
print('\nTrying Supabase /pg endpoint...')
for stmt in [
    "ALTER TABLE public.article_translations ADD COLUMN IF NOT EXISTS pushed_at timestamptz DEFAULT NULL",
    "ALTER TABLE public.article_translations ADD COLUMN IF NOT EXISTS push_error text DEFAULT ''"
]:
    resp = requests.post(
        f'{base}/rest/v1/rpc/',
        headers=h,
        json={'query': stmt},
        timeout=15,
    )
    print(f'  {resp.status_code}: {resp.text[:100] if resp.text else "OK"}')

# Final verification
resp = requests.get(
    f'{base}/rest/v1/article_translations?select=pushed_at,push_error&limit=1',
    headers=h,
    timeout=10,
)
print(f'\nFinal verification: status {resp.status_code}')
if resp.status_code == 200:
    print('SUCCESS - columns exist!')
else:
    print()
    print('=' * 60)
    print('MANUAL ACTION REQUIRED')
    print('=' * 60)
    print('Please go to your Supabase Dashboard > SQL Editor and run:')
    print()
    print("ALTER TABLE public.article_translations ADD COLUMN IF NOT EXISTS pushed_at timestamptz DEFAULT NULL;")
    print("ALTER TABLE public.article_translations ADD COLUMN IF NOT EXISTS push_error text DEFAULT '';")
    print()
    print('After running, the Push section will be fully operational.')
