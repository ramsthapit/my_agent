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

# def get_container_details(container_no: str) -> str:
#     """
#     Fetch container availability/info by container number using Ports America API.

#     Args:
#         container_no: Container number, e.g. "MSBU7060010"
#     """
#     container = (container_no or "").strip().upper()
#     if not container:
#         return "Please provide a valid container number."

#     headers = {
#         "Accept": "*/*",
#         "Origin": "https://pnct.net",
#         "Referer": "https://pnct.net/",
#         "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
#     }
#     params = {
#         "siteId": "PNCT_NJ",
#         "key": container,
#         "_": str(int(time.time() * 1000)),
#     }
#     try:
#         resp = requests.get(BUSINQUIRY_URL, headers=headers, params=params, timeout=30)
#         resp.raise_for_status()
#         data = resp.json()
#         return json.dumps(data, indent=2) if data is not None else "Empty response from API."
#     except requests.HTTPError as e:
#         return f"PortsAmerica HTTP error: {e.response.status_code} {e.response.reason}"
#     except Exception as e:
#         return f"PortsAmerica request failed: {str(e)}"

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

def get_container_details(container_no: str) -> dict:
    """
    Use server.py's MCP tool (get_container_details) to get container details.
    """
    return _run_async(_adk_server.get_container_details(container_no))

def pnct_empty_return():
    """
    Use server.py's MCP tool (fetch_pnct_empty_return) to fetch the PNCT EmptyReturn page.
    Provide the raw Cookie header string copied from your browser session.
    """
    try:
        result = _run_async(_adk_server.fetch_pnct_empty_return())
        if isinstance(result, dict) and result.get("error"):
            return f"PNCT error: {result.get('error')}"
        html = result.get("html")
        return html if html is not None else ""
    except Exception as e:
        return f"PNCT request failed: {str(e)}"
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
          - "Hi" → say hello to Developer
        
        - Empty Return: You are a Track OS AI Agent specialized in port operations and container tracking.

            You are given the full HTML content of the PNCT Empty Return page. Your task is to **extract structured data** from the HTML, specifically:

            ---

            ### Data to Extract

            **Shipping Lines**: All shipping lines listed in the table.  
            **Container Types and Status**: For each shipping line, extract the status (YES / NO / N/A) for each container type:

            - 20' Dry
            - 20' Open Tops
            - 20' Flat
            - 20' Reefers
            - Hangers
            - 40' Dry
            - 40' Open Tops
            - 40' Flat
            - 40' High Cubes
            - 40' High Cube Reefers
            - 45' High Cubes

            **Remarks**: If a “More/Less” section exists for a shipping line, extract the full remarks content for that line.

             you then get data in a structured JSON format like this:

            ```json
            [
            {
                "shipping_line": "MSC",
                "containers": {
                "20' Dry": "YES",
                "20' Open Tops": "YES",
                "20' Flat": "YES",
                "20' Reefers": "YES",
                "Hangers": "YES",
                "40' Dry": "YES",
                "40' Open Tops": "YES",
                "40' Flat": "YES",
                "40' High Cubes": "YES",
                "40' High Cube Reefers": "YES",
                "45' High Cubes": "YES"
                },
                "remarks": "20DV Dispatch: PNCT/Marsh\n40DV Dispatch: PNCT/PORT LIBERTY\n..."
            },
            {
                "shipping_line": "MAERSK SAFMARINE SEALAND HAMBURG SUD",
                "containers": {
                "20' Dry": "NO",
                "20' Open Tops": "NO",
                "20' Flat": "NO",
                "20' Reefers": "NO",
                "Hangers": "NO",
                "40' Dry": "NO",
                "40' Open Tops": "NO",
                "40' Flat": "NO",
                "40' High Cubes": "NO",
                "40' High Cube Reefers": "NO",
                "45' High Cubes": "NO"
                },
                "remarks": "All Specialized Equipment and 20' Reefers return to APM\nDispatch 20DV from PNCT/APM\n..."
            }
            ]

            ### Task

            1. When the user asks about **availability of containers**, reply in **natural language** describing which shipping lines are open (YES) or not (NO/N/A) for the requested container type.
            2. When the user asks about a **specific shipping line**, list all container types that are available (YES) and include remarks if present.
            3. Format your response clearly, using bullet points or short sentences for readability.
            4. Include relevant remarks if they exist for the shipping line.
            5. When the user provides a container number:
                - Use the MCP tool get_container_details(container_no) to fetch container details.
                - Then use the MCP tool pnct_empty_return to get empty return information for that container type.

            
            ### Important

            - Always map YES/NO/N/A to user-friendly text (“available” / “not available” / “not applicable”).  
            - Keep responses concise but informative.  
            - Include shipping line remarks if available.  
            - Include the date and time or gate hours when the empty return is available.
            - Do not include HTML tags in the response.
    ''',
    tools=[
        get_container_details,
        weather_for_city,
        geocode_location_tool,
        hello,
        pnct_empty_return,
    ],
) 
