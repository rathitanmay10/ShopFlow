"""Export the OpenAPI schema as a Postman v2.1 collection.

The FastAPI app is instantiated in-process (no live server needed). Output is
written to stdout so callers can redirect to a file.
"""

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app


def _items_for_path(path: str, methods: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for method, op in methods.items():
        if method not in {"get", "post", "put", "patch", "delete"}:
            continue
        items.append(
            {
                "name": op.get("summary") or f"{method.upper()} {path}",
                "request": {
                    "method": method.upper(),
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "url": {
                        "raw": "{{base_url}}" + path,
                        "host": ["{{base_url}}"],
                        "path": [seg for seg in path.split("/") if seg],
                    },
                    "description": op.get("description", ""),
                },
            }
        )
    return items


def build_collection() -> dict[str, Any]:
    openapi = app.openapi()
    items: list[dict[str, Any]] = []
    for path, methods in openapi.get("paths", {}).items():
        items.extend(_items_for_path(path, methods))
    return {
        "info": {
            "name": openapi.get("info", {}).get("title", "ShopFlow API"),
            "schema": ("https://schema.getpostman.com/json/collection/v2.1.0/collection.json"),
        },
        "item": items,
        "variable": [{"key": "base_url", "value": "http://localhost:8000"}],
    }


def main() -> None:
    json.dump(build_collection(), sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
