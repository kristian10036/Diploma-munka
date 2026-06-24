# Architektúra

Renderelt diagram: [SVG](docs/architecture.svg) · [PNG](docs/architecture.png)

## Áttekintő diagram

```mermaid
flowchart LR
  subgraph Native[Debian host – natív, hardverközeli réteg]
    HW1[Aaronia SPECTRAN V6]
    HW2[Ettus USRP]
    UHD[UHD driver]
    ARSDK[Aaronia RTSA API]
    SDR[sdrangelsrv\nREST control plane]
    RF[C++ rf-agent\ncentral producer]
    AP[aaronia-probe\nizolált subprocess]
    UP[usrp-probe\nizolált subprocess]
    HW1 --> ARSDK --> AP --> RF
    HW2 --> UHD --> UP --> RF
    RF -. control .-> SDR
  end

  subgraph Docker[Docker Compose – hordozható alkalmazási réteg]
    ING[spectrum-ingest\nvalidation + latest-frame fan-out]
    API[FastAPI backend]
    DB[(PostgreSQL + TimescaleDB + pgvector)]
    MQTT[Mosquitto]
    KIS[Kismet]
    OLL[Ollama\nchat + embeddings]
    WEB[Nginx + frontend]
    RF -->|SpectrumFrame WebSocket| ING
    ING --> WEB
    API <--> DB
    API <--> MQTT
    KIS --> API
    API <--> OLL
    API -->|/metrics| PROM
    ING -->|metrics| PROM
    PROM -->|allow-listed query API| API
    WEB --> API
  end

  FILES[(Host filesystem\nrecordings, uploads, Kismet, ML, backups)]
  RF --> FILES
  API --> FILES
  KIS --> FILES
```

## RF adatút

```mermaid
flowchart TD
  SRC[IRfSource\nmock / replay / future worker] --> PROD[Single central producer]
  PROD --> LATEST[Latest validated SpectrumFrame]
  PROD --> REC[zstd NDJSON recording writer]
  LATEST --> WS1[WebSocket client A]
  LATEST --> WS2[WebSocket client B]
  LATEST --> ING[spectrum-ingest]
```

A központi producer miatt:

- recording kliens nélkül is készül;
- több WebSocket-kliens nem fogyasztja el egymás elől a frame-eket;
- lassú kliens nem hoz létre korlátlan sort;
- minden downstream ugyanazt a sequence-folyamot látja, de lassú kliens
  kihagyhat köztes frame-eket.

## RAG és offline Ollama

```mermaid
flowchart LR
  DOC[Dokumentum] --> CHUNK[Átfedő chunkolás]
  CHUNK --> EMB[Embedding provider\nlocal_hash vagy Ollama]
  EMB --> PG[(pgvector HNSW)]
  Q[Kérdés] --> QEMB[Kérdés embedding]
  QEMB --> PG
  PG --> TOPK[Top-k forráschunk]
  SQL[(Mérési SQL context)] --> PROMPT[Grounded prompt]
  TOPK --> PROMPT
  PROMPT --> LLM[Offline Ollama chat model]
  LLM --> ANSWER[Válasz + source_records]
```

A RAG **nem maga az AI-modell**. A RAG releváns dokumentumrészeket keres ki;
a generáló Ollama-modell ezek és a mérési SQL-kontextus alapján fogalmaz választ.
Az embeddingmodell és a chatmodell egymástól függetlenül cserélhető.

## Felelősségi határok

| Réteg | Felelősség | Nem tartozik ide |
|---|---|---|
| `rf-agent` | source lifecycle, SpectrumFrame, recording, hardverprobe, SDRangel vezérlés | PostgreSQL üzleti adatok |
| `spectrum-ingest` | upstream reconnect, schema-validáció, bounded fan-out, metrikák | hardverdriver |
| backend | DB, API, session, Kismet/BLE, ML, assistant/RAG, monitoring proxy | nagy sebességű IQ streaming |
| PostgreSQL | metadata, ritkított mérések, riasztások, ML/RAG index | teljes IQ vagy teljes recording |
| fájlrendszer | recording, IQ/audio/PCAP/Kismet, ML modellek, backup | relációs lekérdezési logika |
| Ollama | offline embedding és válaszgenerálás | mérési forrás vagy igazságforrás |
| Prometheus | helyi metrikatárolás és idősoros lekérdezés | Grafana, RF-jelfeldolgozás vagy felhős telemetria |


## Monitoring határ

A Prometheus nem publikus felület és nem elemzi az RF-jelet. A backend, az ingest
és későbbi exporterek metrikáit gyűjti. A frontend kizárólag a backend
allow-listás monitoring API-ját használja; Grafana és `remote_write` nincs.
