from __future__ import annotations

import csv
import io
import json
import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ReferenceImportError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ImportedReference:
    points: list[tuple[int, float]]
    metadata: dict[str, Any]
    import_format: str


class ReferenceImporter(ABC):
    format_name: str

    @abstractmethod
    def can_handle(self, filename: str, mime: str, header: bytes) -> bool:
        raise NotImplementedError

    @abstractmethod
    def inspect(self, payload: bytes) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def import_points(self, payload: bytes) -> ImportedReference:
        raise NotImplementedError


def _normalize_column(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().casefold()).strip("_")


def _validated(points: list[tuple[int, float]]) -> list[tuple[int, float]]:
    if len(points) < 2:
        raise ReferenceImportError("insufficient_points", "Legalább két referenciapont szükséges.")
    points.sort(key=lambda item: item[0])
    previous = -1
    for frequency, power in points:
        if frequency <= previous or frequency < 0 or not math.isfinite(power):
            raise ReferenceImportError(
                "invalid_reference_points",
                "A frekvenciák legyenek szigorúan növekvők, a teljesítmények végesek.",
            )
        previous = frequency
    return points


def _summary(imported: ImportedReference, size_bytes: int) -> dict[str, Any]:
    frequencies = [item[0] for item in imported.points]
    powers = [item[1] for item in imported.points]
    return {
        "format": imported.import_format,
        "size_bytes": size_bytes,
        "point_count": len(imported.points),
        "start_frequency_hz": frequencies[0],
        "stop_frequency_hz": frequencies[-1],
        "minimum_power_dbm": min(powers),
        "maximum_power_dbm": max(powers),
        "metadata": imported.metadata,
    }


class CsvReferenceImporter(ReferenceImporter):
    format_name = "csv"

    def can_handle(self, filename: str, mime: str, header: bytes) -> bool:
        suffix = Path(filename).suffix.casefold()
        if suffix == ".csv" or mime.casefold() in {"text/csv", "application/csv"}:
            return True
        text = header.decode("utf-8-sig", errors="ignore").casefold()
        return "frequency" in text and ("power" in text or "dbm" in text)

    @staticmethod
    def _rows(payload: bytes) -> list[dict[str, str]]:
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ReferenceImportError("invalid_csv", "A CSV nem UTF-8 kódolású.") from exc
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        try:
            reader = csv.DictReader(io.StringIO(text), dialect=dialect)
            rows = list(reader)
        except csv.Error as exc:
            raise ReferenceImportError(
                "invalid_csv", "A CSV nem értelmezhető táblázatként."
            ) from exc
        if not reader.fieldnames:
            raise ReferenceImportError("missing_csv_header", "A CSV fejlécet nem tartalmaz.")
        return rows

    def inspect(self, payload: bytes) -> dict[str, Any]:
        return _summary(self.import_points(payload), len(payload))

    def import_points(self, payload: bytes) -> ImportedReference:
        points: list[tuple[int, float]] = []
        for raw_row in self._rows(payload):
            row = {
                _normalize_column(str(key)): value
                for key, value in raw_row.items()
                if key is not None
            }
            frequency: Any = (
                row.get("frequency_hz")
                or row.get("actual_rf_frequency_hz")
                or row.get("measured_frequency_hz")
            )
            if frequency in (None, "") and row.get("frequency_mhz") not in (None, ""):
                frequency = round(float(str(row["frequency_mhz"]).replace(",", ".")) * 1_000_000)
            power = row.get("power_dbm") or row.get("dbm") or row.get("level_dbm")
            if frequency in (None, "") or power in (None, ""):
                raise ReferenceImportError(
                    "missing_csv_columns",
                    "Kötelező oszlop: frequency_hz vagy frequency_mhz, valamint power_dbm.",
                )
            try:
                points.append(
                    (
                        int(float(str(frequency).replace(",", "."))),
                        float(str(power).replace(",", ".")),
                    )
                )
            except ValueError as exc:
                raise ReferenceImportError(
                    "invalid_csv_value", "A referencia CSV számoszlopa hibás értéket tartalmaz."
                ) from exc
        return ImportedReference(_validated(points), {}, self.format_name)


