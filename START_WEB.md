# Starting the Web UI

## ✅ Server Status

The web server is starting. It should be available at:

**http://localhost:5000**

## 🔒 Safety Features

The web UI includes **double confirmation** before any translation:

1. **First Confirmation**: Shows number of articles and languages
2. **Second Confirmation**: Final confirmation before proceeding

No translations will happen without your explicit confirmation!

## 📋 How to Use

1. **Open your browser** and go to: http://localhost:5000

2. **Test Connection**: Click "Test Connection" to verify API access

3. **Load Articles**: 
   - Optionally filter by Collection ID or Tag ID
   - Click "Load Articles"

4. **Select Articles**: Check the articles you want to translate

5. **Select Languages**: Choose target languages from the grid

6. **Preview Translation** (Optional):
   - Select a language from dropdown
   - Click "Preview Translation"
   - Review the translated content

7. **Translate** (Requires Double Confirmation):
   - Click "🚀 Translate Selected Articles"
   - **First confirmation**: Review the summary
   - **Second confirmation**: Final confirmation
   - Only then will translations proceed

## ⚠️ Important Notes

- **Preview is safe**: Preview translations don't update Intercom
- **Translation requires confirmation**: You must confirm twice before any updates
- **Progress tracking**: See real-time progress during translation
- **Results modal**: Review success/errors after completion

## 🛑 To Stop the Server

Press `Ctrl+C` in the terminal where the server is running.

## 🔧 Troubleshooting

If the server doesn't start:
- Check if port 5000 is available
- Verify environment variables are set
- Check Python and Flask are installed

If you can't access http://localhost:5000:
- Wait a few seconds for server to fully start
- Check firewall settings
- Try http://127.0.0.1:5000
