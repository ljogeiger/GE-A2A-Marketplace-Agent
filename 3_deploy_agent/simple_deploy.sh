#!/bin/bash
set -e

# Configuration
SERVICE_NAME="remote-time-agent"
REGION="us-central1" # Default, change if needed

# Get Project ID from gcloud config
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

# Define the common deployment arguments
DEPLOY_ARGS=" \
    --set-env-vars GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_VERTEXAI=True \
"

# 1. Submit the build to Cloud Build
echo "Submitting build for $SERVICE_NAME..."
gcloud builds submit remote_a2a --tag gcr.io/$PROJECT_ID/$SERVICE_NAME

# 2. Deploy to Cloud Run
echo "Deploying $SERVICE_NAME to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
    --platform managed \
    --region $REGION \
    --port 8001 \
    --allow-unauthenticated \
    --set-secrets="OKTA_DOMAIN=OKTA_DOMAIN:latest,OKTA_AUTH_SERVER_ID=OKTA_AUTH_SERVER_ID:latest,OKTA_RS_CLIENT_ID=OKTA_RS_CLIENT_ID:latest,OKTA_RS_CLIENT_SECRET=OKTA_RS_CLIENT_SECRET:latest" \
    $DEPLOY_ARGS

echo "=================================================="
echo "Deployment Complete!"
echo "Service Name: $SERVICE_NAME"
echo "Region: $REGION"
echo "To get the service URL, run: gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format 'value(status.url)'"
echo "=================================================="
