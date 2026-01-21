# GCP Marketplace Integration Setup

This document outlines the steps to integrate your application with GCP Marketplace using Pub/Sub notifications, Google Partner Procurement API, and Okta for Dynamic Client Registration (DCR).

## Overview

The integration consists of three main parts:

1.  **Partner Portal Configuration**: Setting up the listing and linking service accounts.
2.  **Code Changes**: Handling Pub/Sub messages and provisioning clients. (Approval is handled automatically by the Marketplace).
3.  **Cloud Deployment**: Deploying the handler as a Cloud Run service triggered by a Pub/Sub Push Subscription.

## 1. Partner Portal Listing

1.  Navigate to the Google Cloud Partner Portal.
2.  **Tech Integration**:
    - Upload your Agent Card to Google Cloud Storage (GCS).
    - Link the Runtime Service Account (see below) to your listing.
    - **Important**: Note down the **Pub/Sub Topic** provided by the portal (e.g., `projects/cloudcommerceproc-prod/topics/[PARTNER-TOPIC-ID]`).

## 2. Code Changes

The codebase includes a `marketplace_handler.py` service. This service:

1.  **Receives Pub/Sub Events**: Listens for messages on the configured topic via a Push Subscription.
2.  **Handles Direct DCR**: Processes direct client registration requests using a Signed JWT (Hybrid Handler).
3.  **Provisions Client**: Registers a new client in Okta associated with the `orderId`.

**Note**: Order approval is handled automatically by the Marketplace settings (Automatic Entitlement/Account Approval), so no manual API call is needed in the code. Note that if you choose automatic approval - entitlements get approved at 12am PT.

### Prerequisites

- `fastapi`, `uvicorn`
- `google-auth`, `requests` (or `httpx`)
- `pydantic`
- `google-cloud-iam` (for testing scripts)

## 3. Cloud Changes & Deployment

### Service Accounts

You need two distinct Service Accounts (SAs):

1.  **Runtime SA** (`[RUNTIME-SA-EMAIL]`):

    - Example: `cloud-run-time-agent-marketpla@...`
    - Used by the Cloud Run instance itself.
    - Permissions: Access to Secret Manager, Okta credentials.

2.  **Pub/Sub SA** (`[PUBSUB-SA-EMAIL]`):
    - Example: `pub-sub-service-account@...`
    - Used as the identity for the Pub/Sub Push Subscription.
    - **Permissions**: Must be granted access to the external Marketplace Topic (done in Partner Portal).
    - **Local Permissions**: Must be granted `roles/run.invoker` on the Cloud Run service (handled by `deploy.sh`).

### Secrets Management

Before deploying, create the necessary secrets in GCP Secret Manager:

```bash
# Okta Domain (e.g., https://your-org.okta.com)
gcloud secrets create okta-domain --replication-policy="automatic"
echo -n "https://[YOUR-OKTA-DOMAIN]" | gcloud secrets versions add okta-domain --data-file=-

# Okta API Token
gcloud secrets create okta-api-token --replication-policy="automatic"
echo -n "[YOUR-OKTA-API-TOKEN]" | gcloud secrets versions add okta-api-token --data-file=-
```

### Deployment Script

The `deploy.sh` script handles the deployment and subscription setup.

**Prerequisite**: You must have a JSON key file for the **Pub/Sub SA** (`[PUBSUB-SA-EMAIL]`) locally. This is required to authenticate as that SA to create the subscription on the external topic.

```bash
# 1. Download the key file for [PUBSUB-SA-EMAIL]
# 2. Set the environment variable
export SA_KEY_FILE="/path/to/your/service-account-key.json"

# 3. Run the deployment
chmod +x deploy.sh
./deploy.sh
```

## Gotchas & Troubleshooting

### Subscription Creation Authentication

Creating the Pub/Sub subscription to the external Marketplace topic requires special authentication. You cannot simply impersonate the Service Account; you must **activate** it using a key file.

- **The Issue**: The `gcloud pubsub subscriptions create` command needs to prove it has permission on the _external_ topic. Only the Service Account linked in the Partner Portal has this.
- **The Fix**: The `deploy.sh` script does this automatically if `SA_KEY_FILE` is provided:

  ```bash
  gcloud auth activate-service-account --key-file=[PATH_TO_KEY_FILE]
  # --> Activated service account credentials for: [PUBSUB-SA-EMAIL]

  gcloud pubsub subscriptions create [SUB_NAME] \
      --topic=[EXTERNAL_TOPIC] \
      --push-endpoint=[SERVICE_URL]/dcr \
      --push-auth-service-account=[PUBSUB-SA-EMAIL]
  ```

- **Reference**:
  - [gcloud pubsub subscriptions create](https://docs.cloud.google.com/sdk/gcloud/reference/pubsub/subscriptions/create#--push-auth-service-account)
  - [Push Subscription Authentication](https://docs.cloud.google.com/pubsub/docs/create-push-subscription#authentication)

### Approval API Docs

(For reference only - code handles this automatically if auto-approve is off, but currently it is assumed on)

- [Entitlements Approve](https://docs.cloud.google.com/marketplace/docs/partners/commerce-procurement-api/reference/rest/v1/providers.entitlements/approve)
- [Account Approval](https://docs.cloud.google.com/marketplace/docs/partners/offers/account-approval)
