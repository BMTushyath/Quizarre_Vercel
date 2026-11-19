# ⚡ Quizarre (Production Hybrid Vercel Deployment)

A full-stack real-time quiz platform with buzzer synchronization, built for high-scale, zero-downtime production deployment.

---

## 🏛️ Production Architecture (Option B: Hybrid)

```
┌────────────────────────────────────────────────────────┐
│                   Vercel Edge Network                  │
│       React Frontend (index.html, frontend.jsx, css)   │
│             Global CDN • SSL • Zero Cold Starts        │
└───────────────────────────┬────────────────────────────┘
                            │ REST (HTTPS) + WebSocket (WSS)
┌───────────────────────────▼────────────────────────────┐
│         FastAPI Backend (Railway / Render / Docker)    │
│            Persistent Event Loop & WebSocket Hub       │
│      /api/upload-csv   /api/quiz/create   /ws/{id}/{p} │
└─────────────┬────────────────────────────┬─────────────┘
              │                            │
     ┌────────▼────────┐          ┌────────▼────────┐
     │  Shared Redis   │          │   PostgreSQL    │
     │ (Upstash / Cloud│          │ (Neon / Supabase│
     │ Buzzer ZSET ms  │          │ Persistent DB   │
     └─────────────────┘          └─────────────────┘
```

---

## 🚀 Deployment Guide

### Part 1: Deploy Backend (Railway or Render)

1. **Push this `Quizarre_Vercel` repository to GitHub**.
2. **Deploy on Railway** (or Render):
   - Go to [railway.app](https://railway.app) and create a **New Project** → **Deploy from GitHub repo**.
   - Railway will automatically detect the `Dockerfile` or `Procfile`.
3. **Add Managed Redis & Postgres**:
   - In Railway, click **+ New** → **Database** → **Redis**.
   - Click **+ New** → **Database** → **PostgreSQL**.
   - Railway automatically sets `REDIS_URL` and `DATABASE_URL` for your service!
   *(Alternatively, use free [Upstash Redis](https://upstash.com) and [Neon Postgres](https://neon.tech) and paste the connection strings into the Environment Variables tab).*
4. **Copy your Backend URL**:
   - In Railway service settings, click **Generate Domain** (e.g. `https://quizarre-backend.up.railway.app`).

---

### Part 2: Deploy Frontend to Vercel

1. **Configure Backend URL**:
   - Open [`config.js`](file:///config.js) and paste your backend URL:
     ```javascript
     window.QUIZARRE_CONFIG = {
       BACKEND_URL: "https://quizarre-backend.up.railway.app"
     };
     ```
2. **Deploy with Vercel**:
   - Go to [vercel.com](https://vercel.com) → **Add New Project** → Import your repository.
   - **Framework Preset**: Select `Other`.
   - **Build & Output Settings**: Leave defaults (no build command needed; Vercel CDN serves static files directly).
   - Click **Deploy**.
3. Your quiz app is now live at `https://your-project.vercel.app`!

---

## 🧪 Local Testing

You can run the app locally with or without external databases:

```bash
# Optional: start real Redis and Postgres with Docker
docker-compose up -d

# Start backend
python -m venv venv
venv\Scripts\activate       # Windows
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000` (or `http://localhost:3000`).

---

## 🔒 Environment Variables

| Variable | Required | Description | Fallback |
|---|---|---|---|
| `PORT` | Optional | Port for the Uvicorn server | `8000` |
| `REDIS_URL` | Optional | Genuine Redis connection string (`redis://...`) | In-memory `FakeRedis` |
| `DATABASE_URL` | Optional | PostgreSQL connection string (`postgresql://...`) | Local SQLite (`quiz.db`) |
| `ALLOWED_ORIGINS` | Optional | Allowed CORS domains (e.g. `https://*.vercel.app`) | `*` (All allowed) |
