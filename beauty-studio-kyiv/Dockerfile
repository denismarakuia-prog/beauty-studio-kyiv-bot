FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# gcc needed for uvicorn[standard] C extensions (uvloop, httptools)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure data directory exists (overridden by Render disk mount when configured)
RUN mkdir -p /app/data

EXPOSE 8000

# Exec form — no shell wrapper; Python reads $PORT directly via os.environ
CMD ["python", "main.py"]
