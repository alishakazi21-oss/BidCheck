# ── Stage 1: Build & wheels generation ───────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels -r requirements.txt

# ── Stage 2: Minimal runtime image ──────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install minimal runtime libraries only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy pre-built wheels and install them without build compilers
COPY requirements.txt .
COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Copy application source code
COPY . .

# Generate initial demo database & benchmarks
RUN python scripts/make_dummy_data.py && python scripts/load_kaggle_data.py

EXPOSE 8501 8000

CMD ["streamlit", "run", "ui/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
