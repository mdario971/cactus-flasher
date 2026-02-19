"""Board scanner service for Cactus Flasher."""
import asyncio
import re
from typing import Dict, List, Any, Optional
import aiohttp

from ..config import get_board_ports, get_board_hostname, settings


async def scan_board(host: str, port: int, timeout: float = 3.0) -> bool:
    """Check if a board's OTA port is reachable via raw TCP connection.

    Uses raw TCP instead of HTTP because ESPHome OTA uses a binary protocol.
    Sending HTTP to the OTA port causes 'Magic bytes mismatch' errors on the board.
    Retries once on failure.
    """
    for attempt in range(2):
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout,
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            pass
        if attempt == 0:
            await asyncio.sleep(0.5)
    return False


async def scan_board_http(host: str, port: int, timeout: float = 3.0) -> bool:
    """Check if a board is online via HTTP request to its webserver."""
    url = f"http://{host}:{port}/"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                return response.status in (200, 401, 403)
    except Exception:
        return False


def _make_basic_auth(web_username: str = None, web_password: str = None):
    """Create aiohttp BasicAuth if credentials are provided."""
    if web_username and web_password:
        return aiohttp.BasicAuth(web_username, web_password)
    return None


async def get_board_info(host: str, api_port: int, timeout: float = 5.0) -> Dict[str, Any]:
    """Get ESPHome device info from a board's native API port."""
    # ESPHome native API uses a custom protocol, not HTTP
    # For now, just check if the port is open
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, api_port),
            timeout=timeout,
        )
        writer.close()
        await writer.wait_closed()
        return {"api_available": True}
    except Exception:
        return {"api_available": False}


async def get_mac_address(
    host: str, webserver_port: int, timeout: float = 5.0,
    web_username: str = None, web_password: str = None,
) -> Optional[str]:
    """Try to extract MAC address from ESPHome web server page.

    ESPHome web_server pages typically include the device MAC address
    somewhere in the HTML content. Supports HTTP Basic Auth.
    """
    url = f"http://{host}:{webserver_port}/"
    auth = _make_basic_auth(web_username, web_password)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=timeout),
                auth=auth,
            ) as response:
                if response.status == 200:
                    html = await response.text()
                    mac_match = re.search(
                        r'([0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:'
                        r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2})',
                        html,
                    )
                    if mac_match:
                        return mac_match.group(1).upper()
    except Exception:
        pass
    return None


async def scan_single_board(name: str, board: dict) -> Dict[str, Any]:
    """Scan a single board and return its status.

    Checks OTA, webserver, and API ports.
    If webserver is online, also tries to discover MAC address and sensors.
    Passes web_server auth credentials if configured.
    """
    ports = get_board_ports(board["id"])
    host = board.get("host") or settings.DDNS_HOST
    web_user = board.get("web_username")
    web_pass = board.get("web_password")

    # Check OTA port (most reliable for ESP32 OTA)
    ota_online = await scan_board(host, ports["ota"])

    # Check webserver port
    web_online = await scan_board_http(host, ports["webserver"])

    # Get API info if OTA is online
    api_info = {}
    if ota_online:
        api_info = await get_board_info(host, ports["api"])

    hostname = get_board_hostname(name, board["id"], board.get("hostname"))

    # Try to discover MAC address if webserver is online and MAC not already known
    mac_address = board.get("mac_address")
    if not mac_address and web_online:
        mac_address = await get_mac_address(
            host, ports["webserver"],
            web_username=web_user, web_password=web_pass,
        )

    # Try to discover sensors and device info if webserver is online
    sensors = board.get("sensors", [])
    device_info = board.get("device_info", {})
    if web_online:
        try:
            from .sensors import discover_sensors, get_device_info
            discovered = await discover_sensors(
                host, ports["webserver"],
                web_username=web_user, web_password=web_pass,
            )
            if discovered:
                sensors = discovered
            # Extract device info (version, platform, etc.)
            new_info = await get_device_info(
                host, ports["webserver"],
                web_username=web_user, web_password=web_pass,
            )
            if new_info:
                device_info = new_info
        except Exception:
            pass

    return {
        "name": name,
        "id": board["id"],
        "type": board.get("type", "esp32"),
        "host": host,
        "hostname": hostname,
        "ports": ports,
        "online": ota_online or web_online,
        "ota_online": ota_online,
        "web_online": web_online,
        "api_info": api_info,
        "mac_address": mac_address,
        "sensors": sensors,
        "device_info": device_info,
    }


async def scan_all_boards(boards: Dict[str, dict]) -> List[Dict[str, Any]]:
    """Scan all boards concurrently and return their statuses.

    Also logs status transitions (online/offline) to persistent storage.
    """
    if not boards:
        return []

    tasks = [
        scan_single_board(name, board)
        for name, board in boards.items()
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out exceptions and return valid results
    valid_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            name = list(boards.keys())[i]
            board = boards[name]
            ports = get_board_ports(board["id"])
            hostname = get_board_hostname(name, board["id"], board.get("hostname"))
            valid_results.append({
                "name": name,
                "id": board["id"],
                "type": board.get("type", "esp32"),
                "host": board.get("host") or settings.DDNS_HOST,
                "hostname": hostname,
                "ports": ports,
                "online": False,
                "error": str(result),
            })
        else:
            valid_results.append(result)

    # Log status transitions
    try:
        from .status_logger import log_status_change, get_last_statuses

        last_statuses = get_last_statuses()
        for result in valid_results:
            name = result["name"]
            new_status = "online" if result.get("online") else "offline"
            ota = "OK" if result.get("ota_online") else "FAIL"
            web = "OK" if result.get("web_online") else "FAIL"
            api = "OK" if result.get("api_info", {}).get("api_available") else "FAIL"
            details = f"OTA:{ota} WEB:{web} API:{api}"
            log_status_change(name, new_status, details)
    except Exception:
        pass  # Don't break scanning if logging fails

    return valid_results


async def discover_boards_on_network(
    base_host: str = None,
    port_range: tuple = (8201, 8299),
    timeout: float = 2.0,
    known_board_ids: set = None,
) -> List[Dict[str, Any]]:
    """Discover ESP32 boards on the network by scanning OTA ports."""
    host = base_host or settings.DDNS_HOST
    discovered = []
    known = known_board_ids or set()

    async def check_port(port: int):
        board_id = port - 8200
        if await scan_board(host, port, timeout):
            return {
                "id": board_id,
                "host": host,
                "ota_port": port,
                "webserver_port": 8000 + board_id,
                "api_port": 6000 + board_id,
                "is_new": board_id not in known,
            }
        return None

    # Scan ports concurrently in batches to avoid overwhelming the network
    batch_size = 20
    for start in range(port_range[0], port_range[1], batch_size):
        end = min(start + batch_size, port_range[1])
        tasks = [check_port(port) for port in range(start, end)]
        results = await asyncio.gather(*tasks)
        discovered.extend([r for r in results if r is not None])

    return discovered
