"""
Vercel serverless function entry point for Flask app
"""
import sys
import os
from pathlib import Path

# Add parent directory to path so we can import app modules
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

# Set working directory to parent
os.chdir(parent_dir)

# Load environment variables (Vercel provides these via env vars)
from dotenv import load_dotenv
load_dotenv()

# Import the Flask app
from app import app

# Explicitly set static and template folders using absolute paths
# This ensures Flask can find them in the Vercel serverless environment
app.static_folder = str(parent_dir / 'static')
app.template_folder = str(parent_dir / 'templates')

# Vercel Python runtime expects the app to be exported
# It automatically handles WSGI apps like Flask
