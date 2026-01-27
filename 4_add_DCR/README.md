# Dynamic Client Registration (DCR) for Gemini Enterprise

This directory contains the implementation of a Dynamic Client Registration (DCR) endpoint. DCR allows Gemini Enterprise to programmatically register as an OAuth 2.0 client with your agent's authorization server (Okta in this case).

## Overview & Examples

The DCR flow involves configuring your Agent to advertise the DCR endpoint and then handling the registration requests from Google.

### 1. AgentCard Configuration

First, you must declare your DCR endpoint in your `AgentCard` by adding the DCR extension and provider url.
The provider url is used in the audience check in step 5.

```json
{
  "name": "your_agent_name",
  "protocolVersion": "1.0.0",
  "provider": {
    "organization": "Your Organization",
    "url": "https://your-organization.com"
  },
  "capabilities": {
    "extensions": [
      {
        "uri": "https://cloud.google.com/marketplace/docs/partners/ai-agents/setup-dcr",
        "params": {
          "target_url": "<your_dcr_endpoint_url>"
        }
      }
    ]
  }
}
```

### 2. Request (from Gemini Enterprise)

Google sends a POST request to your `<target_url>` with a JSON body containing a signed JWT (`software_statement`).

**Request Body:**

```json
{
  "software_statement": "<software_statement_jwt>"
}
```

**Decoded JWT Structure (`software_statement`):**
The JWT header contains the signing key ID (`kid`), and the payload contains the registration details:

```json
{
  "iss": "https://www.googleapis.com/service_accounts/v1/metadata/x509/cloud-agentspace@system.gserviceaccount.com",
  "iat": <ISSUED_AT_TIMESTAMP>,
  "exp": <EXPIRATION_TIMESTAMP>,
  "aud": "<AGENTCARD_PROVIDER_URL>",
  "auth_app_redirect_uris": [
    "<REDIRECT_URI>"
  ],
  "sub": "<PROCUREMENT_ACCOUNT_ID>",
  "google": {
    "order": "<ORDER_ID>"
  }
}
```

- `iss`: Identity of the sender (Google).
- `aud`: Must match your agent's provider URL.
- `auth_app_redirect_uris`: The redirect URIs to register with Okta.
- `google.order`: The Marketplace Order ID, used to associate the client.

### 3. Validation & Registration (Server Logic)

Upon receiving the request, the server:

1.  **Validates Signature:** Checks the JWT signature using Google's public keys.
2.  **Validates Claims:** Verifies `iss`, `exp`, and `aud`.
3.  **Registers Client:** Calls Okta's API to create a new OIDC application using the `auth_app_redirect_uris`.
4.  **Stores Mapping:** Saves the `google.order` -> `client_id` mapping (in `clients_db.json` for this local setup).

### 4. Response (to Gemini Enterprise)

The server responds with the newly created Client ID and Secret.

**Response Body:**

```json
{
  "client_id": "<newly_created_client_id>",
  "client_secret": "<newly_created_client_secret>",
  "client_secret_expires_at": 0
}
```

- `client_secret_expires_at`: Set to `0` as Gemini Enterprise does not currently support secret rotation.

---

## Design Decisions

- **Local Database:** For this local implementation, we use a simple JSON file (`clients_db.json`) to store the `order_id` -> `client_id/secret` mapping. This allows for easy inspection and debugging. In the next phase (deployment), this will be replaced with **Firestore** for persistence and scalability.
- **Test Issuer:** To facilitate local testing without triggering real Google Marketplace events, the code supports an optional `ALLOW_TEST_ISSUER` flag. This allows the endpoint to accept JWTs signed by a specific user-controlled Service Account (`TEST_SERVICE_ACCOUNT`) instead of strictly requiring the production Google issuer.
- **FastAPI:** Chosen for its speed and native async support, which is beneficial for handling external HTTP calls to Google (for keys) and Okta.

## Implementation Status & Omitted Steps

