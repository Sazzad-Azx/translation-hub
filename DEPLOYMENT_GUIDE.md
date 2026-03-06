# Deployment Guide: Flask App to Vercel via GitHub

This guide will walk you through deploying your Flask Translation Hub application to Vercel using GitHub.

## Prerequisites

1. **GitHub Account** - Sign up at https://github.com
2. **Vercel Account** - Sign up at https://vercel.com (you can use GitHub to sign in)
3. **Git installed** on your computer

## Step 1: Prepare Your Project

### Files Already Created:
- ✅ `.gitignore` - Excludes sensitive files from Git
- ✅ `vercel.json` - Vercel configuration
- ✅ `api/index.py` - Serverless function entry point
- ✅ `requirements.txt` - Python dependencies

## Step 2: Create GitHub Repository

### 2.1 Initialize Git (if not already done)

Open terminal/command prompt in your project directory:
```bash
cd "C:\Users\Mir Sazzad Hossain\Downloads\sbx-denybin\.cursor\intercom-translator"
git init
```

### 2.2 Add All Files

```bash
git add .
```

### 2.3 Create Initial Commit

```bash
git commit -m "Initial commit: Flask Translation Hub app"
```

### 2.4 Create Repository on GitHub

1. Go to https://github.com/new
2. Repository name: `translation-hub` (or any name you prefer)
3. Description: "FundedNext Translation Hub - Intercom Article Translation System"
4. Choose **Public** or **Private** (Private recommended for production)
5. **DO NOT** initialize with README, .gitignore, or license (we already have these)
6. Click **"Create repository"**

### 2.5 Push to GitHub

GitHub will show you commands. Use these (replace `YOUR_USERNAME` with your GitHub username):

```bash
git remote add origin https://github.com/YOUR_USERNAME/translation-hub.git
git branch -M main
git push -u origin main
```

You'll be prompted for your GitHub username and password (or personal access token).

## Step 3: Deploy to Vercel

### 3.1 Sign In to Vercel

1. Go to https://vercel.com
2. Click **"Sign Up"** or **"Log In"**
3. Choose **"Continue with GitHub"** (recommended)

### 3.2 Import Your Repository

1. Click **"Add New..."** → **"Project"**
2. Find your `translation-hub` repository
3. Click **"Import"**

### 3.3 Configure Project Settings

Vercel should auto-detect:
- **Framework Preset**: Other (or Python)
- **Root Directory**: `./` (leave as is)
- **Build Command**: Leave empty (not needed for Python)
- **Output Directory**: Leave empty

### 3.4 Add Environment Variables

**IMPORTANT**: Add all your environment variables here:

1. Click **"Environment Variables"** section
2. Add each variable:

```
INTERCOM_ACCESS_TOKEN = your_intercom_access_token_here
OPENAI_API_KEY = your_openai_api_key_here
OPENAI_MODEL = gpt-4o-mini
SUPABASE_URL = (your Supabase URL)
SUPABASE_SERVICE_KEY = (your Supabase service key)
```

**For each environment:**
- ✅ Production
- ✅ Preview
- ✅ Development

### 3.5 Deploy

1. Click **"Deploy"**
2. Wait 2-5 minutes for build to complete
3. You'll get a URL like: `https://translation-hub-xyz.vercel.app`

## Step 4: Verify Deployment

1. Visit your Vercel URL
2. Test the application:
   - Check if the dashboard loads
   - Test API endpoints
   - Verify static files (CSS, JS) load correctly

## Step 5: Custom Domain (Optional)

1. In Vercel dashboard, go to **Settings** → **Domains**
2. Add your custom domain (e.g., `translation-hub.yourdomain.com`)
3. Follow DNS configuration instructions

## Troubleshooting

### Issue: Build fails
- Check Vercel build logs
- Ensure `requirements.txt` has all dependencies
- Verify Python version compatibility

### Issue: Environment variables not working
- Make sure you added them in Vercel dashboard
- Check variable names match exactly (case-sensitive)
- Redeploy after adding variables

### Issue: Static files not loading
- Check `vercel.json` routes configuration
- Ensure static files are in `static/` directory
- Verify file paths in HTML templates

### Issue: API endpoints return 404
- Check `api/index.py` is correctly importing Flask app
- Verify routes are defined in `app.py`
- Check Vercel function logs

## Updating Your App

After making changes:

1. **Commit changes:**
   ```bash
   git add .
   git commit -m "Your update message"
   git push
   ```

2. **Vercel auto-deploys** - It will automatically detect the push and redeploy

## Important Notes

⚠️ **Security:**
- Never commit `.env` file (already in `.gitignore`)
- Use Vercel environment variables for secrets
- Keep your repository private if it contains sensitive info

⚠️ **Limitations:**
- Vercel serverless functions have execution time limits (10s on Hobby, 60s on Pro)
- Large file uploads may need special handling
- Database connections should use connection pooling

## Support

- Vercel Docs: https://vercel.com/docs
- Flask on Vercel: https://vercel.com/docs/concepts/functions/serverless-functions/runtimes/python
- GitHub Docs: https://docs.github.com
