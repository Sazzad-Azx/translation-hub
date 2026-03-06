-- Run this in Supabase Dashboard: SQL Editor
-- Project: translation on supabase
-- Creates the table that mirrors Intercom articles for the dashboard.

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

-- Allow service role to read/write (default for service_role key)
-- No extra RLS needed if using service_role; for anon key you would add RLS policies.
