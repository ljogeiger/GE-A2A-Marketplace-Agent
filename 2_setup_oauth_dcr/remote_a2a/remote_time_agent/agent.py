from google.adk.agents.llm_agent import Agent
from google.adk.tools import FunctionTool, ToolContext
from a2a.server.agenhttpx import AdkAgentToA2AExecutor
from a2a.server.apps.jsonrpc.starlette_app import A2AStarletteApplication, AGENT_CARD_WELL_KNOWN_PATH
from a2a.server.request_handlers import DefaultRequestHandler

import logging
from datetime import datetime
from typing import Dict, Any

import pytz
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder

from fastapi import FastAPI, Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import httpx
import os
import json

# Setup Okta
OKTA_DOMAIN = os.environ.get("OKTA_DOMAIN", "trial-6400907.okta.com")
OKTA_AUTH_SERVER_ID = os.environ.get("OKTA_AUTH_SERVER_ID", "default")
INTROSPECTION_URL = f"https://{OKTA_DOMAIN}/oauth2/{OKTA_AUTH_SERVER_ID}/v1/introspect"
# These should be the credentials of the *A2A agent application itself* in Okta
# if using client_credentials grant for introspection.
# However, introspection usually uses the CLIENT_ID of the *caller*
# but is authenticated by the Resource Server (this agent).
# Let's assume this agent has its own credentials to call the introspection endpoint.
RESOURCE_SERVER_CLIENT_ID = os.environ.get("OKTA_RS_CLIENT_ID")
RESOURCE_SERVER_CLIENT_SECRET = os.environ.get("OKTA_RS_CLIENT_SECRET")

# Initialize components globally for reuse (caching)
geolocator = Nominatim(user_agent="city_time_app")
tf = TimezoneFinder()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


# --- Auth Middleware ---
# --- Auth Middleware ---
class OAuthMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):
        a2a_base_path = "/a2a/remote_time_agent"
        if request.url.path.startswith(a2a_base_path):
            if request.url.path.endswith(AGENT_CARD_WELL_KNOWN_PATH):
                return await call_next(request)

            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": "Missing or invalid Authorization header"
                    })
            token = auth_header.split(" ")[1]

            async with httpx.AsyncClient() as client:
                try:
                    print(f"Introspecting token at: {INTROSPECTION_URL}")
                    response = await client.post(
                        INTROSPECTION_URL,
                        data={
                            'token': token,
                            'token_type_hint': 'access_token'
                        },
                        auth=(RESOURCE_SERVER_CLIENT_ID,
                              RESOURCE_SERVER_CLIENT_SECRET))
                    if response.status_code == 401:
                        return JSONResponse(
                            status_code=401,
                            content={
                                "error":
                                "Unauthorized to call introspection endpoint",
                                "detail": response.text
                            })
                    if response.status_code == 400:
                        return JSONResponse(
                            status_code=400,
                            content={
                                "error":
                                "Bad request to introspection endpoint",
                                "detail": response.text
                            })
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

                    request.state.scopes = scopes
                    request.state.token_info = token_info
                except httpx.HTTPStatusError as e:
                    print(
                        f"Introspection HTTP error: {e.response.status_code} - {e.response.text}"
                    )
                    return JSONResponse(status_code=500,
                                        content={
                                            "error":
                                            "Token introspection failed",
                                            "detail": str(e)
                                        })
                except Exception as e:
                    print(f"Auth Middleware error: {e}")
                    return JSONResponse(
                        status_code=500,
                        content={"error": "Authentication processing error"})
        return await call_next(request)


# --- FastAPI App ---
app = FastAPI()

# Add the middleware
app.add_middleware(OAuthMiddleware)

# --- A2A Application ---
agent_executor = AdkAgentToA2AExecutor(agent=root_agent)
a2a_app = A2AStarletteApplication(agent_executor=agent_executor,
                                  request_handler=DefaultRequestHandler(),
                                  path="/a2a/remote_time_agent",
                                  allow_agent_card=True)

# Mount the A2A app
app.mount("/a2a/remote_time_agent", app=a2a_app)


@app.get("/")
def read_root():
    return {"message": "Remote Time Agent A2A Server is running"}


# To run this server:
# Set environment variables: OKTA_DOMAIN, OKTA_RS_CLIENT_ID, OKTA_RS_CLIENT_SECRET
# uvicorn main:app --host 0.0.0.0 --port 8001 --reload
