# Intercom Translation Workflow - Web Page

## Web Page Link

When the server is running, open your browser and go to:

### **http://localhost:5000**

Or use:

### **http://127.0.0.1:5000**

---

## The page won't load unless the server is running

Follow these steps:

### Step 1: Open a terminal in the project folder

- Open Command Prompt or PowerShell
- Go to the `intercom-translator` folder, for example:
  ```
  cd C:\Users\NEXT\.cursor\intercom-translator
  ```

### Step 2: Set environment variables (if not using a .env file)

In PowerShell:
```powershell
$env:INTERCOM_ACCESS_TOKEN="your_intercom_access_token_here"
$env:OPENAI_API_KEY="your_openai_api_key_here"
$env:OPENAI_MODEL="gpt-4o"
```

### Step 3: Start the web server

```bash
python run_web.py
```

You should see something like:
```
 * Running on http://0.0.0.0:5000
```

### Step 4: Open the web page

In your browser, go to: **http://localhost:5000**

---

## Quick start (double-click)

You can also run `run_web.bat` (if it exists) or create a shortcut that runs:

```
python C:\Users\NEXT\.cursor\intercom-translator\run_web.py
```

Then open **http://localhost:5000** in your browser.

---

## If the page still doesn't work

1. **"This site can't be reached"** – The server is not running. Start it with `python run_web.py` and leave that window open.
2. **Port 5000 in use** – Start the app on another port, e.g. `set PORT=5001` then `python run_web.py`, and use **http://localhost:5001**.
3. **Blank or broken page** – Hard refresh (Ctrl+F5) or try another browser (Chrome/Edge).
