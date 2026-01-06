import asyncio
from collections.abc import Sequence
import http.server
import json
import os
import threading
import sys
import urllib.parse
from urllib.parse import parse_qs
from urllib.parse import urlparse
import httpx
from dotenv import load_dotenv
import secrets  # Import secrets for generating a secure random state

from google.adk.agents.llm_agent import Agent
from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.auth import auth_credential
from google.adk.events.event import Event
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.sessions.session import Session
from google.adk.agents.invocation_context import InvocationContext
from google.genai import types as genai_types
from google.adk.agents.run_config import RunConfig

# Load environment variables from .env file
load_dotenv()


async def get_agent_card(httpx_client: httpx.AsyncClient,
                         agent_card_url: str) -> dict:
    """Fetches and parses the agent card JSON from the given URL."""
    try:
        print(f"Fetching agent card from: {agent_card_url}")
        response = await httpx_client.get(agent_card_url)
        response.raise_for_status()
        return response.json()
    except httpx.RequestError as e:
        print(f"ERROR: Failed to fetch agent card from {agent_card_url}: {e}")
        raise
    except json.JSONDecodeError as e:
        print(
            f"ERROR: Failed to decode agent card JSON from {agent_card_url}: {e}"
        )
        raise


async def get_authenticated_client(agent_card: dict) -> httpx.AsyncClient:
    """Gets an authenticated httpx.AsyncClient using OAuth2 authorization code flow.

  This function reads the agent card, performs an OAuth2 authorization code flow
  by starting a local server to capture the redirect, and then exchanges the
  authorization code for an access token. The resulting access token is used
  to create and return an httpx.AsyncClient with appropriate authorization
  headers.

  Args:
    agent_card: The parsed agent card JSON.

  Returns:
    An httpx.AsyncClient instance authenticated with the obtained access token.

  Raises:
    ValueError: If the agent card is missing necessary OAuth2 configuration or env variables are not set.
    RuntimeError: If the OAuth flow fails, e.g., state mismatch or no auth code.
    httpx.RequestError: If the token exchange fails.
  """
    security_schemes = agent_card.get("securitySchemes", {})
    oauth_scheme = security_schemes.get("oauth2", {})
    flows = oauth_scheme.get("flows", {})
    auth_code_flow = flows.get("authorizationCode", {})

    auth_url_base = auth_code_flow.get("authorizationUrl")
    token_url = auth_code_flow.get("tokenUrl")
    scopes = list(auth_code_flow.get("scopes", {}).keys())

    if not auth_url_base or not token_url:
        raise ValueError(
            "Agent card missing OAuth2 configuration (authorizationUrl or tokenUrl)"
        )

    client_id = os.getenv("OKTA_CLIENT_ID")
    client_secret = os.getenv("OKTA_CLIENT_SECRET")

    if not client_id:
        raise ValueError("OKTA_CLIENT_ID environment variable not set")
    if not client_secret:
        raise ValueError("OKTA_CLIENT_SECRET environment variable not set")

    redirect_uri = "http://localhost:8085"
    # Generate a random state value
    oauth_state = secrets.token_urlsafe(16)

    # Start local server to capture the code
    code_event = threading.Event()
    auth_code = None
    received_state = None

    class AuthHandler(http.server.BaseHTTPRequestHandler):

        def do_GET(self):
            nonlocal auth_code, received_state
            print("OAuth redirect received...")
            query_components = parse_qs(urlparse(self.path).query)
            received_state = query_components.get("state", [None])[0]

            if "code" in query_components:
                auth_code = query_components["code"][0]
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"Authorization successful! You can close this window.")
            else:
                error = query_components.get("error", ["Unknown error"])[0]
                error_description = query_components.get(
                    "error_description", ["No description"])[0]
                self.send_response(400)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(
                    f"<html><body><h1>OAuth Error</h1><p><b>Error:</b> {error}</p><p><b>Description:</b> {error_description}</p></body></html>"
                    .encode("utf-8"))
                print(f"OAuth Error: {error} - {error_description}")
            code_event.set()

        def log_message(self, format, *args):
            sys.stderr.write("%s - - [%s] %s\n" %
                             (self.address_string(),
                              self.log_date_time_string(), format % args))

    server = http.server.HTTPServer(("localhost", 8085), AuthHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    # Construct OAuth URL
    parsed_url = urllib.parse.urlparse(auth_url_base)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    query_params.update({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "response_type": "code",
        "state": oauth_state,  # Add the state parameter
    })
    for k, v in query_params.items():
        if isinstance(v, list) and len(v) == 1:
            query_params[k] = v[0]

    new_query = urllib.parse.urlencode(query_params, doseq=True)
    full_auth_url = urllib.parse.urlunparse(
        parsed_url._replace(query=new_query))

    print(
        f"\n👉 Please open this URL in your browser to authenticate:\n\n{full_auth_url}\n"
    )
    code_event.wait()
    server.shutdown()
    server_thread.join()

    if received_state != oauth_state:
        print(
            f"ERROR: OAuth state mismatch. Expected: {oauth_state}, Received: {received_state}"
        )
        raise RuntimeError("OAuth state mismatch.")

    if not auth_code:
        raise RuntimeError("Failed to obtain authorization code.")

    print(f"Auth code received: {auth_code[:10]}...")
    print("Exchanging code for token...")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                token_url,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": auth_code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
            )
            response.raise_for_status()
            token_data = response.json()
            access_token = token_data["access_token"]
            print("Token exchange successful!")
        except httpx.RequestError as e:
            print(f"ERROR: Token exchange request failed: {e}")
            raise
        except httpx.HTTPStatusError as e:
            print(
                f"ERROR: Token exchange failed with status {e.response.status_code}: {e.response.text}"
            )
            raise
        except json.JSONDecodeError as e:
            print(f"ERROR: Failed to decode token response JSON: {e}")
            raise
        except KeyError as e:
            print(
                f"ERROR: 'access_token' not found in token response: {token_data}"
            )
            raise

    headers = {"Authorization": f"Bearer {access_token}"}
    return httpx.AsyncClient(headers=headers, timeout=600.0)


