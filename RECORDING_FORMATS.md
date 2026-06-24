# Recording formátumok és állapotok

## Spectrum

A meglévő spectrum recording formátum kompatibilis maradt:

```text
recording-id/
├── metadata.json
├── frames.ndjson.zst
└── checksum.sha256
```

Power-spectrum frame-eket tárol; utólagos hangdemodulációra önmagában nem
alkalmas, mert nincs komplex IQ adat.

## IQ / SigMF

```text
recording-id/
├── metadata.json
├── recording-id.sigmf-meta
├── recording-id.sigmf-data
└── checksum.sha256
```

Támogatott mock/absztrakciós datatípus: `cf32_le`, `ci16_le`. Metadata tartalmaz
sample rate-et, center frekvenciát, forrást, eszközt, antennát, downconvertert,
packet loss/overflow számlálót és checksumot. A lezárás staging könyvtárból,
fsync és atomikus rename után történik.

## Audio / WAV

Mono vagy sztereó PCM16 little-endian WAV, sidecar `metadata.json` és SHA-256.
A demoduláció, center frekvencia, sample rate és forrás tárolható. Valós
SDRangel audio output még nem lett hardverrel ellenőrizve.

## Tárhelyvédelem

- minimum szabad tárhely;
- felvételenkénti maximális méret és időtartam;
- checksum verification;
- korrupt vagy hiányos recording jelölése;
- retention csak dry-run jelöltlistát ad;
- automatikus törlés nincs.

## Megbízhatósági állapot

- Spectrum: `implemented_mock_tested`;
- IQ/SigMF writer/reader/checksum: `implemented_mock_tested`;
- Audio/WAV writer/reader/checksum: `implemented_mock_tested`;
- Aaronia/USRP IQ: `hardware_not_tested`;
- SDRangel audio output: `not_configured` vagy `configured_not_tested`.
