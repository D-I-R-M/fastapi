FROM python:3.11-slim

# dbus-python needs build tools and the dbus C headers
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libdbus-1-dev \
        libglib2.0-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# Install without the dbus extras on non-Linux or when not needed;
# on a real Sugar device the dbus package will compile fine.
RUN pip install --no-cache-dir \
        fastapi \
        "uvicorn[standard]" \
        pydantic \
        pydantic-settings \
        httpx \
        python-dotenv \
        anthropic

COPY . .

# Default to mock backends so the image works anywhere
ENV DATASTORE_BACKEND=mock \
    LLM_PROVIDER=mock \
    LOG_LEVEL=info

EXPOSE 8000

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}
