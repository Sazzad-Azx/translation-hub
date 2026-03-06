"""Quick check/add pushed_at and push_error columns to article_translations."""
import requests
from config import SUPABASE_URL, SUPABASE_SERVICE_KEY

rest_base = f'{SUPABASE_URL.rstrip("/")}/rest/v1'
h = {
    'apikey': SUPABASE_SERVICE_KEY,
    'Authorization': f'Bearer {SUPABASE_SERVICE_KEY}',
    'Content-Type': 'application/json',
}

# Check if pushed_at column exists
resp = requests.get(f'{rest_base}/article_translations?select=pushed_at&limit=1', headers=h, timeout=10)
print(f'Check pushed_at column: status {resp.status_code}')
if resp.status_code == 200:
    print('Columns already exist!')
else:
    print('Columns do NOT exist yet.')
    print('Please run this SQL in Supabase SQL Editor:')
    print()
    print('ALTER TABLE public.article_translations ADD COLUMN IF NOT EXISTS pushed_at timestamptz DEFAULT NULL;')
    print("ALTER TABLE public.article_translations ADD COLUMN IF NOT EXISTS push_error text DEFAULT '';")
