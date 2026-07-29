from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    fixture = Path(sys.argv[1])
    projections = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(fixture.glob("projection-*.json"))
    ]
    independently_reconstructed = [
        path.name
        for path, payload in zip(
            sorted(fixture.glob("projection-*.json")),
            projections,
            strict=True,
        )
        if "derived_classification" in payload
    ]
    if independently_reconstructed:
        print(
            "classification reconstructed independently in "
            + ", ".join(independently_reconstructed)
        )
        return 1
    print("projections consume the shared workflow classification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
