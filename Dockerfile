FROM node:20-slim AS frontend

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
ENV BUILD_OUT_DIR=dist
RUN npm run build


FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# python3-venv is required because managed apps create isolated venvs at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-venv \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
COPY --from=frontend /frontend/dist ./app/static/app

RUN pip install --upgrade pip \
    && pip install .

RUN useradd --create-home --home-dir /home/manager --shell /usr/sbin/nologin manager \
    && mkdir -p /app/data \
    && chown -R manager:manager /app

USER manager

EXPOSE 7999

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7999"]
