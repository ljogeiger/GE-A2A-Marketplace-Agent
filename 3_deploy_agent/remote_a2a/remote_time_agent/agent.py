import logging
from datetime import datetime
from typing import Dict, Any
from dotenv import load_dotenv

import pytz
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import httpx
import os
import json
from functools import wraps
import uuid

# ADK and A2A core components
from google.adk.agents.llm_agent import Agent
from google.adk.tools import FunctionTool, ToolContext
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory import InMemoryMemoryService
from google.genai import types as genai_types
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor, A2aAgentExecutorConfig
from google.adk.runners import Runner

from a2a.server.apps.jsonrpc.starlette_app import A2AStarletteApplication, AGENT_CARD_WELL_KNOWN_PATH
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    TaskState,
    TextPart,
    Part,
    UnsupportedOperationError,  # Import for cancel
    AgentCard,  # Import for loading from file
)
from a2a.utils import new_agent_text_message
from a2a.utils.errors import ServerError  # Import for cancel
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

load_dotenv()

# Setup Okta
OKTA_DOMAIN = os.environ.get("OKTA_DOMAIN", "trial-6400907.okta.com").replace("https://", "").replace("http://", "")
OKTA_AUTH_SERVER_ID = os.environ.get("OKTA_AUTH_SERVER_ID", "default")
INTROSPECTION_URL = f"https://{OKTA_DOMAIN}/oauth2/{OKTA_AUTH_SERVER_ID}/v1/introspect"
# These should be the credentials of the *A2A agent application itself* in Okta
# if using client_credentials grant for introspection.
# However, introspection usually uses the CLIENT_ID of the *caller*
# but is authenticated by the Resource Server (this agent).
# Let's assume this agent has its own credentials to call the introspection endpoint.
RESOURCE_SERVER_CLIENT_ID = os.environ.get("OKTA_RS_CLIENT_ID")
RESOURCE_SERVER_CLIENT_SECRET = os.environ.get("OKTA_RS_CLIENT_SECRET")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Debug logging for configuration
if not RESOURCE_SERVER_CLIENT_ID:
    logger.error("OKTA_RS_CLIENT_ID is not set in environment variables!")
else:
    logger.info(
        f"OKTA_RS_CLIENT_ID is set: {RESOURCE_SERVER_CLIENT_ID[:4]}...")

if not RESOURCE_SERVER_CLIENT_SECRET:
    logger.error("OKTA_RS_CLIENT_SECRET is not set in environment variables!")
else:
    logger.info("OKTA_RS_CLIENT_SECRET is set.")

# Initialize components globally for reuse (caching)
geolocator = Nominatim(user_agent="city_time_app")
tf = TimezoneFinder()


def get_current_time(city: str) -> Dict[str, Any]:
    """
    Retrieves the current time for any city globally.
    Uses geocoding to find coordinates and timezonefinder for IANA lookup.
    """
    try:
        # 1. Geocode city name to coordinates
        location = geolocator.geocode(city, language='en', timeout=10)

        if not location:
            logger.warning(f"Could not resolve location for city: {city}")
            return {"status": "error", "message": "Location not found"}

        # 2. Find the timezone name from coordinates
        timezone_str = tf.timezone_at(lng=location.longitude,
                                      lat=location.latitude)

        if not timezone_str:
            return {
                "status": "error",
                "message": "Timezone could not be determined"
            }

        # 3. Calculate time using pytz
        timezone = pytz.timezone(timezone_str)
        now = datetime.now(timezone)

        return {
            "status": "success",
            "data": {
                "input_city": city,
                "resolved_address": location.address,
                "timezone": timezone_str,
                "time_24h": now.strftime("%H:%M"),
                "time_12h": now.strftime("%I:%M %p"),
                "date": now.strftime("%Y-%m-%d"),
                "utc_offset": now.strftime("%z")
            }
        }

    except Exception as e:
        logger.error(f"Error fetching time for {city}: {str(e)}")
        return {"status": "error", "message": "Internal server error"}


