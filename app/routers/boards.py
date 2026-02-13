"""Board management router for Cactus Flasher."""
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status

from ..config import get_boards, save_boards, get_board_ports, get_board_hostname, settings
from ..models.schemas import BoardCreate, BoardUpdate, BoardStatus, BoardList, SensorInfo
from ..services.scanner import scan_board, scan_board_http, get_board_info, scan_all_boards, discover_boards_on_network

router = APIRouter()


@router.get("", response_model=BoardList)
async def list_boards():
    """List all registered boards with their status."""
    boards_config = get_boards()
    boards_data = boards_config.get("boards", {})

    board_statuses = []
    for name, board in boards_data.items():
        ports = get_board_ports(board["id"])
        host = board.get("host") or settings.DDNS_HOST
        hostname = get_board_hostname(name, board["id"], board.get("hostname"))

        # Build sensor list from stored data
        sensors = None
        if board.get("sensors"):
            sensors = [
                SensorInfo(
                    id=s.get("id", ""),
                    name=s.get("name", ""),
                    state=s.get("state"),
                    unit=s.get("unit"),
                )
                for s in board["sensors"]
            ]

        board_statuses.append(
            BoardStatus(
                name=name,
                id=board["id"],
                type=board.get("type", "esp32"),
                webserver_port=ports["webserver"],
                ota_port=ports["ota"],
                api_port=ports["api"],
                online=False,  # Will be updated by scan
                host=host,
                hostname=hostname,
                mac_address=board.get("mac_address"),
                last_seen=board.get("last_seen"),
                sensors=sensors,
            )
        )

    return BoardList(boards=board_statuses)


@router.get("/scan")
async def scan_boards():
    """Scan all boards and return their online/offline status.

    Also persists discovered MAC addresses, sensors, and updates last_seen timestamps.
    """
    boards_config = get_boards()
    boards_data = boards_config.get("boards", {})

    results = await scan_all_boards(boards_data)

    # Persist MAC, last_seen, and sensors back to boards.yaml
    changed = False
    for result in results:
        name = result.get("name")
        if name not in boards_data:
            continue

        # Update MAC if discovered and not already set
        if result.get("mac_address") and not boards_data[name].get("mac_address"):
            boards_data[name]["mac_address"] = result["mac_address"]
            changed = True

        # Update last_seen if board is online
        if result.get("online"):
            boards_data[name]["last_seen"] = datetime.now(timezone.utc).isoformat()
            changed = True

        # Update sensors if discovered
        if result.get("sensors"):
            boards_data[name]["sensors"] = result["sensors"]
            changed = True

    if changed:
        save_boards(boards_config)

    return {"boards": results}


# IMPORTANT: /status-log must be BEFORE /{board_name} to avoid FastAPI matching it as a board name
@router.get("/status-log")
async def get_board_status_log(limit: int = 100, board: Optional[str] = None):
    """Get board online/offline status transition log."""
    from ..services.status_logger import get_status_log

    logs = get_status_log(limit=limit, board_name=board)
    return {"logs": logs}


@router.get("/discover")
async def discover_boards(auto_register: bool = False):
    """Discover ESP32 boards on the network by scanning OTA ports."""
    boards_config = get_boards()
    boards_data = boards_config.get("boards", {})

    known_board_ids = {b["id"] for b in boards_data.values()}

    discovered = await discover_boards_on_network(
        base_host=settings.DDNS_HOST,
        known_board_ids=known_board_ids,
    )

    auto_registered = []
    if auto_register:
        if "boards" not in boards_config:
            boards_config["boards"] = {}
        for board in discovered:
            if board["is_new"]:
                board_name = f"board-{board['id']:02d}"
                boards_config["boards"][board_name] = {
                    "id": board["id"],
                    "type": "esp32",
                    "host": None,
                    "hostname": None,
                }
                auto_registered.append(board_name)
        if auto_registered:
            save_boards(boards_config)

    return {
        "discovered": discovered,
        "total_found": len(discovered),
        "new_boards": sum(1 for b in discovered if b["is_new"]),
        "auto_registered": auto_registered,
    }


