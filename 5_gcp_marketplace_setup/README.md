# GCP Marketplace Integration Setup

This comprehensive guide outlines the steps to integrate your application with GCP Marketplace, covering the Partner Portal setup, Infrastructure provisioning, and Application Logic. It is designed for users who may be new to Gemini Enterprise, Marketplace, or GCP.

---

## Architecture Diagram

_[Insert Architecture Diagram Here]_

_(The diagram should show the flow from Marketplace -> Pub/Sub -> Cloud Run -> Firestore, and separately the Agent -> DCR Endpoint -> Okta flow)_

---

## 1. High-Level Workflows

There are two distinct flows in this integration. It is crucial to understand that they happen asynchronously and often at different times.

### Flow 1: Procurement from Marketplace (The "Backend" Flow)

This flow happens when an administrator purchases your application on the Google Cloud Marketplace.

1.  **Purchase**: Customer buys the Agent on GCP Marketplace.
2.  **Notification**: GCP publishes a message to a **Pub/Sub Topic**.
3.  **Provisioning**: Your **Cloud Run** service receives this message via a Push Subscription.
    - It extracts the `orderId`.
    - It calls the **Google Partner Procurement API** to approve the Account (and Entitlement if manual).
    - It creates a corresponding Client App in **Okta**.
    - It saves the `orderId` -> `clientId/secret` mapping in **Firestore**.

### Flow 2: Registration on Gemini Enterprise (The "Frontend" Flow)

This flow happens when the user (or admin) actually configures/starts the Agent within the Gemini Enterprise environment.

1.  **Initiation**: The Agent starts up and needs credentials. It sends a **Dynamic Client Registration (DCR)** request to your endpoint.
2.  **Authentication**: The request includes a JWT (`software_statement`) signed by Google.
3.  **Validation**: Your **Cloud Run** service:
    - Validates the JWT signature.
    - Extracts the `google.order` (Order ID) from the JWT.
    - **Cross-Check**: Verifies that this Order ID exists in **Firestore** (provenance from Flow 1).
4.  **Completion**: If valid, it returns the Okta credentials (Client ID & Secret) to the Agent.

---

## 2. Partner Portal Listing

