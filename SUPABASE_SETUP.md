# Supabase setup (backend data storage)

## 1. Create the table once

**Option A – Script (if you have the DB connection string)**  
Add `SUPABASE_DB_URL` to `.env` (from Supabase Dashboard > Project Settings > Database > Connection string URI), then run:

```bash
python create_supabase_table.py
```

**Option B – Manual in Dashboard**  
1. Open your Supabase project: **https://reiacekmluvuguqfswac.supabase.co**  
2. Go to **SQL Editor** > New query.  
3. Run the SQL in **`supabase_schema.sql`** (copy from that file or from below).

```sql
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
```

4. Click **Run**. After this, the app can sync and list articles.

## 2. Config

The app uses these (already set in `config.py`):

- **SUPABASE_URL**: `https://reiacekmluvuguqfswac.supabase.co`
- **SUPABASE_SERVICE_KEY**: your service_role key

To override, set env vars: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`.

## 3. Test sync from command line

```bash
cd intercom-translator
set INTERCOM_ACCESS_TOKEN=your_intercom_token
python -c "
from sync_service import sync_collection_from_intercom
r = sync_collection_from_intercom('About FundedNext')
print(r)
"
```

## 4. From the web UI

1. Open **http://localhost:5000** (with the app running).
2. In the **Dashboard** section, click **Sync About FundedNext from Intercom**.
3. Click **Refresh list** to see article names from Supabase.
