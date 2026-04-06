-- Table to cache daily OpenAI API costs per key
-- Run this in Supabase SQL Editor: https://supabase.com/dashboard/project/reiacekmluvuguqfswac/sql

CREATE TABLE IF NOT EXISTS public.daily_api_costs (
  date DATE NOT NULL,
  key_id TEXT NOT NULL,
  cost DOUBLE PRECISION NOT NULL DEFAULT 0,
  requests INTEGER NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, key_id)
);

CREATE INDEX IF NOT EXISTS idx_daily_api_costs_date ON public.daily_api_costs(date);
