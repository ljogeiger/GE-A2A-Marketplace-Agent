from google.adk.agents.llm_agent import Agent
from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

get_time_agent = RemoteA2aAgent(
    name="time_agent",
    description="Agent that retrieves the current time in a specified city.",
    agent_card=
    (f"http://localhost:8001/a2a/remote_time_agent{AGENT_CARD_WELL_KNOWN_PATH}"
     ),
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
