from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Iterator
from typing import Any

from fastapi.responses import StreamingResponse


def _serialize_cell(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str, ensure_ascii=False)
    return value


def _csv_lines(fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> Iterator[str]:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    yield buffer.getvalue()
    for row in rows:
        buffer.seek(0)
        buffer.truncate(0)
        writer.writerow({key: _serialize_cell(value) for key, value in row.items()})
        yield buffer.getvalue()


def csv_export_response(filename: str, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> StreamingResponse:
    return StreamingResponse(
        _csv_lines(fieldnames, rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