root_agent = Agent(
    model='gemini-3-flash-preview',
    name='remote_time_agent',
    description="Tells the current time in a specified city.",
    instruction=
    "You are a helpful assistant that tells the current time in cities. Use the 'get_current_time' tool for this purpose.",
    tools=[get_current_time],
)

# # --- ADK Agent Executor for A2A ---
# class AdkAgentExecutor(AgentExecutor):

#     def __init__(self, agent: Agent):
#         self.agent = agent
#         self.runner = Runner(
#             app_name=self.agent.name,
#             agent=self.agent,
#             session_service=InMemorySessionService(),
#             artifact_service=InMemoryArtifactService(),
#             memory_service=InMemoryMemoryService(),
#         )

#     async def execute(self, context: RequestContext,
#                       event_queue: EventQueue) -> None:
#         if not context.message:
#             return

#         user_id = "a2a_user"
#         session_id = context.context_id or str(uuid.uuid4())
#         updater = TaskUpdater(event_queue, context.task_id, session_id)

#         try:
#             await updater.submit()
#             await updater.start_work()

#             query = context.get_user_input()
#             if query is None:
#                 await updater.update_status(
#                     TaskState.FAILED,
#                     message=new_agent_text_message("No text input provided."),
#                     final=True)
#                 return

#             content = genai_types.Content(role='user',
#                                           parts=[genai_types.Part(text=query)])

#             session = await self.runner.session_service.get_session(
#                 app_name=self.runner.app_name,
#                 user_id=user_id,
#                 session_id=session_id,
#             ) or await self.runner.session_service.create_session(
#                 app_name=self.runner.app_name,
#                 user_id=user_id,
#                 session_id=session_id,
#             )

#             final_event = None
#             async for event in self.runner.run_async(session_id=session.id,
#                                                      user_id=user_id,
#                                                      new_message=content):
#                 if event.is_final_response():
#                     final_event = event
#                     break

#             if final_event and final_event.content and final_event.content.parts:
#                 response_text = "".join(part.text
#                                         for part in final_event.content.parts
#                                         if hasattr(part, 'text') and part.text)
#                 if response_text:
#                     await updater.add_artifact(
#                         [TextPart(text=response_text)],
#                         name='result',
#                     )
#                     await updater.complete()
#                 else:
#                     await updater.update_status(
#                         TaskState.FAILED,
#                         message=new_agent_text_message(
#                             'Agent response had no text content.'),
#                         final=True)
#             else:
#                 await updater.update_status(
#                     TaskState.FAILED,
#                     message=new_agent_text_message(
#                         'Failed to get a final response from agent.'),
#                     final=True)

#         except Exception as e:
#             logger.error(f"Error in AdkAgentExecutor: {e}", exc_info=True)
#             await updater.update_status(
#                 TaskState.FAILED,
#                 message=new_agent_text_message(f"An error occurred: {str(e)}"),
#                 final=True,
#             )

#     async def cancel(self, context: RequestContext, event_queue: EventQueue):
#         # Basic cancel implementation
#         logger.info(f"Cancel requested for task {context.task_id}")
#         updater = TaskUpdater(event_queue, context.task_id, context.context_id)
#         await updater.update_status(
#             TaskState.CANCELED,
#             message=new_agent_text_message("Task cancellation requested."),
#             final=True)
#         # In a real scenario, you might need to add logic to stop any ongoing ADK agent execution if possible.
#         # For this example, we just mark the task as CANCELED.