class JsonReferenceImporter(ReferenceImporter):
    format_name = "json"

    def can_handle(self, filename: str, mime: str, header: bytes) -> bool:
        return (
            Path(filename).suffix.casefold() == ".json"
            or mime.casefold() == "application/json"
            or header.lstrip().startswith((b"{", b"["))
        )

    def inspect(self, payload: bytes) -> dict[str, Any]:
        return _summary(self.import_points(payload), len(payload))

    def import_points(self, payload: bytes) -> ImportedReference:
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReferenceImportError(
                "invalid_json", "A JSON referencia nem értelmezhető."
            ) from exc
        metadata = value.get("metadata", {}) if isinstance(value, dict) else {}
        rows = value.get("points", []) if isinstance(value, dict) else value
        if not isinstance(metadata, dict):
            raise ReferenceImportError(
                "invalid_json_metadata", "A metadata mezőnek objektumnak kell lennie."
            )
        if not isinstance(rows, list):
            raise ReferenceImportError(
                "invalid_json_points", "A points mezőnek tömbnek kell lennie."
            )
        points: list[tuple[int, float]] = []
        for row in rows:
            if not isinstance(row, dict):
                raise ReferenceImportError("invalid_json_points", "Minden pont objektum legyen.")
            frequency = row.get("frequency_hz")
            if frequency is None and row.get("frequency_mhz") is not None:
                frequency = round(float(row["frequency_mhz"]) * 1_000_000)
            power = row.get("power_dbm", row.get("dbm"))
            if frequency is None or power is None:
                raise ReferenceImportError(
                    "invalid_json_points", "A frequency_hz és power_dbm kötelező."
                )
            try:
                points.append((int(frequency), float(power)))
            except (TypeError, ValueError) as exc:
                raise ReferenceImportError(
                    "invalid_json_points", "A frequency_hz és power_dbm számtípusú legyen."
                ) from exc
        return ImportedReference(_validated(points), metadata, self.format_name)


class OscorPeakPlaceholder(ReferenceImporter):
    format_name = "oscor_peak"

    def can_handle(self, filename: str, mime: str, header: bytes) -> bool:
        return Path(filename).suffix.casefold() == ".peak"

    def inspect(self, payload: bytes) -> dict[str, Any]:
        return {
            "format": self.format_name,
            "supported": False,
            "size_bytes": len(payload),
            "conversion_hint": "Exportálj CSV-t az OSCOR Data Viewerből, majd importáld a CSV-t.",
        }

    def import_points(self, payload: bytes) -> ImportedReference:
        raise ReferenceImportError(
            "unsupported_peak_format",
            "A proprietary .peak formátum dokumentáció vagy validált mintafájl nélkül "
            "nem támogatott. Exportálj CSV-t az OSCOR Data Viewerből.",
        )


IMPORTERS: tuple[ReferenceImporter, ...] = (
    OscorPeakPlaceholder(),
    JsonReferenceImporter(),
    CsvReferenceImporter(),
)


def importer_for(filename: str, mime: str, header: bytes) -> ReferenceImporter:
    for importer in IMPORTERS:
        if importer.can_handle(filename, mime, header):
            return importer
    raise ReferenceImportError(
        "unsupported_reference_format", "Csak dokumentált JSON és CSV referencia importálható."
    )


def peak_preserving_resample(
    points: list[tuple[int, float]], maximum_points: int
) -> list[tuple[int, float]]:
    if len(points) <= maximum_points:
        return list(points)
    if maximum_points < 2:
        raise ValueError("maximum_points must be at least two")
    output: list[tuple[int, float]] = []
    for bucket in range(maximum_points):
        start = math.floor(len(points) * bucket / maximum_points)
        end = max(start + 1, math.floor(len(points) * (bucket + 1) / maximum_points))
        output.append(max(points[start:end], key=lambda item: item[1]))
    output.sort(key=lambda item: item[0])
    return output
