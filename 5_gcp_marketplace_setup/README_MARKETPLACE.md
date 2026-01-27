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
3.  **Checks Account Status**: Upon `ACCOUNT_CREATION_REQUESTED`, it verifies if the account is active and approves it if necessary (safety check).
4.  **Provisions Client**: Registers a new client in Okta associated with the `orderId`.

**Note**: Entitlement approval is handled **automatically** by the Marketplace settings (Automatic Entitlement Approval). This typically occurs at **12:00 AM PT** daily. The code does not manually approve entitlements.

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

The following states need to be actioned on through the Patner Procurement API:

- ACCOUNT_ACTIVE -> Approve Account. This needs to happen separately b/c you don't get a notification on account creation.
  Use this curl command to approve accounts:

```
curl -X POST "https://cloudcommerceprocurement.googleapis.com/v1/providers/cpe-isv-partner-experiments/accounts/209b25f0-36b9-4354-aeae-50e317f56afd:approve" -H "Authorization: Bearer $(gcloud auth print-access-token)"   -H "Content-Length: 0"
```

- ENTITLEMENT_OFFER_ACCEPTED -> Approve Entitlement

The pubsub message will have the form of:

```
Decoded Data: {
"eventId": "CREATE_ENTITLEMENT-f502acf7-5ada-4f92-a53e-d0c9644099f9",
"eventType": "ENTITLEMENT_OFFER_ACCEPTED",
"entitlement": {
"id": "18f7b898-4024-4a2f-b9e8-520d661a8801",
"updateTime": "2026-01-21T00:06:19.754732Z",
"newPlan": "AIAgentEnterprisePlan-P2Y",
"newProduct": "projects/528009937268/services/service.endpoints.private-cp-1053659.cloud.goog/privateOffers/831e0e7d-6251-476e-9ed6-66dd11e05a66",
"newOffer": "projects/528009937268/services/service.endpoints.private-cp-1053659.cloud.goog/privateOffers/831e0e7d-6251-476e-9ed6-66dd11e05a66",
"orderId": "18f7b898-4024-4a2f-b9e8-520d661a8801",
"entitlementBenefitIds": ["45f87775-101b-43dc-a03d-bad9da21c5d7"]
},
"providerId": "cpe-isv-partner-experiments"
}
```

For manual approval here is the curl command:

```
curl -X POST "https://cloudcommerceprocurement.googleapis.com/v1/providers/cpe-isv-partner-experiments/entitlements/18f7b898-4024-4a2f-b9e8-520d661a8801:approve" -H "Authorization: Bearer $(gcloud auth print-access-token)"   -H "Content-Length: 0"
```

https://docs.cloud.google.com/marketplace/docs/partners/integrated-saas/manage-entitlements#eventtypes

Note that even with automatic activation turned on, the order takes 10-20 minutes to get active.
