# ⚡ Quizarre (100% Free Production Deployment)

A full-stack real-time quiz platform with buzzer synchronization, designed to run **100% free** on cloud providers: **Vercel** for the frontend and **Render** (or Koyeb) for the WebSocket backend.

---

## 🏛️ Architecture & Free Tier Lifecycle

```
┌────────────────────────────────────────────────────────┐
│                   Vercel Edge Network                  │
│       React Frontend (index.html, frontend.jsx, css)   │
│             Global CDN • SSL • 100% Free Always        │
└───────────────────────────┬────────────────────────────┘
                            │ REST (HTTPS) + WebSocket (WSS)
┌───────────────────────────▼────────────────────────────┐
│              Render Free Web Service                   │
│      FastAPI Persistent Event Loop & WebSocket Hub     │
│  (Sleeps when inactive • Auto-wakes on user visit)     │
└─────────────┬────────────────────────────┬─────────────┘
              │                            │
     ┌────────▼────────┐          ┌────────▼────────┐
     │  Upstash Redis  │          │  Neon Postgres  │
     │ 10,000 req/day  │          │   0.5 GB Free   │
     │   100% Free     │          │   100% Free     │
     └─────────────────┘          └─────────────────┘
```

> **💤 Auto-Wake UX**: When the backend sleeps on Render's free tier, the frontend automatically pings `/health` upon page load. A sleek banner informs the user (*"Waking up free cloud backend... Ready in ~30s"*). Once awake, it turns green and runs at lightning speed with zero interruptions!

---

## 🚀 100% Free Deployment Guide

### Step 1: Deploy Backend to Render (100% Free)

1. Sign up for free at [render.com](https://render.com) (login with your GitHub account).
2. Click **New +** → **Web Service**.
3. Select your repository: **`BMTushyath/Quizarre_Vercel`**.
4. Configure the service:
   - **Name**: `quizarre-backend`
   - **Region**: Choose closest to you (e.g. Frankfurt, Oregon, Singapore).
   - **Runtime**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: Select **Free** (0.1 CPU, 512 MB RAM).
5. (Optional - Databases):
   - You can run out of the box with zero databases (uses built-in SQLite & FakeRedis).
   - Or add free cloud databases in the **Environment Variables** section:
     - `REDIS_URL`: from [Upstash](https://upstash.com) (Free Redis)
     - `DATABASE_URL`: from [Neon](https://neon.tech) (Free Postgres)
6. Click **Create Web Service**.
7. Once deployed, copy your Render URL:
   `https://quizarre-backend.onrender.com`

---

### Step 2: Connect Frontend to Render & Deploy on Vercel

1. Open [`config.js`](file:///config.js) and paste your Render URL:
   ```javascript
   window.QUIZARRE_CONFIG = {
     BACKEND_URL: "https://quizarre-backend.onrender.com"
   };
   ```
2. Commit and push:
   ```bash
   git add config.js
   git commit -m "Update backend URL to Render"
   git push
   ```
3. Deploy to Vercel:
   - Go to [vercel.com](https://vercel.com) → **Add New Project**.
   - Import `BMTushyath/Quizarre_Vercel`.
   - Framework Preset: **Other**.
   - Click **Deploy**.

---

### Alternative Free Backend: Koyeb

If you want an alternative to Render:
- [koyeb.com](https://koyeb.com) offers a permanent **Free Eco Tier** with native WebSockets and automatic deployments from Docker or GitHub.

---

## 🧪 Local Development

Run locally with automatic fallback (no cloud services required):

```bash
python -m venv venv
venv\Scripts\activate       # Windows
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000` in your browser.