Before touching any code, you must configure the "Business" side in the [Google Cloud Partner Portal](https://producerportal.google.com/).

### Steps

1.  **Create Solution**: Set up your solution listing.
2.  **Tech Integration**:
    - **Agent Card**: Upload your Agent Card JSON to a Google Cloud Storage (GCS) bucket and link it.
    - **Link Service Account**: You will be asked to link a Service Account. Use the **Runtime Service Account** (created in step 3 below). This grants it permission to call the Procurement API.
    - **Pub/Sub Topic**: The portal will provide a Topic Name (e.g., `projects/cloudcommerceproc-prod/topics/cpe-isv-partner-experiments`). **Write this down**. This is where Google sends order notifications (triggering Flow 1).

---

## 3. Cloud Infrastructure Setup

We need to set up the "Plumbing" in your GCP Project.

### 3.1. Service Accounts (SA)

We use two distinct SAs for security (Least Privilege):

1.  **Runtime SA** (`cloud-run-time-agent-marketpla@...`):

    - **Role**: Identifies the running code.
    - **Permissions needed**:
      - `roles/secretmanager.secretAccessor` (To read Okta keys).
      - `roles/datastore.user` (To read/write Firestore).
      - `roles/aiplatform.user` (If using Vertex AI).
      - **External**: Must be linked in the Partner Portal to access the Procurement API.

2.  **Pub/Sub Invoker SA** (`pub-sub-service-account@...`):
    - **Role**: Identifies the Pub/Sub subscription.
    - **Permissions needed**:
      - `roles/run.invoker` (To call your Cloud Run endpoint).
      - **External**: Must be granted access to the Partner Portal Topic (usually handled by Google when you add it in the portal, or via specific IAM bindings).

### 3.2. Database (Firestore)

We use **Firestore** (Native Mode) to persist Order IDs.

- **Why?** Flow 1 (Procurement) and Flow 2 (Registration) are asynchronous. We need a reliable place to store "Order X is valid and maps to Client Y" that persists across service restarts.

### 3.3. Secrets

Store sensitive credentials in GCP Secret Manager:

- `okta-domain`
- `okta-api-token`

---

## 4. Application Logic & Code

The `marketplace_handler.py` is a "Hybrid" endpoint serving both flows:

### Handling Flow 1: Procurement (Async Pub/Sub)

- **Trigger**: A Pub/Sub message arrives at `/dcr` (via Push Subscription).
- **Action**:
  1.  Decodes the message.
  2.  Extracts the `orderId`.
  3.  Approves the Account using the **Google Partner Procurement API** (Required step even for auto-entitlement).
  4.  Calls Okta API to create a new OIDC App.
  5.  Saves `orderId` -> `clientId/secret` mapping to **Firestore**.

### Handling Flow 2: Registration (Sync DCR)

- **Trigger**: The Agent sends a POST request to `/dcr` with a `software_statement` (JWT).
- **Action**:
  1.  Validates the JWT (Signature, Issuer, Audience).
  2.  **Critical Check**: Extracts `google.order` (Order ID) from the JWT.
  3.  **Validation**: Checks if this Order ID exists in **Firestore**.
      - _If Yes_: Returns the Okta credentials.
      - _If No_: Rejects the request (Preventing spoofing).

---

## 5. Deployment Guide

This section details how to go from an empty project to a running integration.

### Phase 1: Environment Setup

1.  **Install Cloud SDK**: Ensure `gcloud` CLI is installed.
2.  **Authenticate**:
    ```bash
    gcloud auth login
    ```
3.  **Set Project**:
    ```bash
    export PROJECT_ID=[YOUR_PROJECT_ID]
    gcloud config set project $PROJECT_ID
    ```

### Phase 2: Partner Portal UI Setup

This phase involves manual configuration in the Google Cloud Producer Portal.

**1. Create Your Solution**

- Navigate to the [Producer Portal](https://producerportal.google.com/).
- Click "Add Solution" and select "SaaS" or the appropriate type.
- Fill in the basic "Solution Details".
  - _Place your screenshot here:_
  - `![Solution Details](images/solution_details.png)`

**2. Technical Integration Configuration**

- Go to the **Technical Integration** tab of your solution.
- **Agent Card**: You will be asked to upload your Agent Card.
  - Ensure your `agent.json` is ready.
  - Upload it to a GCS bucket and provide the link, or upload directly if supported.
  - _Place your screenshot here:_
  - `![Agent Card Upload](images/agent_card_upload.png)`

**3. Link Service Accounts**

- Scroll to the **Service Accounts** section.
- **Link Runtime SA**: Click "Link Service Account" and enter `cloud-run-time-agent-marketpla@...`.
  - _Why?_ This allows your app to talk to the Procurement API.
- **Link Pub/Sub SA**: Add `pub-sub-service-account@...`.
  - _Why?_ This allows Google to send messages to your subscription.
  - _Place your screenshot here:_
  - `![Link Service Accounts](images/link_service_accounts.png)`

**4. Get Pub/Sub Topic**

- Once saved, the portal will generate a **Topic Name** (e.g., `projects/cloudcommerceproc-prod/topics/...`).
- **Copy this**. You will need it for `deploy.sh` (as the `TOPIC` variable).
  - _Place your screenshot here:_
  - `![Pub/Sub Topic](images/pubsub_topic.png)`

### Phase 3: Create Service Accounts & Keys

You need to create the identities that the system will use.

1.  **Create the Runtime Service Account**:

    - _Name used in script_: `cloud-run-time-agent-marketpla`

    ```bash
    gcloud iam service-accounts create cloud-run-time-agent-marketpla \
        --display-name="Cloud Run Runtime SA"
    ```

2.  **Create the Pub/Sub Invoker Service Account**:

    - _Name used in script_: `pub-sub-service-account`

    ```bash
    gcloud iam service-accounts create pub-sub-service-account \
        --display-name="Pub/Sub Invoker SA"
    ```

3.  **Generate Key File for Pub/Sub SA**:
    - **Crucial**: This file is needed by `deploy.sh` to authenticate as this SA and create the cross-project subscription.
    ```bash
    gcloud iam service-accounts keys create cpe-isv-partner-experiments-80bda91e2f1c.json \
        --iam-account=pub-sub-service-account@$PROJECT_ID.iam.gserviceaccount.com
    ```
    - _Note_: The filename `cpe-isv-partner-experiments-80bda91e2f1c.json` matches the default in `deploy.sh`. If you name it differently, update the script.

### Phase 4: Create Secrets

Store your Okta configuration securely.

1.  **Okta Domain**:

    ```bash
    gcloud secrets create okta-domain --replication-policy="automatic"
    echo -n "https://[YOUR-OKTA-DOMAIN]" | gcloud secrets versions add okta-domain --data-file=-
    ```

2.  **Okta API Token**:
    ```bash
    gcloud secrets create okta-api-token --replication-policy="automatic"
    echo -n "[YOUR-OKTA-API-TOKEN]" | gcloud secrets versions add okta-api-token --data-file=-
    ```

### Phase 5: Configure & Deploy

We have automated the infrastructure provisioning and deployment using shell scripts.

1.  **Update Configuration**:

    - Open `deploy.sh`.
    - Update `RUN_SERVICE_ACCOUNT` with your full email: `cloud-run-time-agent-marketpla@$PROJECT_ID.iam.gserviceaccount.com`.
    - Update `PUBSUB_INVOKER_SA` with your full email: `pub-sub-service-account@$PROJECT_ID.iam.gserviceaccount.com`.
    - Update `SA_KEY_FILE` path if you changed the filename or location.

2.  **Initialize Firestore** (Run once):

    - This script enables the Firestore API and ensures the database is created.

    ```bash
    chmod +x setup_firestore.sh
    ./setup_firestore.sh
    ```

3.  **Deploy Application**:

    - This script sets up permissions, creates the Pub/Sub subscription, and deploys to Cloud Run.

    ```bash
    # Ensure the key file path matches what is inside deploy.sh or export it here
    export SA_KEY_FILE="$(pwd)/cpe-isv-partner-experiments-80bda91e2f1c.json"

    chmod +x deploy.sh
    ./deploy.sh
    ```

Note: When testing this, make sure to add users to the newly created Okta app so they can log in via oauth.

---

## 6. Gotchas & "Why did we do this?"

### 1. "Refresh Token Not Found" Error

- **Issue**: During Flow 2, the Agent requests a refresh token, but Okta wasn't returning one.
- **Fix**: We explicitly added `offline_access` to the `scope` when registering the Okta client in `dcr/utils.py`.

### 2. Firestore vs. Local File

- **Decision**: We moved from a local JSON file to Firestore.
- **Why?** Cloud Run is stateless. A local file is lost when the instance scales down or restarts. Firestore bridges Flow 1 and Flow 2 reliably.

### 3. Authentication "Allow Unauthenticated"

- **Decision**: The Cloud Run service is public (`--allow-unauthenticated`).
- **Why?**
  - **Flow 2 (DCR)**: The incoming request uses a JWT signed by Google, but not an IAM OIDC token.
  - **Flow 1 (Pub/Sub)**: The Push Subscription authenticates via a Service Account, but Cloud Run's native IAM check can sometimes be finicky with cross-project push subscriptions.
  - **Security**: We implement application-level security (JWT validation & Order ID checks) to compensate.

### 4. Order ID Validation

- **Critical Security**: We **must** validate that the Order ID in Flow 2 actually exists in our database (from Flow 1).
- **Why?** The DCR JWT is validly signed by Google for _any_ order. Without checking our DB, anyone with a valid Google Marketplace JWT (even for a different product) could potentially register a client. Our DB check ensures we only register clients for orders _we_ received notification for.

---

## 7. Security Summary

- **Least Privilege**: Separate SAs for Runtime and Invoker.
- **JWT Validation**: Strict checks on Issuer (`iss`), Audience (`aud`), and Expiration (`exp`).
- **Business Logic Check**: Order ID must exist in Firestore before issuing credentials.
- **Secret Management**: No hardcoded keys; everything uses GCP Secret Manager.

---

## 8. Manual Operations (Reference)

If Flow 1 (Automated Provisioning) fails, you can verify/approve orders manually using `curl`.

**Approve Account (One-time)**:

```bash
curl -X POST "https://cloudcommerceprocurement.googleapis.com/v1/providers/cpe-isv-partner-experiments/accounts/[ACCOUNT_ID]:approve" \
-H "Authorization: Bearer $(gcloud auth print-access-token)" \
-H "Content-Length: 0"
```

**Approve Entitlement**:

```bash
curl -X POST "https://cloudcommerceprocurement.googleapis.com/v1/providers/cpe-isv-partner-experiments/entitlements/[ENTITLEMENT_ID]:approve" \
-H "Authorization: Bearer $(gcloud auth print-access-token)" \
-H "Content-Length: 0"
```
