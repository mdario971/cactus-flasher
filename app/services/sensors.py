"""Sensor discovery service for Cactus Flasher.

Discovers sensors from ESPHome boards via their web_server component.
Parses the HTML page or uses the /events SSE endpoint to extract entity data.
"""
import re
from typing import List, Dict, Any, Optional
import aiohttp


async def discover_sensors(
    host: str, webserver_port: int, timeout: float = 5.0
) -> List[Dict[str, Any]]:
    """Discover sensors from an ESPHome board's web server.

    Tries to parse sensor data from the ESPHome web_server HTML page.
    Falls back to the /events SSE endpoint if HTML parsing fails.

    Returns list of sensor dicts: [{"id": "...", "name": "...", "state": "...", "unit": "..."}, ...]
    """
    sensors = []

    try:
        url = f"http://{host}:{webserver_port}/"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status == 200:
                    html = await response.text()
                    sensors = parse_esphome_web_page(html)
    except Exception:
        pass

    # Fallback: try /events endpoint for SSE data
    if not sensors:
        try:
            sensors = await _try_events_endpoint(host, webserver_port, timeout)
        except Exception:
            pass

    return sensors


def parse_esphome_web_page(html: str) -> List[Dict[str, Any]]:
    """Parse ESPHome web_server HTML to extract sensor entities.

    ESPHome web_server v2+ renders entity rows in the page.
    Looks for common patterns in ESPHome-generated HTML.
    """
    sensors = []

    # ESPHome web_server v3 / v2 uses specific HTML patterns
    # Pattern 1: Look for sensor state spans with id and value
    # <span id="sensor-temperature" class="state">22.5 C</span>
    # or variations like data attributes

    # Pattern: find elements with id containing "sensor-" or "number-" or "text_sensor-"
    # and extract the state text
    entity_patterns = [
        # ESPHome v2+ uses a REST-like approach with specific element IDs
        # Match: id="sensor-xxx" or id="number-xxx" or id="text_sensor-xxx"
        r'id=["\'](?:sensor|number|text_sensor|binary_sensor)-([^"\']+)["\'][^>]*>([^<]*)<',
        # Match state spans with entity prefixes
        r'<(?:span|td|div)[^>]*class=["\'][^"\']*state[^"\']*["\'][^>]*id=["\']([^"\']+)["\'][^>]*>([^<]*)<',
    ]

    for pattern in entity_patterns:
        matches = re.findall(pattern, html, re.IGNORECASE)
        for match in matches:
            entity_id = match[0].strip()
            state_text = match[1].strip()

            if not entity_id or not state_text:
                continue

            # Parse state and unit
            name = entity_id.replace("-", " ").replace("_", " ").title()
            state, unit = _parse_state_unit(state_text)

            sensors.append({
                "id": entity_id,
                "name": name,
                "state": state,
                "unit": unit,
            })

    # Pattern 2: ESPHome v3 uses a different structure with JSON-like data
    # Look for JSON state objects embedded in the page
    json_pattern = r'"id"\s*:\s*"([^"]+)"\s*,\s*"state"\s*:\s*"([^"]*)"'
    json_matches = re.findall(json_pattern, html)
    seen_ids = {s["id"] for s in sensors}
    for match in json_matches:
        entity_id = match[0].strip()
        if entity_id in seen_ids:
            continue
        state_text = match[1].strip()
        name = entity_id.replace("-", " ").replace("_", " ").title()
        state, unit = _parse_state_unit(state_text)
        sensors.append({
            "id": entity_id,
            "name": name,
            "state": state,
            "unit": unit,
        })

    # Pattern 3: Look for table rows with sensor data (older ESPHome versions)
    # <tr><td>Temperature</td><td>22.5 C</td></tr>
    table_pattern = r'<tr[^>]*>\s*<td[^>]*>([^<]+)</td>\s*<td[^>]*>([^<]+)</td>'
    table_matches = re.findall(table_pattern, html, re.IGNORECASE)
    for match in table_matches:
        name = match[0].strip()
        state_text = match[1].strip()

        # Skip header rows or non-sensor data
        if name.lower() in ('name', 'entity', 'sensor', 'state', 'value', 'type'):
            continue

        entity_id = name.lower().replace(" ", "_")
        if entity_id in seen_ids:
            continue

        state, unit = _parse_state_unit(state_text)
        if state and state not in ('N/A', 'n/a', '-'):
            sensors.append({
                "id": entity_id,
                "name": name,
                "state": state,
                "unit": unit,
            })
            seen_ids.add(entity_id)

    return sensors


async def _try_events_endpoint(
    host: str, webserver_port: int, timeout: float = 5.0
) -> List[Dict[str, Any]]:
    """Try to get sensor data from ESPHome /events SSE endpoint.

    ESPHome web_server exposes an /events endpoint that streams
    Server-Sent Events with entity state updates.
    """
    sensors = []
    url = f"http://{host}:{webserver_port}/events"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=timeout),
                headers={"Accept": "text/event-stream"},
            ) as response:
                if response.status != 200:
                    return sensors

                # Read only first chunk of SSE data (don't stream forever)
                chunk = await response.content.read(8192)
                text = chunk.decode("utf-8", errors="ignore")

                # Parse SSE events
                # Format: data: {"id":"sensor-xxx","state":"22.5","value":"22.5 C"}
                import json

                for line in text.split("\n"):
                    line = line.strip()
                    if line.startswith("data:"):
                        try:
                            data = json.loads(line[5:].strip())
                            if isinstance(data, dict) and "id" in data:
                                entity_id = data["id"]
                                state = str(data.get("state", data.get("value", "")))
                                name = entity_id.replace("-", " ").replace("_", " ").title()
                                state_val, unit = _parse_state_unit(state)
                                sensors.append({
                                    "id": entity_id,
                                    "name": name,
                                    "state": state_val,
                                    "unit": unit,
                                })
                        except (json.JSONDecodeError, TypeError):
                            continue
    except Exception:
        pass

    return sensors


def _parse_state_unit(state_text: str) -> tuple:
    """Parse a state string like '22.5 C' into ('22.5', 'C').

    Returns (state, unit) tuple.
    """
    if not state_text:
        return ("", "")

    state_text = state_text.strip()

    # Common unit patterns
    unit_patterns = [
        (r'^([\d.,-]+)\s*(%)\s*$', None),           # 65 % or 65%
        (r'^([\d.,-]+)\s*(\u00b0[CcFf])\s*$', None), # 22.5 C
        (r'^([\d.,-]+)\s*(C|F|K)\s*$', None),        # 22.5 C/F/K
        (r'^([\d.,-]+)\s*(hPa|Pa|mbar|bar)\s*$', None),  # pressure
        (r'^([\d.,-]+)\s*(lx|lux)\s*$', None),       # light
        (r'^([\d.,-]+)\s*(dB|dBm)\s*$', None),       # signal
        (r'^([\d.,-]+)\s*(V|mV|A|mA|W|kW|kWh|Wh)\s*$', None),  # electrical
        (r'^([\d.,-]+)\s*(ppm|ppb|ug/m3|mg/m3)\s*$', None),  # air quality
        (r'^([\d.,-]+)\s*(mm|cm|m|km|in|ft)\s*$', None),  # distance
        (r'^([\d.,-]+)\s*(s|ms|min|h)\s*$', None),   # time
        (r'^([\d.,-]+)\s*([a-zA-Z/]+)\s*$', None),   # generic number + unit
    ]

    for pattern, _ in unit_patterns:
        match = re.match(pattern, state_text)
        if match:
            return (match.group(1), match.group(2))

    # No unit found, return as-is
    return (state_text, "")
