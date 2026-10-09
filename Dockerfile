# GovBid Pro: one container with the built React app and the FastAPI backend.

# ---- build the frontend
FROM node:20-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- backend
FROM python:3.12-slim-bookworm
# OpenCascade (STEP reading) links against these X11/OpenGL libraries even without a screen
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglx-mesa0 libx11-6 libxext6 libxrender1 libxcb1 libglib2.0-0 libsm6 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist /app/frontend/dist

# Data lives on a mounted disk: set DATABASE_URL and UPLOAD_DIR to paths under it.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "if [ -z \"$APP_PASSWORD\" ] && [ \"$ALLOW_NO_LOGIN\" != \"1\" ]; then echo 'Refusing to start: set APP_PASSWORD (or ALLOW_NO_LOGIN=1 for a private network).'; exit 1; fi; exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
