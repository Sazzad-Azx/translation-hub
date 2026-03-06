# Test run: Sync About FundedNext articles

## What was done

1. **Sync behavior**
   - When you run sync for "About FundedNext", the app first looks for a collection with that name in Intercom.
   - If **no such collection exists** (e.g. your Intercom has 0 collections), it **falls back to syncing all articles** from Intercom into Supabase.
   - So the test run still copies whatever articles you have into the database.

2. **Current Intercom state (from earlier checks)**
   - Help Center returned **0 collections**.
   - There is **1 article** ("Your first public article").
   - So with the fallback, the test run will sync that 1 article to Supabase.

## What you need to do

### 1. Create the table in Supabase (once)

1. Open: **https://reiacekmluvuguqfswac.supabase.co**
2. Go to **SQL Editor**.
3. Run the SQL in **`supabase_schema.sql`** (creates `intercom_articles` table).

### 2. Install the Supabase Python client

In a terminal (from the `intercom-translator` folder):

```bash
python -m pip install supabase
```

If you get permission errors, try:

```bash
python -m pip install --user supabase
```

Or run the terminal as Administrator and run `python -m pip install supabase` again.

### 3. Run the test sync

From the `intercom-translator` folder:

**PowerShell:**

```powershell
$env:INTERCOM_ACCESS_TOKEN="your_intercom_access_token_here"
$env:SUPABASE_URL="https://reiacekmluvuguqfswac.supabase.co"
$env:SUPABASE_SERVICE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJlaWFjZWttbHV2dWd1cWZzd2FjIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MDAxMTE3NywiZXhwIjoyMDg1NTg3MTc3fQ.dAHUSTH5XhAS6WAGFA1YyqBcIFzjGCWWwsRj1jH8ruo"
python run_sync_test.py
```

**Or** use a `.env` file with those variables and run:

```bash
python run_sync_test.py
```

## Expected result

- **If the Supabase table exists and `supabase` is installed:**  
  The script prints a result like:  
  `Synced 1 article(s) to Supabase` and lists the article(s).  
  (With the current Intercom data, that will be the one article, under the fallback "all articles".)

- **When you later add an "About FundedNext" collection in Intercom** and put articles in it, the same command will sync only that collection’s articles.

## Optional: list collections / articles

- **List Intercom collections:**  
  `python list_collections.py`

- **List Intercom articles (raw structure):**  
  `python list_articles_raw.py`
