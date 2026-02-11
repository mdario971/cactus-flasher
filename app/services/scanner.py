"""Board scanner service for Cactus Flasher."""
import asyncio
import socket
from typing import Dict, List, Any
import aiohttp

from ..config import get_board_ports, get_board_hostname, settings


async def scan_board(host: str, port: int, timeout: float = 3.0) -> bool:
    """Check if a board is online via HTTP to its OTA /update endpoint.

    Uses HTTP GET instead of raw TCP - ESPHome/ArduinoOTA respond with
    200 or 405 on GET /update, which is more reliable than raw TCP check.
    Retries once on failure.
    """
    for attempt in range(2):
        try:
            url = f"http://{host}:{port}/update"
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    if response.status in (200, 405, 401, 403):
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
                return response.status in (200, 401, 403)  # Any response means it's alive
    except Exception:
        return False


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


async def scan_single_board(name: str, board: dict) -> Dict[str, Any]:
    """Scan a single board and return its status."""
    ports = get_board_ports(board["id"])
    host = board.get("host", settings.DDNS_HOST)

    # Check OTA port (most reliable for ESP32 OTA)
    ota_online = await scan_board(host, ports["ota"])

    # Check webserver port
    web_online = await scan_board_http(host, ports["webserver"])

    # Get API info if OTA is online
    api_info = {}
    if ota_online:
        api_info = await get_board_info(host, ports["api"])

    hostname = get_board_hostname(name, board["id"], board.get("hostname"))

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
    }


async def scan_all_boards(boards: Dict[str, dict]) -> List[Dict[str, Any]]:
    """Scan all boards concurrently and return their statuses."""
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
                "host": board.get("host", settings.DDNS_HOST),
                "hostname": hostname,
                "ports": ports,
                "online": False,
                "error": str(result),
            })
        else:
            valid_results.append(result)

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
