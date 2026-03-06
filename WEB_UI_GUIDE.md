# Web UI Guide

## 🚀 Quick Start

### Start the Web Application

```bash
cd intercom-translator
python run_web.py
```

The web UI will be available at: **http://localhost:5000**

## Features

### ✨ Main Features

1. **Connection Status**
   - Real-time connection status indicator
   - Test Intercom and OpenAI API connections
   - Shows number of available articles

2. **Article Selection**
   - Load articles from Intercom Help Center
   - Filter by Collection ID or Tag ID
   - Select multiple articles for translation
   - Visual selection with checkboxes

3. **Language Selection**
   - Select from 11 target languages
   - Select All / Deselect All buttons
   - Visual grid layout

4. **Live Preview** 🔍
   - Preview translations before running full workflow
   - Select any language to see translation preview
   - Shows translated title, description, and body
   - Real-time translation using GPT

5. **Translation Workflow**
   - Translate selected articles to selected languages
   - Progress bar with real-time updates
   - Results modal with success/error summary
   - Detailed error reporting

## Usage

### Step 1: Test Connection
- Click "Test Connection" to verify API access
- Green indicator = Connected
- Red indicator = Connection failed

### Step 2: Load Articles
- Optionally enter Collection ID or Tag ID to filter
- Click "Load Articles" to fetch from Intercom
- Select articles you want to translate

### Step 3: Select Languages
- Choose target languages from the grid
- Use "Select All" / "Deselect All" for quick selection

### Step 4: Preview Translation (Optional)
- Select a language from the dropdown
- Click "Preview Translation"
- Review the translated content

### Step 5: Translate
- Click "🚀 Translate Selected Articles"
- Confirm the action
- Watch progress bar
- Review results in the modal

## API Endpoints

The web UI uses these REST API endpoints:

- `GET /api/articles` - Get articles from Intercom
- `GET /api/article/<id>` - Get specific article
- `GET /api/languages` - Get available languages
- `POST /api/preview` - Preview translation
- `POST /api/translate` - Run translation workflow
- `GET /api/test-connection` - Test API connections

## Configuration

Set environment variables or use `.env` file:

```env
INTERCOM_ACCESS_TOKEN=your_token
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-4o
PORT=5000
FLASK_DEBUG=True
```

## Troubleshooting

### Server won't start
- Check if port 5000 is available
- Verify Python and Flask are installed
- Check environment variables are set

### Connection fails
- Verify API keys are correct
- Check internet connection
- Review browser console for errors

### Preview not working
- Ensure at least one article is selected
- Select a language from dropdown
- Check browser console for API errors

## Browser Support

- Chrome/Edge (recommended)
- Firefox
- Safari
- Modern browsers with ES6 support

## Development

### File Structure
```
intercom-translator/
├── app.py              # Flask application
├── run_web.py          # Web server launcher
├── templates/
│   └── index.html      # Main HTML template
└── static/
    ├── style.css       # Styles
    └── app.js          # Frontend JavaScript
```

### Customization

- **Styling**: Edit `static/style.css`
- **Functionality**: Edit `static/app.js`
- **Backend**: Edit `app.py`

## Next Steps

1. Start the server: `python run_web.py`
2. Open browser: http://localhost:5000
3. Test connection and load articles
4. Preview translations
5. Run full translation workflow

Enjoy translating! 🌐
