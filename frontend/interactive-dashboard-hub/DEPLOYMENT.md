# Vercel Deployment Guide

This guide explains how to deploy the Prognosis Classifier Dashboard frontend to Vercel.

## Prerequisites

1. A Vercel account (sign up at https://vercel.com)
2. Your backend API deployed and accessible (see Backend Deployment section)
3. Git repository access to the `fe.dev1` branch

## Frontend Deployment to Vercel

### Option 1: Deploy via Vercel Dashboard (Recommended)

1. **Go to Vercel Dashboard**
   - Visit https://vercel.com/dashboard
   - Click "Add New Project"

2. **Import Git Repository**
   - Select your Git provider (GitHub, GitLab, or Bitbucket)
   - Choose the repository: `healthflex-in/prognosis-classifier`
   - **Important**: Select the branch `fe.dev1` (not `dev-1`)

3. **Configure Project Settings**
   - **Root Directory**: Set to `frontend/interactive-dashboard-hub`
   - **Framework Preset**: Vite (should auto-detect)
   - **Build Command**: `npm run build` (default)
   - **Output Directory**: `dist` (default)
   - **Install Command**: `npm install` (default)

4. **Environment Variables**
   - Click "Environment Variables"
   - Add the following:
     ```
     VITE_API_URL=https://your-backend-url.com
     ```
   - Replace `https://your-backend-url.com` with your actual backend API URL
   - Make sure to add it for all environments (Production, Preview, Development)

5. **Deploy**
   - Click "Deploy"
   - Wait for the build to complete
   - Your frontend will be live at a URL like `https://your-project.vercel.app`

### Option 2: Deploy via Vercel CLI

1. **Install Vercel CLI**
   ```bash
   npm i -g vercel
   ```

2. **Navigate to Frontend Directory**
   ```bash
   cd frontend/interactive-dashboard-hub
   ```

3. **Login to Vercel**
   ```bash
   vercel login
   ```

4. **Deploy**
   ```bash
   vercel
   ```
   - Follow the prompts
   - When asked for the root directory, specify: `frontend/interactive-dashboard-hub`
   - Add environment variable `VITE_API_URL` when prompted

5. **Set Production Environment Variable**
   ```bash
   vercel env add VITE_API_URL production
   ```
   - Enter your backend API URL when prompted

## Backend Deployment

Since Vercel is optimized for frontend and serverless functions, you'll need to deploy your FastAPI backend separately. Here are recommended options:

### Option 1: Railway (Recommended for FastAPI)

1. **Sign up at Railway**: https://railway.app
2. **Create New Project** → "Deploy from GitHub repo"
3. **Select Repository**: `healthflex-in/prognosis-classifier`
4. **Select Branch**: `dev-1`
5. **Root Directory**: `backend/api`
6. **Configure**:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Add environment variables (MongoDB connection, etc.)
7. **Get the deployment URL** (e.g., `https://your-app.railway.app`)

### Option 2: Render

1. **Sign up at Render**: https://render.com
2. **Create New Web Service**
3. **Connect Repository**: Select `healthflex-in/prognosis-classifier`, branch `dev-1`
4. **Configure**:
   - Root Directory: `backend/api`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Environment: Python 3
5. **Add Environment Variables** (MongoDB, etc.)
6. **Deploy** and get the URL

### Option 3: Fly.io

1. **Install Fly CLI**: `curl -L https://fly.io/install.sh | sh`
2. **Navigate to backend**: `cd backend/api`
3. **Initialize**: `fly launch`
4. **Configure** and deploy

## Environment Variables

### Frontend (Vercel)
- `VITE_API_URL`: Your backend API URL (e.g., `https://your-backend.railway.app`)

### Backend (Railway/Render/Fly.io)
- MongoDB connection string
- Any other backend-specific environment variables

## CORS Configuration

Make sure your backend has CORS enabled for your Vercel domain:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://your-project.vercel.app",
        "http://localhost:8080",  # For local development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Continuous Deployment

Once connected to Vercel:
- **Automatic deployments**: Every push to `fe.dev1` branch will trigger a new deployment
- **Preview deployments**: Pull requests get preview URLs automatically
- **Production**: Merges to `fe.dev1` (or your production branch) deploy to production

## Troubleshooting

### Build Fails
- Check that you've set the correct root directory (`frontend/interactive-dashboard-hub`)
- Verify all dependencies are in `package.json`
- Check build logs in Vercel dashboard

### API Connection Issues
- Verify `VITE_API_URL` is set correctly in Vercel environment variables
- Check CORS settings on your backend
- Ensure backend is accessible from the internet

### 404 Errors on Routes
- The `vercel.json` includes a rewrite rule to handle client-side routing
- If issues persist, check the rewrite configuration

## Branch Strategy

- **`fe.dev1`**: Frontend code (deployed to Vercel)
- **`dev-1`**: Backend code (deployed to Railway/Render/Fly.io)

Make sure to select the correct branch when setting up deployments!
