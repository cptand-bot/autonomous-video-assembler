from __future__ import annotations

"""Read-only adapter for the GEO2_ARCHIVE_TEST Google Sheet.

The adapter deliberately returns plain dictionaries so the rest of the
assembler remains testable without Google credentials or network access.
"""

import json
import os
from dataclasses import dataclass
from typing import Any


DEFAULT_SPREADSHEET_ID = "1BuaBPZQyIkpzXnRGK3cbIsLqRcTJy_sPR49_dDx71o4"


@dataclass(frozen=True)
class GeoRecord:
    key: str
    text: str = ""
    original_link: str = ""
    media_type: str = ""
    channel: str = ""
    author_notes: tuple[str, ...] = ()
    reasoning: tuple[str, ...] = ()
    production: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "text": self.text,
            "original_link": self.original_link,
            "media_type": self.media_type,
            "channel": self.channel,
            "author_notes": list(self.author_notes),
            "reasoning": list(self.reasoning),
            "production": self.production,
        }


def _rows_to_dicts(values: list[list[Any]]) -> list[dict[str, Any]]:
    if not values:
        return []
    headers = [str(x or "") for x in values[0]]
    return [dict(zip(headers, row + [""] * (len(headers) - len(row)))) for row in values[1:]]


class GeoRadarClient:
    """Small read-only Google Sheets client using a service-account JSON key."""

    def __init__(self, spreadsheet_id: str | None = None, service_account_json: str | None = None):
        self.spreadsheet_id = spreadsheet_id or os.getenv("GEORADAR_SPREADSHEET_ID", DEFAULT_SPREADSHEET_ID)
        raw = service_account_json or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not raw:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not configured")
        try:
            self._credentials_info = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON") from exc

    def _service(self):
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        credentials = Credentials.from_service_account_info(
            self._credentials_info,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        return build("sheets", "v4", credentials=credentials, cache_discovery=False)

    def values(self, sheet: str, range_: str = "A1:Z500") -> list[list[Any]]:
        response = self._service().spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{sheet}'!{range_}",
            valueRenderOption="FORMATTED_VALUE",
        ).execute()
        return response.get("values", [])

    def find(self, key: str) -> GeoRecord:
        archive = _rows_to_dicts(self.values("Archive"))
        row = next((r for r in archive if key in {r.get("record_key", ""), r.get("production_id", "")} or key in str(r.get("text", ""))), None)
        if row is None:
            raise KeyError(f"Georadar record not found: {key}")
        notes = _rows_to_dicts(self.values("AuthorNotes"))
        reasoning = _rows_to_dicts(self.values("AuthorReasoning"))
        productions = _rows_to_dicts(self.values("Productions"))
        linked_notes = [r.get("original_text", "") for r in notes if key in str(r.get("original_text", "")) or key == r.get("archive_record_key", "")]
        linked_reasoning = [r.get("author_original", "") for r in reasoning if key in str(r.get("related_geo2_ids", "")) or key in str(r.get("source_reference", ""))]
        production = next((r for r in productions if r.get("production_id") == key), None)
        return GeoRecord(
            key=key,
            text=row.get("text", ""),
            original_link=row.get("original_link", ""),
            media_type=row.get("media_type", ""),
            channel=row.get("channel_title", ""),
            author_notes=tuple(x for x in linked_notes if x),
            reasoning=tuple(x for x in linked_reasoning if x),
            production=production,
        )
