"""Board management router for Cactus Flasher."""
from typing import List
from fastapi import APIRouter, HTTPException, status

from ..config import get_boards, save_boards, get_board_ports, get_board_hostname, settings
from ..models.schemas import BoardCreate, BoardUpdate, BoardStatus, BoardList
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
            )
        )

    return BoardList(boards=board_statuses)


@router.get("/scan")
async def scan_boards():
    """Scan all boards and return their online/offline status."""
    boards_config = get_boards()
    boards_data = boards_config.get("boards", {})

    results = await scan_all_boards(boards_data)
    return {"boards": results}


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
    """Ping a specific board to check if it's online."""
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

    return {
        "board": board_name,
        "host": host,
        "hostname": hostname,
        "port": ports["ota"],
        "online": ota_online or web_online,
        "ota_online": ota_online,
        "web_online": web_online,
        "api_available": api_info.get("api_available", False),
    }
