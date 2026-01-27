# A2A Agent with OAuth 2.0 Security (local)

This project demonstrates a secure Agent-to-Agent (A2A) communication architecture using OAuth 2.0. It features a **Remote Time Agent** (Resource Server) that requires authentication and specific scopes to access, and a **Test Client Agent** that performs the OAuth dance to acquire a valid token before calling the remote agent.

## Overview

The system consists of two main components:

1.  **Remote Time Agent (Server)**: A FastAPI-based A2A server that hosts the "Time Agent". It uses middleware to intercept requests, validate OAuth tokens via Okta introspection, and enforce custom scopes (`agent:time`).
2.  **Test Client Agent (Client)**: A CLI-based agent that:
    - Fetches the `agent-card.json` to discover security requirements.
    - Authenticates the user via Okta (Authorization Code flow).
    - Uses the obtained access token to make authenticated requests to the Remote Time Agent.

## Design Decisions

### 1. Custom A2A Server (FastAPI)

**Why?**
Instead of embedding authentication logic directly into the agent's business logic, we wrap the agent in a custom FastAPI server. This allows us to use **Middleware** (`OAuthMiddleware`) as a centralized point of security enforcement.

- **Separation of Concerns**: The agent logic (`get_current_time`) remains pure and unaware of OAuth details.
- **Security**: Authentication (Token Validity) and Authorization (Scopes) are enforced before the request ever reaches the agent executor.

### 2. Two Distinct Okta Applications

**Why?**
OAuth 2.0 best practices dictate separating the "Client" (who wants access) from the "Resource Server" (who hosts the data).

- **Client App (Web App)**: Used by the Test Client to initiate the login flow. It represents the user/application requesting access.
- **Resource Server App (API Services)**: Used by the Remote Time Agent to _validate_ tokens. It credentials allow it to call Okta's Introspection API to check if a token is valid and active.

### 3. Custom Scope (`agent:time`)

**Why?**
We use a custom scope to implement fine-grained access control. Merely having a valid token isn't enough; the token must grant the specific privilege to read time data. This prevents over-privileged access.

---

## Agent Card Technical Details

The `agent.json` file (also known as the Agent Card) describes the agent's capabilities and security requirements. Here's a breakdown of key components:

### 1. DCR (Dynamic Client Registration) Components

In your `agent.json`, the DCR configuration is handled via a specific **Extension** within the `capabilities` section:

```json
"extensions": [
  {
    "uri": "https://cloud.google.com/marketplace/docs/partners/ai-agents/setup-dcr",
    "params": {
      "target_url": "https://marketplace-handler-528009937268.us-central1.run.app/dcr"
    }
  }
]
```

- **What it does:** This extension signals to a marketplace or client that this agent supports **Dynamic Client Registration**. Instead of manually creating an Okta App for every single user or platform that wants to use your agent, DCR allows the client (the calling software) to programmatically register itself with your Identity Provider (via the `target_url` proxy) to get its own Client ID and Secret on the fly.
- **`uri`**: A unique identifier for the extension, pointing to the documentation or specification that defines how this DCR handshake works.
- **`params` -> `target_url`**: This is the critical endpoint. It points to a "DCR Handler" or Proxy (in this case, a Google Cloud Run service). When a platform (like the Google Cloud Marketplace) wants to connect to your agent, it sends a request to this URL to negotiate credentials securely.

### 2. OAuth Scopes

Scopes define the "permissions" the client is asking for. Your agent card lists three specific scopes in the `securitySchemes` and `security` sections:

```json
"scopes": {
  "agent:time": "Get the current time from the agent.",
  "openid": "Basic user profile.",
  "offline_access": "Refresh token."
}
```

- **`openid`**:
  - **Why:** This is the foundational scope for **OIDC (OpenID Connect)**. It tells Okta "I want to identify the user." Without this, you are just doing raw OAuth2 authorization without a standard identity layer. It returns an ID Token along with the Access Token.
