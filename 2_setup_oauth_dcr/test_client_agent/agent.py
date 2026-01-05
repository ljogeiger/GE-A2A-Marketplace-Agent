from google.adk.agents.llm_agent import Agent
from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.auth import auth_credential
import os

OKTA_CLIENT_ID = os.environ.get("OKTA_CLIENT_ID")
OKTA_CLIENT_SECRET = os.environ.get("OKTA_CLIENT_SECRET")

if not OKTA_CLIENT_ID or not OKTA_CLIENT_SECRET:
    raise ValueError(
        "Please set OKTA_CLIENT_ID and OKTA_CLIENT_SECRET environment variables"
    )

# This credential object is used by the ADK framework (when running adk web)
# to interact with your Okta authorization server.
auth_cred = auth_credential.AuthCredential(
    auth_type=auth_credential.AuthCredentialTypes.OPEN_ID_CONNECT,
    oauth2=auth_credential.OAuth2Auth(
        client_id=OKTA_CLIENT_ID,
        client_secret=OKTA_CLIENT_SECRET,
    ),
)

get_time_agent = RemoteA2aAgent(
    name="time_agent",
    description="Agent that retrieves the current time in a specified city.",
    agent_card=
    (f"http://localhost:8001/a2a/remote_time_agent{AGENT_CARD_WELL_KNOWN_PATH}"
     ),
    auth_credential=auth_cred,
)

root_agent = Agent(
    model='gemini-3-flash-preview',
    name='root_agent',
    description=
    "An agent that can get the current time in various cities using the get_time_agent.",
    instruction=
    ("You are a helpful assistant that can retrieve the current time in various cities. "
     "To get the current time in a city, use the 'get_time_agent' A2A agent."),
    sub_agents=[get_time_agent],
)
