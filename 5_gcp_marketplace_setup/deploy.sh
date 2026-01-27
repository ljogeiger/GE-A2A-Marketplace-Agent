# Configuration
SERVICE_NAME="marketplace-handler"
REGION="us-central1"
# Service Account for the Cloud Run Instance (Runtime) - has Secret Accessor & Procurement API perms
RUN_SERVICE_ACCOUNT="cloud-run-time-agent-marketpla@cpe-isv-partner-experiments.iam.gserviceaccount.com"
# Service Account for Pub/Sub Subscription identity (Invoker)
PUBSUB_INVOKER_SA="pub-sub-service-account@cpe-isv-partner-experiments.iam.gserviceaccount.com"
TOPIC="projects/cloudcommerceproc-prod/topics/cpe-isv-partner-experiments"
SUB_NAME="marketplace-order-sub"
SA_KEY_FILE="/Users/lukasgeiger/Desktop/GE_A2A_Marketplace_Agent/5_gcp_marketplace_setup/cpe-isv-partner-experiments-80bda91e2f1c.json"

echo "Deploying Cloud Run service: $SERVICE_NAME..."

# Note: Ensure that the 'okta-domain' and 'okta-api-token' secrets exist in Secret Manager
# and the Service Account has 'Secret Manager Secret Accessor' role.
# We mount the NFS share to /mnt/filestore
gcloud run deploy $SERVICE_NAME \
  --source . \
  --region $REGION \
  --service-account $RUN_SERVICE_ACCOUNT \
  --allow-unauthenticated \
  --set-secrets OKTA_DOMAIN=OKTA_DOMAIN:latest,OKTA_API_TOKEN=OKTA_API_TOKEN:latest \
  --set-env-vars DEFAULT_REDIRECT_URI="https://vertexaisearch.cloud.google.com/oauth-redirect"

# Get the URL of the deployed service
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)')
echo "Service deployed at: $SERVICE_URL"

echo "Setting up permissions..."
# Grant the Cloud Run Service Account access to Firestore (Datastore User)
echo "Granting 'roles/datastore.user' to $RUN_SERVICE_ACCOUNT..."
gcloud projects add-iam-policy-binding $(gcloud config get-value project) \
    --member="serviceAccount:$RUN_SERVICE_ACCOUNT" \
    --role="roles/datastore.user"

# Grant Vertex AI User role
echo "Granting 'roles/aiplatform.user' to $RUN_SERVICE_ACCOUNT..."
gcloud projects add-iam-policy-binding $(gcloud config get-value project) \
    --member="serviceAccount:$RUN_SERVICE_ACCOUNT" \
    --role="roles/aiplatform.user"

# Grant Secret Manager Secret Accessor role
echo "Granting 'roles/secretmanager.secretAccessor' to $RUN_SERVICE_ACCOUNT..."
gcloud projects add-iam-policy-binding $(gcloud config get-value project) \
    --member="serviceAccount:$RUN_SERVICE_ACCOUNT" \
    --role="roles/secretmanager.secretAccessor"

# Grant the Pub/Sub Service Account permission to invoke the Cloud Run service
gcloud run services add-iam-policy-binding $SERVICE_NAME \
  --region $REGION \
  --member="serviceAccount:$PUBSUB_INVOKER_SA" \
  --role="roles/run.invoker"

# Grant the Pub/Sub Service Account permission to act as itself (Service Account User).
# This is required because we are authenticating AS the SA and then creating a subscription
# that uses the SA as the push-auth identity.
echo "Granting 'Service Account User' to $PUBSUB_INVOKER_SA on itself..."
gcloud iam service-accounts add-iam-policy-binding $PUBSUB_INVOKER_SA \
    --member="serviceAccount:$PUBSUB_INVOKER_SA" \
    --role="roles/iam.serviceAccountUser"

echo "Activating Service Account for Pub/Sub subscription creation..."
# Ensure SA_KEY_FILE is provided
if [ -z "$SA_KEY_FILE" ]; then
    echo "Error: SA_KEY_FILE environment variable is not set."
    echo "Please provide the path to your Service Account JSON key file."
    echo "Usage: SA_KEY_FILE=/path/to/key.json ./deploy.sh"
    exit 1
fi

# Activate the Service Account
# This changes the active gcloud credential to the Service Account
gcloud auth activate-service-account --key-file="$SA_KEY_FILE"

echo "Creating/Updating Pub/Sub subscription: $SUB_NAME..."
# Create a push subscription to the external topic.
# We are now authenticated as the Service Account which has permissions on the external topic.
if gcloud pubsub subscriptions describe $SUB_NAME &>/dev/null; then
    echo "Subscription exists."
else
    echo "Creating new subscription..."
    gcloud pubsub subscriptions create $SUB_NAME \
        --topic=$TOPIC \
        --push-endpoint=$SERVICE_URL/dcr \
        --push-auth-service-account=$PUBSUB_INVOKER_SA \
        --ack-deadline=60
fi

echo "Deployment complete."