- **`offline_access`**:
  - **Why:** This is required to get a **Refresh Token**. Access tokens are short-lived (e.g., 1 hour). If you want the agent client to be able to keep calling your agent tomorrow without forcing the user to log in again, the client needs a Refresh Token to silently get new Access Tokens. This is a requirement for GE.
- **`agent:time`**:
  - **Why:** This is your **Custom Functional Scope**. It represents the specific "power" to use the Time Agent.
  - **Security Principle:** "Least Privilege." If you had another agent that deleted data, you might have a scope like `agent:delete`. By separating them, a client with an `agent:time` token cannot accidentally or maliciously delete data, because the server (your FastAPI middleware) specifically checks for the `agent:time` string in the token.

### 3. Provider URLs (Authorization & Token Endpoints)

These URLs in the `securitySchemes` tell the client _where_ to go to log in:

```json
"authorizationUrl": "https://trial-6400907.okta.com/oauth2/ausyxkfala0nH5HxE697/v1/authorize",
"tokenUrl": "https://trial-6400907.okta.com/oauth2/ausyxkfala0nH5HxE697/v1/token"
```

- **`authorizationUrl`**:
  - **Function:** The client (e.g., the browser or CLI) opens this URL to show the user the login page.
  - **The "User" Interaction:** This is where the user enters their username/password and clicks "Allow" to grant the requested scopes.
- **`tokenUrl`**:

  - **Function:** This is a back-channel API endpoint. Once the user logs in, Okta gives the client a temporary "Code". The client sends that Code to this `tokenUrl` to exchange it for the actual Access Token (and Refresh Token).
  - **Why it's separate:** The authorization happens in the browser (front-channel), but the token exchange happens server-to-server (back-channel) for better security so the user never sees the raw token.

- **Note on the URL structure**: The segment `ausyxkfala0nH5HxE697` is the **Authorization Server ID**. This confirms you are using a Custom Authorization Server (or a specific instance of one), which is required to support custom scopes like `agent:time`.

## Okta Configuration (Critical)

You need **two** applications and a custom scope in your Okta "default" Authorization Server.

### Prerequisites

- An Okta Developer Account.
- Access to the **Admin Console**.

### Step 1: Configure Authorization Server & Scope

1.  Navigate to **Security** > **API** > **Authorization Servers**.
2.  Select the `default` server (ensure it exists and is active).
3.  **Create Scope**:
    - Go to the **Scopes** tab.
    - Click **Add Scope**.
    - Name: `agent:time`
    - Display phrase: "Access Time Agent"
    - Description: "Allows the agent to retrieve time information."
    - check **Include in public metadata** (Optional but helpful).
    - Click **Create**.

### Step 2: Configure Access Policy

1.  Still in the `default` Authorization Server, go to the **Access Policies** tab.
2.  Click **Add Policy** (or edit the `Default Policy`).
    - Name: "A2A Agent Policy".
    - Assign to: "All clients" (or specifically select the Client App created in Step 3).
3.  **Add Rule**:
    - Click **Add Rule**.
    - Name: "Allow Time Scope".
    - Grant types: **Authorization Code**.
    - Scopes requested: **Any scopes** (or specifically select `agent:time`).
    - Click **Create Rule**.
    - _Note: Without this, Okta will refuse to issue the `agent:time` scope._

### Step 3: Create Client App (For the Test Client)

1.  Navigate to **Applications** > **Applications** > **Create App Integration**.
2.  Sign-in method: **OIDC - OpenID Connect**.
3.  Application type: **Web Application**.
4.  Click **Next**.
5.  **Settings**:
    - App integration name: `A2A Client Agent`.
    - Grant type: Check **Authorization Code**.
    - Sign-in redirect URIs: `http://localhost:8085` (Matches the local server in `test_client_agent/agent.py`).
    - Assignments: Allow everyone (or specific users).
6.  Click **Save**.
7.  **Copy Credentials**: Note the `Client ID` and `Client secret`. You will use these for `OKTA_CLIENT_ID` and `OKTA_CLIENT_SECRET`.

### Step 4: Create Resource Server App (For the Remote Agent)

