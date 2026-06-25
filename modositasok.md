P3.
Apró utómunka a viewport-bekötésen. A funkció kész és a tesztek zöldek; ezek
csak csiszolások. Csak a minimálisan szükséges fájlokat módosítsd, a meglévő
viewport-controller.js logikáját NE írd át.

P1.1  Üres select-kattintás ne indítson retune-t. A spectrumCanvas mouseup
      ágában az endInteraction(currentRfViewport())-ot csak akkor hívd meg, ha a
      gesztus ténylegesen módosította a nézetet (vagyis lefutott egy setView a
      drag/select/overview ágban). Plain kattintásnál (dx<=8, nincs nézetváltás)
      ne menjen ki viewport-kérés. Egészítsd ki a tests/frontend/
      test_viewport_wiring.js-t egy esettel: beginDrag()+endDrag(0) (nincs
      elmozdulás) után ne keletkezzen request.

P1.2  Dedikált, perzisztens felbontás-readout. Vegyél fel a Spektrum readout
      sávba egy „Felbontás" mezőt, és az acceptSweep()-ben minden frame-nél
      frissítsd a currentSpectrumFrame.stepFrequencyHz-ből (Hz/bin vagy kHz/bin,
      a formatSpan mintájára). A meglévő, viewport-state-hez kötött átmeneti
      üzenet (kért vs. tényleges) maradjon. A tests/frontend/test_ui_static.py
      contractját igazítsd, ha új id-t vezetsz be.

P1.3  Capabilities frissítése forrásváltáskor. Hívd meg a
      refreshRfAgentCapabilities()-t a source start/stop/select műveletek után
      is, ne csak init-kor és a kézi „Frissítés" gombon.

P2.1  Backend proxy-szintű validációs teszt. A tests/api/test_rf_agent_rest.py-
      ba (vagy a megfelelő API-tesztbe) adj egy FastAPI TestClient esetet, amely
      a /api/rf-agent/source/viewport-ra hibás bodyt küld (pl. mode="continuous"
      vagy maximum_points=1), és 422-t vár az agent meghívása NÉLKÜL (a Pydantic
      ViewportRequest validáció miatt). Ne indíts hozzá RF Agentet.

Futtasd a node frontend teszteket és a scripts/offline-acceptance.sh-t; minden
maradjon zöld.
