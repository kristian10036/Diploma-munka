# RF felvételek

A rendszer három, egymástól szándékosan elkülönített felvételtípust kezel.

| Típus | Formátum | Mire alkalmas? | Hardverfüggetlen állapot |
|---|---|---|---|
| `spectrum` | SpectrumFrame NDJSON, opcionális Zstandard tömörítéssel | Spektrum visszajátszás, referencia és ML-adathalmaz | RF-agent mock/replay tesztelt |
| `iq` | SigMF-kompatibilis `.sigmf-meta` + `.sigmf-data` | Későbbi demoduláció és DSP | writer/reader/checksum mock tesztelt; hardver nem tesztelt |
| `audio` | PCM16 WAV + `metadata.json` | Demodulált hang tárolása | mock WAV tesztelt; SDRangel audio nem tesztelt |

## Spectrum recording

Egy meglévő spectrum recording könyvtára visszafelé kompatibilisen:

```text
recording-id/
├── metadata.json
├── frames.ndjson.zst
└── checksum.sha256
```

A tömörítetlen `frames.ndjson` is támogatott. Minden sor egy `SpectrumFrame v1`.
A replay a checksumot, a tömörítési streamet, a méretkorlátot és a frame-sémát
ellenőrzi. A power-spektrum **nem tartalmaz komplex IQ-mintákat**, ezért abból
utólagos AM/NFM/WFM/SSB demoduláció nem végezhető.

## IQ recording – SigMF

```text
recording-id/
├── metadata.json
├── recording-id.sigmf-meta
├── recording-id.sigmf-data
└── checksum.sha256
```

Támogatott előkészített datatípusok: `cf32_le`, `ci16_le`. A metadata tartalmazza
a sample rate-et, center frekvenciát, időbélyeget, forrást, eszközt, antennát,
downconverter-profilt, capture szegmenst, packet-loss/overflow számlálót és a
SHA-256 checksumot. A teljes IQ-adat nem kerül PostgreSQL-be.

## Audio recording

```text
recording-id/
├── metadata.json
├── audio.wav
└── checksum.sha256
```

A WAV formátum PCM signed 16-bit little-endian. A forrás később SDRangel vagy
más, konkrétan ellenőrzött demodulátor lehet. A jelenlegi hardverfüggetlen teszt
csak determinisztikus mock hangot használ.

## Atomikus lezárás és tárhelyvédelem

Az új writer először rejtett `.partial` könyvtárba ír, flush/fsync után checksumot
és metadatát készít, majd az egész könyvtárat atomikusan nevezi át. Félbehagyott
vagy sérült recording a katalógusban külön állapotot kap.

Konfiguráció:

- `RECORDINGS_MIN_FREE_BYTES`
- `RECORDINGS_MAX_BYTES`
- `RECORDINGS_MAX_DURATION_SECONDS`
- `RECORDINGS_RETENTION_DAYS`

A retention endpoint kizárólag **dry-run tervet** készít. Nem töröl recordingot;
a tényleges eltávolítás később külön, auditált karanténművelet lehet.
