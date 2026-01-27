#!/bin/bash
set -e

# Configuration
PROJECT_ID=$(gcloud config get-value project)
REGION="us-central1"
DATABASE_ID="(default)"

echo "Setting up GCP Firestore Database for Project: $PROJECT_ID in $REGION..."

# 1. Enable Firestore API
echo "Enabling Firestore API..."
gcloud services enable firestore.googleapis.com

# 2. Create Firestore Database
# We explicitly create a 'firestore-native' database in the specified region.
# This prevents the "Project is not a valid Firestore project" error.

echo "Checking if Firestore database '$DATABASE_ID' exists..."

if gcloud firestore databases describe --database=$DATABASE_ID --project=$PROJECT_ID &>/dev/null; then
    echo "Firestore database '$DATABASE_ID' already exists."
else
    echo "Creating Firestore database '$DATABASE_ID' (Type: firestore-native, Location: $REGION)..."
    gcloud firestore databases create \
        --database=$DATABASE_ID \
        --location=$REGION \
        --type=firestore-native \
        --project=$PROJECT_ID
    
    echo "Firestore database '$DATABASE_ID' created successfully."
fi

# 3. Reminder about Permissions
echo "=========================================="
echo "Firestore setup complete."
echo "Ensure your Cloud Run service account has permissions (e.g., 'roles/datastore.user') to access this database."
