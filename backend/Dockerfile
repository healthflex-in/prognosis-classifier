FROM python:3.12-slim

# Unbuffered stdout/stderr so print()/logs stream live to `docker logs`
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend source (excluding .env — injected at runtime)
COPY . .

EXPOSE 8013

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8013"]
