# 1_add_a2a: Agent-to-Agent (A2A) Communication

This directory demonstrates how to set up Agent-to-Agent (A2A) communication using the Google ADK. Instead of a single monolithic agent, we split the functionality into a **client agent** and a **remote service agent** (remote_time_agent).

## Project Structure

- **`remote_a2a/remote_time_agent/`**: Contains the "service" agent.
  - `agent.py`: Defines the `remote_time_agent` which has the tool `get_current_time` (same logic as in `0_agent_setup`).
  - `agent.json`: Metadata defining the agent's capabilities for A2A discovery.
  - `.env`: Configuration for the remote agent.
- **`test_client_agent/`**: Contains the "client" agent.
  - `agent.py`: Defines the `root_agent`. Instead of having the time tool locally, it imports `RemoteA2aAgent` and connects to the `remote_time_agent` running on `localhost`.

## Differences from `0_agent_setup`

In `0_agent_setup`, we had a single agent that contained both the LLM instructions and the Python tool (`get_current_time`) in the same process.

In `1_add_a2a`, we decouple them:

1.  **Remote Execution**: The time-telling logic runs in a separate process (`remote_time_agent`) exposed via an HTTP server.
2.  **Client Delegation**: The `test_client_agent` doesn't know _how_ to calculate the time; it only knows _who_ to ask (`get_time_agent`).
3.  **Scalability**: This pattern allows you to build opaque specialized agents (micro-agents) that can be reused by multiple client agents.

## Getting Started

You will need two terminal windows to run this setup: one for the remote agent server and one for the client agent.

### Prerequisites

Ensure you have [uv](https://github.com/astral-sh/uv) installed.

### 1. Configure Environment Variables

Create or update the `.env` files in both `remote_a2a/remote_time_agent/` and `test_client_agent/` with the following content:

```
GOOGLE_GENAI_USE_VERTEXAI=1
GOOGLE_CLOUD_PROJECT=<project-id>
GOOGLE_CLOUD_LOCATION=global
```

### 2. Install Dependencies

From the `1_add_a2a/` directory, run:

```bash
uv sync
```

This will install all necessary dependencies for both agents.

### 3. Start the Remote Agent Server

In your first terminal, from the `1_add_a2a/` directory, run:

```bash
uv run adk api_server --a2a --port 8001 remote_a2a/
```

This starts the A2A server on port 8001, hosting the agents found in the `remote_a2a/` directory.

### 4. Start the Client Agent

In your second terminal, from the `1_add_a2a/` directory, run the client agent which connects to the server you just started:

```bash
uv run adk web
```

Click into the localhost web UI and select the "test_client_agent" from the dropdown.

This command will launch the web UI for the client agent. Once it's ready, you can ask queries like:

> "What time is it in Tokyo?"

The `root_agent` (your `test_client_agent`) will receive this request, recognize it needs time information, and delegate the task to the `remote_time_agent` running on port 8001.

## Design Desicions

ADK supports two ways of exposing an agent via A2A:

1. to_a2a()
2. By creating your own agent card (agent.json) and hosting it using adk api_server --a2a

I chose #2 because I wanted to use ADK Web to debug my remote agent. This isn't the most important decision, but I do recommend explicitly defining your AgentCard rather than relying on the automated feature to generate one for you based on the metadata.
Read more [here](https://google.github.io/adk-docs/a2a/quickstart-exposing/).
