from google.adk.agents.llm_agent import Agent
import requests
import time
import json
from typing import Optional
import os
import sys
import asyncio
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import importlib.util
import threading


BUSINQUIRY_URL = "https://businquiry.portsamerica.com/api/track/GetContainers"

ADK_SERVER_PATH = "/home/ram-sthapit/portpro/Test/ADK/server.py"
_spec = importlib.util.spec_from_file_location("adk_server", ADK_SERVER_PATH)
_adk_server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_adk_server)

def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        result_container = {}
        def _runner():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            result_container["value"] = new_loop.run_until_complete(coro)
            new_loop.close()
        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        t.join()
        return result_container.get("value")

def get_container_details(container_no: str) -> str:
    """
    Fetch container availability/info by container number using Ports America API.

    Args:
        container_no: Container number, e.g. "MSBU7060010"
    """
    container = (container_no or "").strip().upper()
    if not container:
        return "Please provide a valid container number."

    headers = {
        "Accept": "*/*",
        "Origin": "https://pnct.net",
        "Referer": "https://pnct.net/",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    }
    params = {
        "siteId": "PNCT_NJ",
        "key": container,
        "_": str(int(time.time() * 1000)),
    }
    try:
        resp = requests.get(BUSINQUIRY_URL, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return json.dumps(data, indent=2) if data is not None else "Empty response from API."
    except requests.HTTPError as e:
        return f"PortsAmerica HTTP error: {e.response.status_code} {e.response.reason}"
    except Exception as e:
        return f"PortsAmerica request failed: {str(e)}"

def weather_for_city(city: str) -> str:
    """
    Use server.py's MCP tool (fetch_weather) to get current weather for a city.
    """
    city_clean = (city or "").strip()
    if not city_clean:
        return "Please provide a valid city."
    try:
        result = _run_async(_adk_server.fetch_weather(city_clean))
        if isinstance(result, dict) and result.get("error"):
            return f"Weather error: {result.get('error')}"
        temp = result.get("temperature")
        wind = result.get("windspeed")
        wind_dir = result.get("winddirection")
        wcode = result.get("weathercode")
        obs_time = result.get("time")
        name = result.get("city", city_clean)
        if temp is None or wind is None:
            return "Weather data unavailable."
        # Open-Meteo current_weather windspeed is in km/h
        parts = [f"{name}: {temp}°C", f"wind {wind} km/h"]
        if wind_dir is not None:
            parts.append(f"dir {int(wind_dir)}°")
        if wcode is not None:
            parts.append(f"code {int(wcode)}")
        if obs_time:
            parts.append(f"at {obs_time}")
        return ", ".join(parts)
    except Exception as e:
        return f"Weather fetch failed: {str(e)}"

def geocode_location_tool(query: str) -> str:
    """
    Use server.py's MCP tool (geocode_location) to resolve coordinates.
    """
    q = (query or "").strip()
    if not q:
        return "Please provide a valid place name."
    try:
        coords = _run_async(_adk_server.geocode_location(q))
        if not coords:
            return "No coordinates found."
        lat, lon = coords
        return f"{lat:.6f}, {lon:.6f}"
    except Exception as e:
        return f"Geocode failed: {str(e)}"

def hello(name: str = "Temporal") -> dict:
    """
    Use server.py's MCP tool (hello_temporal) to say hello to Temporal.
    """
    return _run_async(_adk_server.hello(name))


root_agent = Agent(
    model='gemini-2.5-flash',
    name='root_agent',
    description='A helpful assistant for user questions.',
    instruction='''
        Capabilities:
        - PNCT Containers: Use the container tool when the user provides a container number (e.g., "MSBU7060010"). Return a concise summary of key details (availability, holds, location, LFD).

        Supported Query Examples (Containers):
        - "I need container info for MSDU123456" → Get full container details
        - "Is MSDU123456 available for pickup?" → Check availability status
        - "Show me the location of container MSDU123456" → Get yard location
        - "Any holds on MSDU123456?" → Check hold status
        - "Get last free day for MSDU123456" → Retrieve LFD information

        - Weather: Use the weather tools powered by server.py.
          - "Weather of New York" → temperature, wind (km/h), direction°, code, time
          - "Weather of Kathmandu" → temperature, wind (km/h), direction°, code, time
          - "Weather in Tokyo" → temperature, wind (km/h), direction°, code, time
          - "Weather in Lagos" → temperature, wind (km/h), direction°, code, time
          - "Weather in Paris" → temperature, wind (km/h), direction°, code, time
          - "Geocode New York"

        - Temporal: Use the temporal tool to say hello to Temporal.
          - "Hello Temporal" → say hello to Temporal
          - "Hello John Doe" → say hello to John Doe
          - "Hlo World" → say hello to World
          - "Hi" → say hello to Temporal
    ''',
    tools=[
        get_container_details,
        weather_for_city,
        geocode_location_tool,
        hello,
    ],
) 
