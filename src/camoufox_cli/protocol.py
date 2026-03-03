"""JSON-line protocol for CLI <-> Daemon communication."""

import json


def parse_command(line: str) -> dict:
    """Parse a JSON-line command from the CLI."""
    return json.loads(line.strip())


def serialize_response(response: dict) -> bytes:
    """Serialize a response dict to JSON-line bytes."""
    return json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n"


def ok_response(id: str, data: dict | None = None) -> dict:
    resp = {"id": id, "success": True}
    if data is not None:
        resp["data"] = data
    return resp


def error_response(id: str, error: str) -> dict:
    return {"id": id, "success": False, "error": error}
