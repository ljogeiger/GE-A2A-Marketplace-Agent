from google.adk.agents.llm_agent import Agent

import logging
from datetime import datetime
from typing import Dict, Any

import pytz
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder

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
