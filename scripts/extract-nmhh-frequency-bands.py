#!/usr/bin/env python3
"""Extract national frequency-allocation bands from the NMHH annex PDF text.

Usage: pdftotext -layout 2melleklet_hu.pdf annex.txt
       python3 scripts/extract-nmhh-frequency-bands.py annex.txt output.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BAND_RE = re.compile(
    r"^\s*(?P<row>\d+)\s+(?P<start>\d[\d .]*?(?:,\d+)?)\s*[–-]\s*"
    r"(?P<end>\d[\d .]*?(?:,\d+)?)\s*(?P<unit>kHz|MHz|GHz)\b"
)
PAGE_NO_RE = re.compile(r"^\s*\d+\s*$")
TABLE_HEADER_WORDS = (
    "Nemzeti felosztás",
    "Frekvenciasávok használati szabályai",
    "További szabály",
)
ROW_RE = re.compile(r"^\s*\d+\s+(?P<body>.*)$")
APPLICATION_RE = re.compile(r"(?:^|\s)(?:[123]|-)\s+[KTÜ]\s+(?P<name>.*?)(?=\s{2,}|$)")
IGNORED_PREFIXES = {
    "N",
    "P",
    "E",
    "PN",
    "NJE",
    "NJÖ",
    "RRE",
    "SRD",
    "1",
    "2",
    "3",
    "-",
}


def number(value: str) -> float:
    return float(value.replace(" ", "").replace(",", "."))


def to_hz(value: float, unit: str) -> int:
    return round(value * {"kHz": 1e3, "MHz": 1e6, "GHz": 1e9}[unit])


def clean_detail(line: str) -> str | None:
    value = re.sub(r"^\s*\d+\s+", "", line).strip()
    value = re.sub(r"\s{2,}", " · ", value)
    if not value or PAGE_NO_RE.match(value) or any(word in value for word in TABLE_HEADER_WORDS):
        return None
    if value in {"A · B · C · D · E · F · G · H", "Alkalmazás · Dokumentum"}:
        return None
    return value


def concise_name(name: str, start_hz: int, end_hz: int) -> str:
    value = re.sub(r"\s+", " ", name).strip(" ·.;")
    lowered = value.casefold()
    if not value or value == "Alkalmazás" or any(word in value for word in TABLE_HEADER_WORDS):
        return ""
    if (
        value in {"Műholdas", "MHz)"}
        or value.count("(") != value.count(")")
        or value.endswith(("–", "-"))
    ):
        return ""
    if "szélessávú adatátvitel" in lowered and start_hz < 2_483_500_000 and end_hz > 2_400_000_000:
        return "Wi-Fi és Bluetooth"
    if value == "WAS/RLAN rendszerek":
        return "Wi-Fi (WAS/RLAN)"
    if value in {"BWA", "BBDR", "LTE", "NR", "RFID", "ISM", "WiMAX"}:
        return value
    replacements = {
        "Amatőr": "Amatőrrádiózás",
        "Műholdas amatőr": "Műholdas amatőrrádiózás",
        "ÁLLANDÓHELYŰ": "Állandóhelyű rádiószolgálat",
        "MOZGÓ": "Mozgó rádiószolgálat",
        "Rádiólokáció": "Rádiólokáció",
        "SRD": "Kis hatótávolságú eszközök (SRD)",
    }
    return replacements.get(value, value.capitalize() if value.isupper() else value)


def extract_uses(lines: list[str], start_hz: int, end_hz: int) -> list[str]:
    uses: list[str] = []

    def add(name: str) -> None:
        value = concise_name(name, start_hz, end_hz)
        values = ("Wi-Fi", "Bluetooth") if value == "Wi-Fi és Bluetooth" else (value,)
        for item in values:
            if item and item not in uses:
                uses.append(item)

    for line in lines:
        row = ROW_RE.match(line)
        if not row:
            continue
        body = row.group("body")
        application = APPLICATION_RE.search(body)
        if application:
            add(application.group("name"))
        if re.search(r"(?:^|\s)SRD(?:\s|$)", body):
            add("SRD")
        prefix = re.split(r"\s{2,}", body.strip(), maxsplit=1)[0].strip()
        if (
            prefix not in IGNORED_PREFIXES
            and len(prefix) > 3
            and not prefix[0].isdigit()
            and not APPLICATION_RE.search(prefix)
        ):
            add(prefix)

    # Az alkalmazásnév informatívabb, mint ugyanannak a szolgálatnak a rövid neve.
    redundant = {
        "Amatőrrádiózás": "Amatőrrádiózás",
        "Műholdas amatőrrádiózás": "Műholdas amatőrrádiózás",
    }
    for service, application in redundant.items():
        if application in uses and uses.count(service) > 1:
            uses.remove(service)
    return uses


def extract(text: str) -> list[dict[str, object]]:
    lines = text.splitlines()
    headers: list[tuple[int, re.Match[str]]] = []
    for index, line in enumerate(lines):
        match = BAND_RE.match(line)
        if match:
            headers.append((index, match))

    bands: list[dict[str, object]] = []
    for position, (index, match) in enumerate(headers):
        start_hz = to_hz(number(match.group("start")), match.group("unit"))
        end_hz = to_hz(number(match.group("end")), match.group("unit"))
        if end_hz < 10_000_000 or start_hz > 24_000_000_000 or end_hz <= start_hz:
            continue
        next_index = headers[position + 1][0] if position + 1 < len(headers) else len(lines)
        band_lines = lines[index + 1 : next_index]
        uses = extract_uses(band_lines, start_hz, end_hz)
        bands.append(
            {
                "id": f"nmhh-{match.group('row')}",
                "row": int(match.group("row")),
                "start_hz": max(start_hz, 10_000_000),
                "end_hz": min(end_hz, 24_000_000_000),
                "range_label": match.group(0).strip().split(maxsplit=1)[1],
                "uses": uses,
            }
        )
    return bands


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: extract-nmhh-frequency-bands.py INPUT.txt OUTPUT.json")
    source, target = map(Path, sys.argv[1:])
    bands = extract(source.read_text(encoding="utf-8", errors="replace"))
    target.write_text(
        json.dumps(
            {"schema_version": 1, "bands": bands}, ensure_ascii=False, separators=(",", ":")
        ),
        encoding="utf-8",
    )
    print(f"wrote {len(bands)} bands to {target}")


if __name__ == "__main__":
    main()
