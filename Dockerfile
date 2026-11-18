# ==========================================
# Stage 1: Build Web Frontend Assets
# ==========================================
FROM node:20-alpine AS frontend-builder

WORKDIR /build

COPY frontend/package*.json ./
RUN npm ci --prefer-offline --no-audit || npm install

COPY frontend/ ./
# Empty VITE_API_BASE_URL ensures web builds use same-domain /api/v1 relative calls
RUN VITE_API_BASE_URL="" npm run build

# ==========================================
# Stage 2: Production Python API Backend
# ==========================================
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application source
COPY backend/ /app/

# Copy compiled frontend distribution for unified single-domain hosting
COPY --from=frontend-builder /build/dist /app/frontend/dist

# Ensure private audio storage directory exists
RUN mkdir -p /app/data/audio /tmp/audio

# Expose default HTTP port for Koyeb (8000)
EXPOSE 8000

# Start FastAPI server on dynamic $PORT injected by Koyeb (defaults to 8000)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
