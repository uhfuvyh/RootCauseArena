FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .

# Install Python packages only (no gcc needed)
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source files
COPY . .

# HuggingFace Spaces requires port 7860
EXPOSE 7860

# Start server
CMD ["uvicorn", "server_v2:app", "--host", "0.0.0.0", "--port", "7860"]
