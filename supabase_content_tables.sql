-- Run this in Supabase Dashboard: SQL Editor
-- Creates tables used by "Fetch from Intercom & store in Supabase" (intercom_content_items, intercom_content_versions).
-- Required columns: intercom_content_items must have id, workspace, project, external_id, external_type.

create extension if not exists "pgcrypto";

-- Main table: Intercom items (articles) stored by external_id (Intercom article id)
create table if not exists public.intercom_content_items (
  id uuid primary key default gen_random_uuid(),
  workspace text not null default 'default',
  project text not null default 'default',
  external_id text not null,
  external_type text not null default 'article',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists idx_intercom_content_items_external_id
  on public.intercom_content_items(external_id);

-- If your table already exists without external_id/external_type, add them:
-- alter table public.intercom_content_items add column if not exists external_id text;
-- alter table public.intercom_content_items add column if not exists external_type text default 'article';

-- Versions: one row per locale (title, body) per content item
create table if not exists public.intercom_content_versions (
  id uuid primary key default gen_random_uuid(),
  content_item_id uuid not null references public.intercom_content_items(id) on delete cascade,
  locale text not null default 'en',
  title text not null default '',
  body_raw text not null default '',
  body_normalized jsonb not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_intercom_content_versions_content_item_id
  on public.intercom_content_versions(content_item_id);
