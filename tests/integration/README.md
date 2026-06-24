# Integrációs tesztek

Az RF agent futása mellett:

```bash
python tests/api/test_rf_agent_rest.py
python tests/websocket/test_rf_agent_spectrum.py
```

A WebSocket teszthez a backend image-ben már telepített `websockets` csomag használható. A tesztek csak olvasnak, kivéve az izolált Aaronia probe explicit indítását; volume-ot és mérési adatot nem módosítanak.
