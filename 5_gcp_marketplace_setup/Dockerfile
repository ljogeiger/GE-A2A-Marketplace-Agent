FROM python:3.11-slim

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copy the application code
COPY . .

# Install dependencies.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Run the web service on container startup.
# We use the PORT environment variable defined by Cloud Run (default 8080).
CMD exec uvicorn marketplace_handler:app --host 0.0.0.0 --port ${PORT}