@router.get("/{board_name}", response_model=BoardStatus)
async def get_board(board_name: str):
    """Get a specific board's details and status."""
    boards_config = get_boards()
    boards_data = boards_config.get("boards", {})

    if board_name not in boards_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Board '{board_name}' not found",
        )

    board = boards_data[board_name]
    ports = get_board_ports(board["id"])
    host = board.get("host") or settings.DDNS_HOST
    hostname = get_board_hostname(board_name, board["id"], board.get("hostname"))

    # Check if board is online
    online = await scan_board(host, ports["ota"])

    # Build sensor list
    sensors = None
    if board.get("sensors"):
        sensors = [
            SensorInfo(
                id=s.get("id", ""),
                name=s.get("name", ""),
                state=s.get("state"),
                unit=s.get("unit"),
            )
            for s in board["sensors"]
        ]

    return BoardStatus(
        name=board_name,
        id=board["id"],
        type=board.get("type", "esp32"),
        webserver_port=ports["webserver"],
        ota_port=ports["ota"],
        api_port=ports["api"],
        online=online,
        host=host,
        hostname=hostname,
        mac_address=board.get("mac_address"),
        last_seen=board.get("last_seen"),
        sensors=sensors,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_board(board: BoardCreate):
    """Register a new board."""
    boards_config = get_boards()
    if "boards" not in boards_config:
        boards_config["boards"] = {}

    if board.name in boards_config["boards"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Board '{board.name}' already exists",
        )

    # Check if ID is already in use
    for existing_name, existing_board in boards_config["boards"].items():
        if existing_board["id"] == board.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Board ID {board.id} is already used by '{existing_name}'",
            )

    board_data = {
        "id": board.id,
        "type": board.type.value,
        "host": board.host,
        "hostname": board.hostname,
    }
    if board.api_key:
        board_data["api_key"] = board.api_key
    if board.mac_address:
        board_data["mac_address"] = board.mac_address
    boards_config["boards"][board.name] = board_data
    save_boards(boards_config)

    return {"message": f"Board '{board.name}' created successfully"}


@router.put("/{board_name}")
async def update_board(board_name: str, board_update: BoardUpdate):
    """Update a board's configuration."""
    boards_config = get_boards()
    boards_data = boards_config.get("boards", {})

    if board_name not in boards_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Board '{board_name}' not found",
        )

    board = boards_data[board_name]

    if board_update.name is not None:
        # Rename board
        if board_update.name != board_name and board_update.name in boards_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Board '{board_update.name}' already exists",
            )
        del boards_config["boards"][board_name]
        board_name = board_update.name

    if board_update.type is not None:
        board["type"] = board_update.type.value

    if board_update.host is not None:
        board["host"] = board_update.host

    if board_update.hostname is not None:
        board["hostname"] = board_update.hostname

    if board_update.api_key is not None:
        board["api_key"] = board_update.api_key

    if board_update.mac_address is not None:
        board["mac_address"] = board_update.mac_address

    boards_config["boards"][board_name] = board
    save_boards(boards_config)

    return {"message": f"Board '{board_name}' updated successfully"}


@router.delete("/{board_name}")
async def delete_board(board_name: str):
    """Delete a board from the registry."""
    boards_config = get_boards()
    boards_data = boards_config.get("boards", {})

    if board_name not in boards_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Board '{board_name}' not found",
        )

    del boards_config["boards"][board_name]
    save_boards(boards_config)

    return {"message": f"Board '{board_name}' deleted successfully"}


@router.post("/{board_name}/ping")
async def ping_board(board_name: str):
    """Ping a specific board to check if it's online.

    Updates last_seen timestamp on successful ping.
    """
    boards_config = get_boards()
    boards_data = boards_config.get("boards", {})

    if board_name not in boards_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Board '{board_name}' not found",
        )

    board = boards_data[board_name]
    ports = get_board_ports(board["id"])
    host = board.get("host") or settings.DDNS_HOST
    hostname = get_board_hostname(board_name, board["id"], board.get("hostname"))

    ota_online = await scan_board(host, ports["ota"])
    web_online = await scan_board_http(host, ports["webserver"])
    api_info = await get_board_info(host, ports["api"]) if ota_online else {"api_available": False}

    online = ota_online or web_online

    # Update last_seen if online
    if online:
        boards_data[board_name]["last_seen"] = datetime.now(timezone.utc).isoformat()
        save_boards(boards_config)

    # Log status transition
    try:
        from ..services.status_logger import log_status_change
        ota_str = "OK" if ota_online else "FAIL"
        web_str = "OK" if web_online else "FAIL"
        api_str = "OK" if api_info.get("api_available") else "FAIL"
        new_status = "online" if online else "offline"
        log_status_change(board_name, new_status, f"OTA:{ota_str} WEB:{web_str} API:{api_str}")
    except Exception:
        pass

    return {
        "board": board_name,
        "host": host,
        "hostname": hostname,
        "port": ports["ota"],
        "online": online,
        "ota_online": ota_online,
        "web_online": web_online,
        "api_available": api_info.get("api_available", False),
        "mac_address": board.get("mac_address"),
    }
