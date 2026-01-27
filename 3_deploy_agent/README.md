# Remote Time Agent - A2A Deployment

This directory contains the deployment configuration and source code for the **Remote Time Agent**, a Google Cloud Run service that implements the Agent to Agent (A2A) protocol. The agent provides a tool to retrieve the current time for a given city, secured via Okta OAuth2.

## Overview

The agent is built using:

- **FastAPI**: For the HTTP server.
- **Google ADK (Agent Development Kit)**: For defining the agent and tools.
- **A2A SDK**: For implementing the A2A protocol endpoints.
- **Google Cloud Run**: For serverless container deployment.

## Project Structure

```
.
├── deploy.sh               # Main deployment script (handles URL generation & agent.json updates, uses Secret Manager)
├── simple_deploy.sh        # Simplified deployment script (uses Secret Manager, good for CI/CD)
└── remote_a2a/             # Application source
    ├── Dockerfile          # Container definition
    ├── requirements.txt    # Python dependencies
    └── remote_time_agent/  # Agent code
        ├── agent.py        # Main application logic
        └── .well-known/    # Discovery metadata
            └── agent.json  # Agent Card served by the application
```

## Prerequisites

Before deploying, ensure you have:

1.  **Google Cloud SDK (`gcloud`)** installed and authenticated.
2.  **Python 3** installed (used by the deployment script for parsing).
3.  A **Google Cloud Project** created and active.

## Configuration

### 1. Secrets Configuration

Both `deploy.sh` and `simple_deploy.sh` are configured to use **Google Secret Manager** for sensitive environment variables. Before deployment, you **must** create the following secrets in your Google Cloud Project:

*   `OKTA_DOMAIN`
*   `OKTA_AUTH_SERVER_ID`
*   `OKTA_RS_CLIENT_ID`
*   `OKTA_RS_CLIENT_SECRET`

For details on how to set these up in Okta and then in Google Secret Manager, refer to the explanation on [why Okta RS Client credentials are needed](#why-okta-rs-client-credentials-are-needed) (note: this is a conceptual link to a previous message, not a markdown anchor).

### 2. Agent Metadata

The `remote_a2a/remote_time_agent/.well-known/agent.json` file defines the agent's capabilities. The `deploy.sh` script automatically updates the `url` and `target_url` fields in this file to match your deployed Cloud Run instance.

## Deployment

### Method 1: Full Deployment (Recommended for first run)

Use `deploy.sh` for the initial deployment. This script performs a "two-step" deployment to resolve the circular dependency where the agent needs to know its own URL in its metadata. It now uses secrets defined in Google Secret Manager.

1.  **Initial Deploy**: Deploys the container to generate a Cloud Run Service URL.
2.  **Update Metadata**: Updates `remote_a2a/remote_time_agent/.well-known/agent.json` with the new URL.
3.  **Final Deploy**: Redeploys the container with the correct metadata.

**Usage:**

```bash
./deploy.sh
```

_Note: Ensure you have selected your Google Cloud project via `gcloud config set project [PROJECT_ID]` before running._

### Method 2: Simple Deployment

Use `simple_deploy.sh` for subsequent updates where the URL hasn't changed, or in CI/CD pipelines. This script also uses secrets from Google Secret Manager.

**Usage:**

```bash
./simple_deploy.sh
```

## Design Decisions & Gotchas

### Circular Dependency

The `agent.json` must serve the full URL of the agent (e.g., `https://.../a2a/remote_time_agent/`). However, the Cloud Run URL is not known until _after_ deployment. `deploy.sh` handles this by deploying twice. **Do not manually edit the URL in `agent.json` if using this script.**

### Secrets Management

Both `deploy.sh` and `simple_deploy.sh` now rely on **Google Secret Manager** to securely provide sensitive configuration to the Cloud Run service. You must manually create the required secrets in your Google Cloud project before deployment.

### Authentication

The agent enforces OAuth2 authentication using Okta.

- **Middleware**: Custom middleware in `agent.py` intercepts requests to `/a2a/remote_time_agent`.
- **Introspection**: It validates the Bearer token against Okta's introspection endpoint.
- **Scope**: Requires the `agent:time` scope.

### Statelessness

The agent uses `InMemorySessionService` and `InMemoryTaskStore`.

- **Implication**: If the Cloud Run instance scales down to zero or crashes, active conversation sessions and task states are lost. For production, replace these with persistent storage (e.g., Firestore or Redis).

## Security

1.  **Public Endpoint**: The Cloud Run service is deployed with `--allow-unauthenticated`. This is required for the A2A protocol handshake, but the application layer enforces authentication via the OAuth middleware.
2.  **Discovery**: The `.well-known/agent.json` path is public to allow other agents to discover this service's capabilities.
3.  **Token Validation**: All functional endpoints require a valid Okta token with the correct scope.

## Verification

After deployment, you can verify the service is running:

1.  **Check Discovery Endpoint**:

    ```bash
    curl https://<YOUR-SERVICE-URL>/a2a/remote_time_agent/.well-known/agent.json
    ```

    Should return the JSON agent card.

2.  **Check Root**:
    ```bash
    curl https://<YOUR-SERVICE-URL>/
    ```
    Should return `{"message": "Remote Time Agent A2A Server is running with OAuth"}`.