While this implementation covers the core DCR protocol, several production-grade features are currently **omitted**:

| Feature                    | Status       | Reason for Omission                                                                                                                                                                                                                                                 |
| :------------------------- | :----------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Procurement Validation** | ❌ Omitted   | verifying that the `google.order` and `sub` (Procurement Account ID) correspond to a valid, active purchase requires integrating with the Google Marketplace Pub/Sub notifications. This is complex to mock locally and is reserved for the cloud deployment phase. |
| **Usage Metering**         | ❌ Omitted   | Reporting usage metrics to Google Service Control is outside the scope of the basic auth flow setup.                                                                                                                                                                |
| **Database (Production)**  | ⚠️ JSON File | Using a local file (`clients_db.json`) is sufficient for development but not thread-safe or persistent across deployments. Will be replaced by Firestore.                                                                                                           |

## Prerequisites

Before running the code, ensure you have the following set up in Okta and Google Cloud:

### 1. Okta Setup

- **Okta Domain:** Your org's URL (e.g., `https://dev-123456.okta.com`).
- **API Token:** Create a generic API token (SSWS) in Okta (**Security** > **API** > **Tokens**). This token needs permissions to create and manage OIDC applications.
  - _Note:_ Ensure the token has sufficient privileges.

### 2. Google Cloud (For Testing)

- **Service Account:** Create a Service Account in your Google Cloud Project.
- **Permissions:** Grant this service account the `Service Account Token Creator` role (or ensure it can sign JWTs). This is used by the test script to mimic Google's signing key.
- **Local Auth:** Ensure your local environment is authenticated (`gcloud auth application-default login`) to use these credentials if running the test script locally.

## Setup & Replication

Follow these steps to replicate the setup locally.

### 1. Environment Configuration

Create a `.env` file in the `dcr/` directory (or root) with the following variables:

```bash
# dcr/.env

# Your Okta Org URL
OKTA_DOMAIN="https://your-org.okta.com"

# The API Token created in Okta
OKTA_API_TOKEN="your_okta_api_token"

# Identifier for your Agent (aud claim). Can be any URL for local testing.
PROVIDER_URL="https://mycompany.com"

# --- Testing Config ---
# Allow our custom service account to sign JWTs for testing?
ALLOW_TEST_ISSUER="true"
# The email of the service account used in test-dcr.py
TEST_SERVICE_ACCOUNT="your-test-sa@your-project.iam.gserviceaccount.com"
```

### 2. Install Dependencies

Ensure you have the required Python packages installed (FastAPI, Uvicorn, httpx, python-jose, google-cloud-iam, etc.).

```bash
uv sync
```

### 3. Run the DCR Server

Start the FastAPI server.

```bash
uv run dcr/main.py
```

_The server will start on port 8080._

### 4. Run the Test Script

In a separate terminal, run the test script. This script acts as "Google," signing a JWT and sending it to your local DCR endpoint.

```bash
uv run test-dcr/test-dcr.py
```

### 5. Verify Success

If successful:

1.  **Console Output:** The `test-dcr.py` script will print `Status Code: 200` and the JSON response containing a `client_id` and `client_secret`.
2.  **Okta:** Log in to your Okta Admin Console. Go to **Applications**. You should see a new Web Application named `Gemini Agent - Order <UUID>`.
3.  **Local DB:** Check `clients_db.json`. It should contain a new entry mapping the Order ID to the Okta Client ID.

## Gotchas

- **HTTPS Requirement:** Okta requires `https://` for the `OKTA_DOMAIN`. Double-check your `.env`.
- **Audience Mismatch:** The `aud` claim in the JWT _must_ match the `PROVIDER_URL` configured in the server. If `test-dcr.py` uses a different URL than `dcr/main.py`, validation will fail.
- **Service Account Permissions:** If the test script fails with "Permission denied" when signing the JWT, ensure your local credentials (or the SA running the script) has `iam.serviceAccounts.signBlob` permission.
