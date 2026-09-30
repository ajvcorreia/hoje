"""Export the OpenAPI document: ``python -m hoje.openapi [path]``.

Deterministic and database-free. The default output is ``backend/openapi.json``; a relative
path argument is resolved against the backend directory.
"""

import json
import sys
from pathlib import Path

from hoje.main import create_app

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PATH = BACKEND_DIR / "openapi.json"


def render() -> str:
    spec = create_app(docs_enabled=False).openapi()
    return json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    target = Path(args[0]) if args else DEFAULT_PATH
    if not target.is_absolute():
        target = BACKEND_DIR / target
    target.write_text(render(), encoding="utf-8", newline="\n")
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