1.  Navigate to **Applications** > **Applications** > **Create App Integration**.
2.  Sign-in method: **OIDC - OpenID Connect**.
3.  Application type: **API Services** (Machine-to-Machine).
4.  Click **Next**.
5.  **Settings**:
    - App integration name: `A2A Resource Server`.
6.  Click **Save**.
7.  **Copy Credentials**: Note the `Client ID` and `Client secret`. You will use these for `OKTA_RS_CLIENT_ID` and `OKTA_RS_CLIENT_SECRET`.
    _Note: For API Services applications acting as Resource Servers for token introspection, direct user assignment is typically not required. Access control for the agent is managed by the scopes present in the access token, which users obtain via the Client App (Step 3)._

---

## Project Setup

### 1. Environment Variables

Create a `.env` file in `remote_a2a/remote_time_agent/.env` AND `test_client_agent/.env` (or set them globally).

**Required Variables:**

```ini
# Okta Domain (e.g., dev-123456.okta.com)
OKTA_DOMAIN=your-okta-domain.com
OKTA_AUTH_SERVER_ID=default

# --- For Remote Agent (Server) ---
# Credentials from Step 4 (API Services App)
OKTA_RS_CLIENT_ID=your_resource_server_client_id
OKTA_RS_CLIENT_SECRET=your_resource_server_client_secret

# --- For Test Client ---
# Credentials from Step 3 (Web App)
OKTA_CLIENT_ID=your_client_app_client_id
OKTA_CLIENT_SECRET=your_client_app_client_secret
```

### 2. Install Dependencies

Ensure you have `uv` installed.

```bash
uv sync
```

---

## Running the Project

You will need two terminal windows.

### Terminal 1: Start the Remote Agent Server

This starts the FastAPI server that protects the agent.

```bash
uv run uvicorn remote_a2a.remote_time_agent.agent:app --host 0.0.0.0 --port 8001 --reload
```

- **Verification**: Open `http://localhost:8001/`. You should see `{"message": "Remote Time Agent A2A Server is running with OAuth"}`.

### Terminal 2: Run the Test Client

This starts the CLI agent that will authenticate and talk to the server.

```bash
uv run test_client_agent/agent.py
```

**What happens next?**

1.  The CLI will print a URL: `👉 Please open this URL in your browser to authenticate: ...`
2.  **Open the link**. It will take you to your Okta login page.
3.  **Log in**.
4.  Okta will redirect you to `localhost:8085`. You should see "Authorization successful!".
5.  Return to the terminal. The client has exchanged the code for a token.
6.  **Interactive Chat**:
    ```text
    Starting interactive session: ...
    You: What time is it in London?
    Agent: The current time in London is ...
    ```

Note: please allow for the agent to respond before sending a follow up. This might take a few seconds. Otherwise you will receive wonky output.

---

## Troubleshooting & Gotchas

### 1. "Missing required scope: agent:time"

- **Error**: Server returns 403.
- **Cause**: The token was issued, but it didn't include the `agent:time` scope.
- **Fix**:
  - Ensure you requested the scope (the code does this automatically).
  - **Check Okta Access Policy (Step 2)**. This is the #1 cause. If the policy doesn't explicitly allow "Any scopes" or `agent:time`, Okta will silently strip it from the token.

### 2. "Token is not active" or Introspection Failed

- **Error**: Server returns 401 or 500 during introspection.
- **Cause**: The Resource Server credentials (`OKTA_RS_CLIENT_ID`) are incorrect, or the app doesn't have permission to introspect.
- **Fix**:
  - Verify `OKTA_RS_CLIENT_ID` and `OKTA_RS_CLIENT_SECRET` in `.env`.
  - Ensure the Resource Server app is "API Services" type.

### 3. "400 Bad Request" on Login Redirect

- **Cause**: The `redirect_uri` sent by the client (`http://localhost:8085`) does not _exactly_ match the "Sign-in redirect URIs" allowed in the Okta Client App settings.
- **Fix**: Go to Okta > Applications > [Your Client App] > General and add `http://localhost:8085`.
