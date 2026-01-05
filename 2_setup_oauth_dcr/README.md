1. Set up two Okta apps. One to be the Oauth for agent access, the other to access the Okta API (for token introspection).
2. Modify AgentCard to include SecuritySchema
3. Create custom a2a server to support best practices for Oauth with A2A.
4. Modify the test client to support authenticated calls to remote agent

## 1 - Okta App Setup

Okta App for Agent to retrieve end user credentials:

1. Log in to your Okta Admin Console.
2. Navigate to Applications > Applications.
3. Click on Create App Integration.
   Select OIDC - OpenID Connect as the Sign-in method.
   Choose Web Application as the Application type. Click Next.
   App integration name: Give your application a descriptive name (e.g., "My AI Agent").
   Grant type: Ensure Authorization Code is selected. This is the standard and most secure flow for this type of application. You may also need/want Refresh Token.
   Sign-in redirect URIs: This is crucial for local testing. Add a URI like http://localhost:8080/callback or a similar path on your local machine where your agent will handle the OAuth callback. You can add more later for deployed environments.
   Sign-out redirect URIs: (Optional for now) You can configure where to redirect after logout.
   Assignments: Control which users or groups can use this application. Start with a test user or group.
   Click Save.

Okta App to for Agent Backend:

1. Log in to Okta Admin Console: Access your Okta administrative interface.
   Create New App Integration:
   Navigate to Applications > Applications.
   Click on Create App Integration.
   For the sign-in method, select OIDC - OpenID Connect.
   For the Application type, choose API Services. This type is intended for machine-to-machine communication where the application needs to access Okta APIs directly.
   Click Next.
   Configure the Application:
   App integration name: Give it a descriptive name, for example, "RemoteTimeAgent Service" or "A2A Agent Backend".
   Click Save.
   Client Credentials:
   After saving, you'll find the Client ID and Client secret on the application's "General" tab. These are the values you will use for OKTA_RS_CLIENT_ID and OKTA_RS_CLIENT_SECRET in your FastAPI server's environment variables.
   https://developer.okta.com/docs/api/openapi/okta-oauth/oauth/tag/CustomAS/#tag/CustomAS/operation/introspectCustomAS
   Client Authentication for Introspection Call:
   Your middleware code uses auth=(RESOURCE_SERVER_CLIENT_ID, RESOURCE_SERVER_CLIENT_SECRET) in the httpx.post call to the introspection endpoint. This typically means the client ID and secret are sent as an HTTP Basic Auth header. Ensure the "Client authentication" method for this Okta application is set to Client Secret (Basic). This is usually the default for API Services apps.

   we are using the default authorization server. otherwise we would have to specify which version.

## Why a Custom A2A Server is Better for Production:

_Centralized Security Enforcement_: You can implement middleware (as in a FastAPI or Starlette application) to intercept all incoming requests to your agent's A2A endpoints. This middleware becomes the single point of control for:

Extracting the Authorization: Bearer token.
Validating the token with Okta (e.g., via introspection).
Checking for the presence of required OAuth scopes based on the skill being invoked. Requests that fail validation are rejected before they reach the core ADK agent logic.
Clear Separation of Concerns: The custom server approach separates the web serving, protocol handling (A2A), and security logic from the agent's skill implementations.

Your FastAPI/Starlette code handles the auth.
The A2AStarletteApplication from the A2A library handles the A2A protocol.
Your ADK Agent and Tool definitions focus purely on the business logic of the skills.
Improved Maintainability & Auditing: Auth logic is consolidated in the middleware, making it easier to update, audit, and test. Changes to your auth policy don't require touching every skill function.

Flexibility: A custom server allows you to easily add other server-level features like:

Rate limiting.
Enhanced logging and monitoring.
Request/response transformation.
Token caching strategies to reduce introspection calls to Okta.