async def create_root_agent():
    """Creates the root agent and its sub-agents, handling OAuth for the remote agent."""
    agent_card_base_url = "http://localhost:8001/a2a/remote_time_agent/"  # TRAILING SLASH
    agent_card_url = f"{agent_card_base_url}.well-known/agent-card.json"

    try:
        async with httpx.AsyncClient() as temp_client:
            agent_card = await get_agent_card(temp_client, agent_card_url)
    except Exception as e:
        print(f"Cannot proceed without agent card. Exiting.")
        return None

    try:
        authenticated_httpx_client = await get_authenticated_client(agent_card)
    except Exception as e:
        print(f"Authentication failed: {e}")
        return None

    root_agent = RemoteA2aAgent(
        name="time_agent",
        description=
        "Agent that retrieves the current time in a specified city.",
        agent_card=agent_card_url,
        httpx_client=authenticated_httpx_client,
    )

    # root_agent = Agent(
    #     model='gemini-3-flash-preview',
    #     name='root_agent',
    #     description=
    #     "An agent that can get the current time in various cities using the get_time_agent.",
    #     instruction=
    #     ("You are a helpful assistant that can retrieve the current time in various cities. "
    #      "To get the current time in a city, use the 'get_time_agent' A2A agent."
    #      ),
    #     sub_agents=[get_time_agent],
    # )
    print("Root agent created successfully with authenticated remote agent.")
    return root_agent


async def main():
    root_agent = await create_root_agent()
    if not root_agent:
        return

    session_id = f"session-{secrets.token_hex(4)}"
    print(f"Starting interactive session: {session_id}")
    session = Session(id=session_id,
                      app_name="test-client",
                      user_id="user-test")
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=session.app_name,
        user_id=session.user_id,
        session_id=session.id,
    )

    print("Type 'quit' to end the conversation.")
    while True:
        user_input = input("You: ")
        if user_input.lower() == 'quit':
            print("Ending session.")
            break

        user_event = Event(
            author="user",
            content=genai_types.Content(
                parts=[genai_types.Part.from_text(text=user_input)]),
        )
        # Append user event to the session object AND the service's memory
        await session_service.append_event(session, user_event)

        context = InvocationContext(
            session_service=session_service,
            session=session,
            agent=root_agent,
            invocation_id=f"inv-{secrets.token_hex(4)}",
            run_config=RunConfig(),
        )

        print("Agent:", end=" ", flush=True)
        async for event in root_agent.run_async(context):
            if event.author == root_agent.name and event.content:
                for part in event.content.parts:
                    if part.text:
                        print(part.text, end="", flush=True)
        print("\n")  # Newline after agent response


if __name__ == "__main__":
    asyncio.run(main())
