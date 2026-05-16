# Use official slim Python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Expose port (documented, but Cloud Run overrides this)
EXPOSE 5000

# Run the production server, dynamically binding to GCP's PORT env variable (defaults to 5000 if not set)
CMD ["sh", "-c", "gunicorn -w 2 -b 0.0.0.0:${PORT:-5000} app:app"]
