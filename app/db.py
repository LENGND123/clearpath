"""FalkorDB connections. One client per call so concurrent requests do not share a socket."""

from __future__ import annotations

import os
import re

from falkordb import FalkorDB

USER_ID = re.compile(r"^[a-zA-Z0-9_-]{1,40}$")


def settings() -> dict:
    return {
        "host": os.getenv("FALKORDB_HOST", "localhost"),
        "port": int(os.getenv("FALKORDB_PORT", "6379")),
        "username": os.getenv("FALKORDB_USERNAME") or None,
        "password": os.getenv("FALKORDB_PASSWORD") or None,
    }


def connect() -> FalkorDB:
    cfg = settings()
    kwargs = {"host": cfg["host"], "port": cfg["port"]}
    if cfg["username"]:
        kwargs["username"] = cfg["username"]
    if cfg["password"]:
        kwargs["password"] = cfg["password"]
    return FalkorDB(**kwargs)


def harbor_name() -> str:
    return os.getenv("HARBOR_GRAPH", "harbor")


def coord_name() -> str:
    return os.getenv("COORD_GRAPH", "coord")


def memory_name(user_id: str) -> str:
    check_user_id(user_id)
    return f"memory_{user_id}"


def check_user_id(user_id: str) -> str:
    if not USER_ID.match(user_id or ""):
        raise ValueError("user_id must be 1-40 letters, numbers, _ or -")
    return user_id


def _column_name(col) -> str:
    # FalkorDB headers are [type, name] pairs. Take the string, whichever side it is on.
    if isinstance(col, (list, tuple)):
        for item in reversed(col):
            if isinstance(item, bytes):
                return item.decode()
            if isinstance(item, str):
                return item
        return str(col[-1])
    if isinstance(col, bytes):
        return col.decode()
    name = getattr(col, "name", None)
    if isinstance(name, (str, bytes)):
        return name.decode() if isinstance(name, bytes) else name
    return str(col)


def rows(result) -> list[dict]:
    """Turn a FalkorDB result into plain dicts. Cells stay scalars or lists."""
    header = [_column_name(col) for col in (result.header or [])]
    parsed = []
    for row in result.result_set or []:
        item = {}
        for key, value in zip(header, row):
            item[key] = _cell(value)
        parsed.append(item)
    return parsed


def _cell(value):
    if isinstance(value, bytes):
        return value.decode()
    if isinstance(value, list):
        return [_cell(item) for item in value]
    return value


def list_graph_names(db: FalkorDB | None = None) -> list[str]:
    db = db or connect()
    try:
        raw = db.list_graphs()
    except Exception:
        raw = db.connection.execute_command("GRAPH.LIST")
    names = []
    for item in list(raw or []):
        if isinstance(item, bytes):
            item = item.decode()
        names.append(str(item))
    return names


def delete_graph(name: str, db: FalkorDB | None = None) -> None:
    db = db or connect()
    try:
        db.select_graph(name).delete()
    except Exception:
        return


def ping() -> None:
    db = connect()
    try:
        db.connection.ping()
    except Exception:
        # A query forces the socket open if ping is not exposed.
        db.select_graph(harbor_name()).query("RETURN 1")
