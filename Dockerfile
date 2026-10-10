# ============================================================
# Multi-stage Dockerfile for dutchkem-trader-legendary
# Backend: Python (FastAPI) | Frontend: Next.js
# ============================================================

# --- Stage 1: Build frontend ---
FROM node:20-alpine AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci 2>/dev/null || npm install
COPY frontend/ ./
RUN npm run build 2>/dev/null || echo "Frontend build skipped"

# --- Stage 2: Backend runtime ---
FROM python:3.11-slim AS backend
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/ ./backend/
RUN if [ -f backend/requirements.txt ]; then \
      pip install --no-cache-dir -r backend/requirements.txt; \
    elif [ -f backend/pyproject.toml ]; then \
      pip install --no-cache-dir -e backend/ 2>/dev/null || \
      pip install --no-cache-dir backend/; \
    else \
      echo "No backend deps declared"; \
    fi

# Copy built frontend assets
COPY --from=frontend-builder /build/frontend/.next ./frontend/.next 2>/dev/null || true
COPY --from=frontend-builder /build/frontend/package.json ./frontend/ 2>/dev/null || true

COPY . .

ENV PYTHONPATH=/app
EXPOSE 8000

CMD ["python", "-m", "backend.api.main"]
