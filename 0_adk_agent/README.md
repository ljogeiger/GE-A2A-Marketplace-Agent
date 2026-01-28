# Time Agent - GE A2A Marketplace

This project implements an AI agent capable of providing the current time for any city worldwide. It is built using the Google ADK (Agent Development Kit) and leverages the `gemini-3-flash-preview` model.

## Features

- **Global Time Lookup:** Instantly find the current time in any city.
- **Smart Geolocation:** Uses `geopy` and `timezonefinder` to accurately determine timezones based on city names.
- **Interactive Web Interface:** Powered by ADK's web UI.

## Prerequisites

- **Python:** Version 3.13
- **uv:** An extremely fast Python package installer and resolver.

## Setup & Installation

This project uses `uv` for dependency management.

1.  **Install `uv`** (if not already installed):
    Please refer to the [official uv documentation](https://docs.astral.sh/uv/) for installation instructions specific to your OS.

2.  **Sync Dependencies:**
    The project dependencies are defined in `pyproject.toml` and locked in `uv.lock`. `uv` will automatically handle environment creation and dependency installation when you run the project.

## Running the Agent

To start the agent and the ADK web interface, run the following command in the project root:

```bash
uv run .
```

This command will:

1.  Set up the virtual environment (if missing).
2.  Install necessary dependencies.
3.  Launch the ADK web server.

Once running, the console will display a local URL (usually `http://localhost:3000` or similar). Open this URL in your web browser to interact with the agent.

## Usage

In the chat interface, simply ask the agent for the time in a specific location.

**Examples:**

- "What time is it in London?"
- "Current time in New York City"
- "Tell me the time in Tokyo"

The agent will resolve the city, find the correct timezone, and respond with the current local time.
