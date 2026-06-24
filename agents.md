# agents.md

## Project context

This project is a Docker-based internal RF/TSCM monitoring platform intended to run on Ubuntu 22.04 Server inside a local network.

The long-term goal is an IRCOS-like spectrum monitoring and analysis system with:

* custom web dashboard
* spectrum monitoring
* NMHH frequency reference layer
* site-specific baseline override logic
* anomaly detection
* Kismet-based Wi-Fi observation import/integration
* Bettercap BLE observation import/integration
* CSV import from external instruments
* TimescaleDB/PostgreSQL storage
* later RAG/AI-based analysis
* later ML-based signal classification

## Main architectural rule

Do not treat spectrum, Wi-Fi and Bluetooth as separate unrelated apps.

Treat the system as a measurement station:

location
→ measurement_session
→ spectrum observations
→ Wi-Fi observations
→ Bluetooth observations
→ anomalies
→ reports
→ analysis/RAG

Every collected record should be connected to:

* location_id or location_name
* measurement_session_id
* source_type
* source_name
* timestamp
* raw_payload where useful
* normalized fields for analysis

## Safety and scope

Do not implement offensive Wi-Fi or Bluetooth functions.

Kismet and Bettercap integration must be used only for passive observation/import in authorized environments.

Do not implement attack automation, credential harvesting, deauthentication, exploitation, or unauthorized interception features.

## Coding rules

* Do not touch real .env secrets.
* Do not commit API keys or passwords.
* Keep .env.example updated.
* Do not delete working endpoints.
* Do not remove existing frontend functionality unless explicitly requested.
* Prefer small working steps over large rewrites.
* If a hardware protocol is unknown, create a clean interface/stub and mark TODO clearly.
* Do not claim that real hardware integration is complete if only a simulator/stub exists.

## Docker/server rules

The project should remain Docker-first and portable between machines.

Core services should run in Docker:

* reverse-proxy
* frontend
* backend
* TimescaleDB/PostgreSQL
* Mosquitto if needed
* Ollama if enabled
* import/analysis workers

Hardware-near collectors may need host networking or privileged mode later, but keep the core platform portable.

## Backend structure target

Move gradually toward:

python-processor/
app/
main.py
config.py
db.py
routers/
services/
services/spectrum_sources/
services/collectors/
services/rag/
services/ml/

Do not perform a massive refactor in one step.

## Work process

When given a plan file, read it first.

Work only on the requested phase.

After each phase:

* list modified files
* list new endpoints
* list migrations
* explain what is complete
* explain what is only stub/preparation
* provide test commands
