"""
Run the web application
"""
import os
import sys
from dotenv import load_dotenv

# Fix Windows console encoding for Unicode characters
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Load environment variables
load_dotenv()

# Set environment variables if not already set
if not os.getenv('INTERCOM_ACCESS_TOKEN'):
    os.environ['INTERCOM_ACCESS_TOKEN'] = 'your_intercom_access_token_here'
if not os.getenv('OPENAI_API_KEY'):
    os.environ['OPENAI_API_KEY'] = 'your_openai_api_key_here'
if not os.getenv('OPENAI_MODEL'):
    os.environ['OPENAI_MODEL'] = 'gpt-4o-mini'

from app import app

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f"\n{'='*60}")
    print("Intercom Translation Workflow - Web UI")
    print(f"{'='*60}")
    print(f"\nStarting server on http://localhost:{port}")
    print("Press Ctrl+C to stop\n")
    app.run(host='0.0.0.0', port=port, debug=True)
