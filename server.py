from mcp.server.fastmcp import FastMCP
import requests
import httpx
import time
from temporalio.client import Client as TemporalClient


mcp = FastMCP("adk-weather")

USER_AGENT = "weather-app/1.0"

@mcp.tool()
async def geocode_location(query: str) -> tuple[float, float] | None:
    """Geocode a location name to latitude and longitude using Nominatim."""
    params = {
        "q": query,
        "format": "json",
        "limit": 1,
    }
    headers = {
        "User-Agent": f"{USER_AGENT} nominatim"
    }
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get("https://nominatim.openstreetmap.org/search", params=params, headers=headers, timeout=20.0)
            resp.raise_for_status()
            data = resp.json()
            if not data:
                return None
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            return lat, lon
        except Exception:
            return None

@mcp.tool()
async def fetch_weather(city: str) -> dict:
    """Fetch current weather for a given city using Open-Meteo API."""
    try:
        coords = await geocode_location(city)
        if not coords:
            return {"error": f"Unable to geocode the provided location."}

        lat, lon = coords
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}&current_weather=true"
        )

        res = requests.get(url)
        res.raise_for_status()
        data = res.json()

        cw = data.get("current_weather") or {}
        return {
            "city": city,
            "latitude": lat,
            "longitude": lon,
            "temperature": cw.get("temperature"),
            "windspeed": cw.get("windspeed"),
            "winddirection": cw.get("winddirection"),
            "weathercode": cw.get("weathercode"),
            "is_day": cw.get("is_day"),
            "time": cw.get("time"),
        }

    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
async def hello(name: str = "Temporal") -> dict:
    """
    Start the 'example' Temporal workflow implemented in temporal-app using the Python SDK.
    """
    client = await TemporalClient.connect("localhost:7233", namespace="default")
    handle = await client.start_workflow(
        "example",            # workflow type (from temporal-app/src/workflows.ts)
        name,                 # first argument to the workflow
        id=f"workflow-{int(time.time()*1000)}",
        task_queue="hello-world",
    )
    result = await handle.result()
    return {
        "workflowId": handle.id,
        "runId": handle.first_execution_run_id,
        "result": result,
    }

@mcp.tool()
async def get_container_details(container_no: str) -> dict:
    client = await TemporalClient.connect("localhost:7233", namespace="default")
    handle = await client.start_workflow(
        "container_details",
        container_no,
        id=f"container-details-{int(time.time()*1000)}",
        task_queue="hello-world",
    )
    return await handle.result()

@mcp.tool()
async def fetch_pnct_empty_return():
    """
    Call PNCT EmptyReturn page replicating the provided curl headers.
    cookie_header should be the raw Cookie header value from the browser.
    """
    url = "https://pnct.net/EmptyReturn"
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "DNT": "1",
        "Referer": "https://pnct.net/",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36",
        "sec-ch-ua": "\"Chromium\";v=\"142\", \"Google Chrome\";v=\"142\", \"Not_A Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": "\"Android\""
    }
    try:
        res = requests.get(url, headers=headers, timeout=30)
        res.raise_for_status()
        return {
            "status": res.status_code,
            "url": res.url,
            "html": res.text,
        }
    except requests.HTTPError as e:
        try:
            code = e.response.status_code
            reason = e.response.reason
        except Exception:
            code = None
            reason = str(e)
        return {"error": f"HTTP error: {code} {reason}"}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    mcp.run()
