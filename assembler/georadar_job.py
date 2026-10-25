from __future__ import annotations

import argparse
import json
from pathlib import Path

from .georadar import GeoRadarClient


def write_context(root: Path, key: str, service_account_json: str) -> dict:
    record = GeoRadarClient(service_account_json=service_account_json).find(key)
    payload = record.as_dict()
    (root / "georadar.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Read one GEO2 record into the current build job")
    parser.add_argument("--root", type=Path, default=Path("build"))
    parser.add_argument("--key", required=True, help="PROD_... or ARM_... key")
    parser.add_argument("--service-account-json", required=True)
    args = parser.parse_args()
    print(json.dumps(write_context(args.root, args.key, args.service_account_json), ensure_ascii=False))


if __name__ == "__main__":
    main()
