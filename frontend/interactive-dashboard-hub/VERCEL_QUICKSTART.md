# Quick Start: Deploy to Vercel

## Step-by-Step Deployment

### 1. Deploy Frontend to Vercel

1. Go to https://vercel.com/dashboard
2. Click **"Add New Project"**
3. Import repository: `healthflex-in/prognosis-classifier`
4. **IMPORTANT**: Select branch **`fe.dev1`** (not `dev-1`)
5. Configure:
   - **Root Directory**: `frontend/interactive-dashboard-hub`
   - **Framework**: Vite (auto-detected)
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
6. Add Environment Variable:
   - Name: `VITE_API_URL`
   - Value: `https://your-backend-url.com` (you'll get this after deploying backend)
7. Click **"Deploy"**

### 2. Deploy Backend (Choose One)

#### Option A: Railway (Easiest)
1. Go to https://railway.app
2. New Project → Deploy from GitHub
3. Select repo: `healthflex-in/prognosis-classifier`
4. Select branch: **`dev-1`**
5. Root Directory: `backend/api`
6. Build: `pip install -r requirements.txt`
7. Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
8. Add environment variables (MongoDB, etc.)
9. Copy the Railway URL (e.g., `https://your-app.railway.app`)

#### Option B: Render
1. Go to https://render.com
2. New Web Service
3. Connect repo: `healthflex-in/prognosis-classifier`, branch **`dev-1`**
4. Root Directory: `backend/api`
5. Build: `pip install -r requirements.txt`
6. Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
7. Copy the Render URL

### 3. Update Frontend Environment Variable

1. Go back to Vercel dashboard
2. Your Project → Settings → Environment Variables
3. Update `VITE_API_URL` with your backend URL
4. Redeploy (or it will auto-redeploy)

### 4. Update Backend CORS

In your backend code (`backend/api/main.py`), ensure CORS includes your Vercel domain:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://your-project.vercel.app",  # Your Vercel URL
        "http://localhost:8080",  # Local dev
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Branch Strategy Reminder

- **Frontend** (`fe.dev1`) → Deploy to **Vercel**
- **Backend** (`dev-1`) → Deploy to **Railway/Render/Fly.io**

## Testing

1. Visit your Vercel URL
2. Check browser console for API connection
3. Test the dashboard functionality

## Troubleshooting

- **Build fails?** Check root directory is `frontend/interactive-dashboard-hub`
- **API not connecting?** Verify `VITE_API_URL` is set correctly
- **CORS errors?** Update backend CORS with your Vercel domain
