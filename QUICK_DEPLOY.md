# Quick Deployment Checklist

Follow these steps in order to deploy your app to Vercel:

## ✅ Pre-Deployment Checklist

- [ ] All code changes committed
- [ ] `.env` file is NOT committed (check `.gitignore`)
- [ ] `requirements.txt` is up to date
- [ ] `vercel.json` exists and is configured
- [ ] `api/index.py` exists

## 📝 Step-by-Step Instructions

### 1. Initialize Git (if not done)
```bash
cd "C:\Users\Mir Sazzad Hossain\Downloads\sbx-denybin\.cursor\intercom-translator"
git init
git add .
git commit -m "Initial commit: Ready for Vercel deployment"
```

### 2. Create GitHub Repository
1. Go to: https://github.com/new
2. Repository name: `translation-hub` (or your choice)
3. Make it **Private** (recommended)
4. Click **"Create repository"**

### 3. Push to GitHub
```bash
# Replace YOUR_USERNAME with your GitHub username
git remote add origin https://github.com/YOUR_USERNAME/translation-hub.git
git branch -M main
git push -u origin main
```

### 4. Deploy to Vercel
1. Go to: https://vercel.com
2. Sign in with GitHub
3. Click **"Add New..."** → **"Project"**
4. Import your `translation-hub` repository
5. **Configure:**
   - Framework: Leave as "Other" or "Python"
   - Root Directory: `./` (default)
   - Build Command: (leave empty)
   - Output Directory: (leave empty)

### 5. Add Environment Variables
In Vercel project settings, add these:

| Variable Name | Value |
|--------------|-------|
| `INTERCOM_ACCESS_TOKEN` | `your_intercom_access_token_here` |
| `OPENAI_API_KEY` | `your_openai_api_key_here` |
| `OPENAI_MODEL` | `gpt-4o-mini` |
| `SUPABASE_URL` | (Your Supabase URL) |
| `SUPABASE_SERVICE_KEY` | (Your Supabase service key) |

**Important:** Add to all environments (Production, Preview, Development)

### 6. Deploy
1. Click **"Deploy"**
2. Wait 2-5 minutes
3. Get your live URL: `https://your-project.vercel.app`

## 🔄 Updating After Changes

```bash
git add .
git commit -m "Update description"
git push
```

Vercel will automatically redeploy!

## 🐛 Common Issues

**Build fails?**
- Check build logs in Vercel dashboard
- Verify all dependencies in `requirements.txt`

**Environment variables not working?**
- Make sure you added them in Vercel (not just locally)
- Redeploy after adding variables

**Static files not loading?**
- Check browser console for 404 errors
- Verify `static/` folder structure

## 📞 Need Help?

- Full guide: See `DEPLOYMENT_GUIDE.md`
- Vercel docs: https://vercel.com/docs
- Check Vercel function logs in dashboard