# --- Auth Middleware ---
class OAuthMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):
        a2a_base_path = "/a2a/remote_time_agent"
        # Log the path for debugging visibility in Cloud Run logs
        print(f"Incoming request path: {request.url.path}")

        if request.url.path.startswith(a2a_base_path):
            # Allow public access to the agent card (discovery)
            # Checking for presence of standard strings to avoid slash ambiguity
            if ".well-known/agent.json" in request.url.path or "agent.json" in request.url.path:
                return await call_next(request)

            auth_header = request.headers.get("Authorization")
            print(f"DEBUG: Auth Header: {auth_header}")

            if not auth_header or not auth_header.startswith("Bearer "):
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": "Missing or invalid Authorization header"
                    })
            token = auth_header.split(" ")[1]

            if not RESOURCE_SERVER_CLIENT_ID or not RESOURCE_SERVER_CLIENT_SECRET:
                logger.error(
                    "Cannot perform introspection: Missing Okta credentials.")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error":
                        "Server misconfiguration: Missing auth credentials"
                    })

            async with httpx.AsyncClient() as client:
                try:
                    # Using print to ensure visibility in Cloud Run stdout
                    print(f"DEBUG: Introspection URL: {INTROSPECTION_URL}")
                    print(f"DEBUG: Token (len): {len(token)}")
                    print(
                        f"DEBUG: Client ID Type: {type(RESOURCE_SERVER_CLIENT_ID)}"
                    )
                    print(
                        f"DEBUG: Client Secret Type: {type(RESOURCE_SERVER_CLIENT_SECRET)}"
                    )

                    # Ensure they are strings
                    rs_id = str(RESOURCE_SERVER_CLIENT_ID)
                    rs_secret = str(RESOURCE_SERVER_CLIENT_SECRET)

                    print(
                        f"DEBUG: Using Auth: {rs_id[:4]}... / (secret len: {len(rs_secret)})"
                    )

                    response = await client.post(INTROSPECTION_URL,
                                                 data={
                                                     'token':
                                                     token,
                                                     'token_type_hint':
                                                     'access_token'
                                                 },
                                                 auth=(rs_id, rs_secret))
                    response.raise_for_status()
                    token_info = response.json()

                    if not token_info.get("active"):
                        return JSONResponse(
                            status_code=401,
                            content={"error": "Token is not active"})

                    scopes = token_info.get("scope", "").split(" ")
                    if "agent:time" not in scopes:
                        return JSONResponse(
                            status_code=403,
                            content={
                                "error": "Missing required scope: agent:time"
                            })
                    request.state.token_info = token_info
                except httpx.HTTPStatusError as e:
                    print(
                        f"Introspection HTTP error: {e.response.status_code} - {e.response.text}"
                    )
                    return JSONResponse(status_code=e.response.status_code,
                                        content={
                                            "error":
                                            "Token introspection failed",
                                            "detail": e.response.text
                                        })
                except Exception as e:
                    print(f"Auth Middleware error: {e}")
                    return JSONResponse(
                        status_code=500,
                        content={"error": "Authentication processing error"})
        return await call_next(request)


# --- FastAPI App Setup ---
app = FastAPI(title="Remote Time Agent Server")
app.add_middleware(OAuthMiddleware)

# --- Load Agent Card from file ---
agent_card_path = os.path.join(os.path.dirname(__file__), ".well-known",
                               "agent.json")
try:
    with open(agent_card_path, "r") as f:
        agent_card_data = json.load(f)
    agent_card = AgentCard(**agent_card_data)
    logger.info(f"Agent card loaded from {agent_card_path}")
except Exception as e:
    logger.error(f"Failed to load agent card from {agent_card_path}: {e}")
    raise

# --- A2A Application ---
# Define the Agent Executor
a2a_execution_config = A2aAgentExecutorConfig()

# ADK Runner
runner = Runner(
    app_name=root_agent.name,
    agent=root_agent,
    session_service=InMemorySessionService(),
    artifact_service=InMemoryArtifactService(),
    memory_service=InMemoryMemoryService(),
)

# using prebuilt A2aAgentExecutor (not custom AdkAgentExecutor)
agent_executor = A2aAgentExecutor(runner=runner)

# A2A Request Handler
request_handler = DefaultRequestHandler(
    agent_executor=agent_executor,
    task_store=InMemoryTaskStore(),
)

a2a_app = A2AStarletteApplication(
    agent_card=agent_card,
    http_handler=request_handler,
)

# Mount the A2A app within FastAPI
app.mount("/a2a/remote_time_agent", app=a2a_app.build())


@app.get("/")
def read_root():
    return {"message": "Remote Time Agent A2A Server is running with OAuth"}


if __name__ == "__main__":
    uvicorn.run(app, host='0.0.0.0', port=8001)
