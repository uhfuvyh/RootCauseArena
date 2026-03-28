# Repair Strategy System - OpenEnv Environment
FROM python:3.11-slim

LABEL maintainer="repair-strategy-system"
LABEL version="2.0.0"
LABEL description="OpenEnv Repair Strategy System v2 (Hidden State)"

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source files
COPY . .

# Expose port
EXPOSE 7860

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7860/health')"

# Run the FastAPI server
CMD ["uvicorn", "server_v2:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
