#!/bin/bash
set -e

# Configuration
SERVICE_NAME="remote-time-agent"
REGION="us-central1" # Default, change if needed
AGENT_JSON_PATH="remote_a2a/remote_time_agent/.well-known/agent.json"

# Check for Project ID
PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
    echo "Error: No Google Cloud project selected."
    echo "Please run 'gcloud config set project [PROJECT_ID]' first."
    exit 1
fi

echo "=================================================="
echo "Deploying $SERVICE_NAME to Project: $PROJECT_ID"
echo "Region: $REGION"
echo "=================================================="

# Prepare Environment Variables from .env
echo "Reading .env file..."
ENV_VARS=$(python3 -c "
import sys
import os

env_path = 'remote_a2a/remote_time_agent/.env'
if os.path.exists(env_path):
    try:
        with open(env_path) as f:
            lines = f.readlines()
        pairs = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'): continue
            if '=' in line:
                k, v = line.split('=', 1)
                # Remove surrounding quotes
                v = v.strip('\"\'')
                pairs.append(f'{k}={v}')
        print(','.join(pairs))
    except Exception as e:
        print('')
else:
    print('')
")

DEPLOY_ARGS=""
if [ ! -z "$ENV_VARS" ]; then
    DEPLOY_ARGS="--set-env-vars $ENV_VARS"
    echo "Loaded environment variables from .env"
fi

# 1. Initial Build & Deploy to get the URL
# We need to deploy first to let Cloud Run generate the deterministic URL for this service.
echo "[Step 1/3] Initial Build & Deploy (to generate URL)..."
gcloud builds submit remote_a2a --tag gcr.io/$PROJECT_ID/$SERVICE_NAME
gcloud run deploy $SERVICE_NAME --image gcr.io/$PROJECT_ID/$SERVICE_NAME --platform managed --region $REGION --port 8001 --allow-unauthenticated $DEPLOY_ARGS

# 2. Get the Service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format 'value(status.url)')
echo "Service URL obtained: $SERVICE_URL"

# 3. Update agent.json
echo "[Step 2/3] Updating agent.json with Service URL..."

# Use python to update json reliably
python3 -c "
import json
import sys

file_path = '$AGENT_JSON_PATH'
service_url = '$SERVICE_URL'

try:
    with open(file_path, 'r') as f:
        data = json.load(f)

    # Update main URL
    # Appends /a2a/remote_time_agent/ to the Cloud Run base URL
    base_path = '/a2a/remote_time_agent/'
    new_url = service_url.rstrip('/') + base_path
    data['url'] = new_url
    print(f'Updated url to: {new_url}')

    # Update DCR target_url if present
    # Removes protocol for this specific field as per typical convention (host:port/path)
    host = service_url.replace('https://', '').replace('http://', '').rstrip('/')
    if 'capabilities' in data and 'extensions' in data['capabilities']:
        for ext in data['capabilities']['extensions']:
            if 'params' in ext and 'target_url' in ext['params']:
                 ext['params']['target_url'] = f'{host}/dcr'
                 print(f'Updated dcr target_url to: {host}/dcr')

    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')

except Exception as e:
    print(f'Error updating JSON: {e}')
    sys.exit(1)
"

# 4. Final Build & Deploy
echo "[Step 3/3] Final Build & Deploy (with updated agent.json)..."
gcloud builds submit remote_a2a --tag gcr.io/$PROJECT_ID/$SERVICE_NAME
gcloud run deploy $SERVICE_NAME --image gcr.io/$PROJECT_ID/$SERVICE_NAME --platform managed --region $REGION --port 8001 --allow-unauthenticated $DEPLOY_ARGS --set-env-vars GOOGLE_CLOUD_PROJECT=$PROJECT_ID, GOOGLE_CLOUD_LOCATION=global, GOOGLE_GENAI_USE_VERTEXAI=True

echo "=================================================="
echo "Deployment Complete!"
echo "Service URL: $SERVICE_URL"
echo "Agent Endpoint: ${SERVICE_URL}/a2a/remote_time_agent/"
echo "=================================================="
