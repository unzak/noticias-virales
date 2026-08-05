#!/usr/bin/env python3
"""Valida los perfiles de configuración incluidos en el repositorio."""

from __future__ import annotations

import json
from pathlib import Path

FILES = (
    Path("cabronazi_performance_profile.json"),
    Path("editorial_selection_profile.json"),
)


def main() -> int:
    for path in FILES:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError(f"{path} debe contener un objeto JSON")
        print(f"OK: {path} ({len(payload)} claves)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
