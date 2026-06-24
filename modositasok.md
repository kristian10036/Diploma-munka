Kösd be a refaktorált projekt élő zoom/pan működésébe a már kész, de jelenleg
be nem kötött viewport-controller.js-t, hogy a spektrumfelbontás ténylegesen
újrahangolódjon az RF Agentnél, ne csak grafikailag nagyítson.

ELŐSZÖR térképezd fel a teljes adatútvonalat, és írd le, pontosan mely fájlokat
és sorokat fogsz módosítani, MIELŐTT kódot írsz. Csak a minimálisan szükséges
fájlokat módosítsd.

────────────────────────────────────────────────────────────────────────
MEGLÉVŐ, KÉSZ ALAPOK – NE írd újra őket
────────────────────────────────────────────────────────────────────────
- python-processor/static/viewport-controller.js (UMD, globális
  ViewportController): debounce (400–500 ms), targetPoints() canvas-szélesség +
  maximum_spectrum_points alapján, desired_rbw_hz = span/points, observeFrame(),
  WAITING_FOR_MATCHING_FRAME → onMatchingFrame már implementálva + unit-tesztelt
  (tests/frontend/test_viewport_controller.js).
- api-client.js: updateRfAgentViewport() → POST /api/rf-agent/source/viewport.
- backend router: POST /api/rf-agent/source/viewport proxy (rf_agent.py).
- RF Agent: POST /source/viewport (http_server.cpp:163), mock end-to-end működik
  (SourceManager::configureViewport → setCenterFrequency/setSpan/
  setSpectrumPointCount), replay/hardver capability alapján elutasít.
- SpectrumFrame hordozza: num_points, step_frequency_hz, sample_rate_hz, rbw_hz;
  a spectrum-frame-adapter.js kiparszolja: numPoints, stepFrequencyHz, rbwHz.

────────────────────────────────────────────────────────────────────────
P0 – e nélkül a bekötés némán nem csinál SEMMIT
────────────────────────────────────────────────────────────────────────
P0.1  Capabilities-lekérés. Jelenleg a frontend SEHOL nem kéri le a
      capabilities-t, és a /api/spectrum/source/status nem adja vissza a
      maximum_spectrum_points / viewport_control mezőket. Adj api-client
      függvényt a meglévő GET /api/rf-agent/capabilities végponthoz, és az
      index.html init során + a forrásállapot frissítésekor (forrásváltáskor)
      hívd meg a controller setCapabilities()-ét. Enélkül supportsViewport()
      mindig false → egyetlen kérés sem megy ki.
P0.2  Script include: add hozzá az index.html-hez a
      <script src="/viewport-controller.js"></script> sort a demod-passband.js
      mintájára, és példányosítsd a controllert.
P0.3  setCanvasPhysicalWidth(spectrumCanvas.width) bekötése a resizeAll()-ba
      (init + minden resize).
P0.4  Interakciós hookok a MEGLÉVŐ handlerekbe: wheel (zoomAt), dblclick,
      select-drag és overview-drag (setView végpontjai), pan, start/stop input,
      zoom-gombok. beginInteraction() interakció közben, endInteraction(viewport)
      a végén; debounce után menjen ki a kérés.
P0.5  observeFrame(parsed, aktívSourceType) hívása az acceptSweep()-ből, hogy a
      frontend csak az ÚJ viewportnak megfelelő, később érkező frame után
      váltson kész (STREAMING) állapotba.

────────────────────────────────────────────────────────────────────────
P1 – helyesség és minőség (a feature működik, de hibás/hiányos enélkül)
────────────────────────────────────────────────────────────────────────
P1.1  sendRequest adapter: a controllernek átadott sendRequest NE a nyers fetch
      Promise-t adja vissza. Awaitold a választ, és res.ok===false esetén
      dobj hibát (a fetch 4xx/5xx-re is resolve-ol), különben a controller
      ERROR ága és a „constrained" eset sosem sül el. Sikeres ágon parse-old a
      JSON-t és add tovább (status: accepted|constrained, num_points,
      step_frequency_hz stb.).
P1.2  TÉNYLEGES Hz/bin vagy kHz/bin a felületen a beérkező frame
      step_frequency_hz-jéből számolódjon, NE a desired_rbw_hz = span/points
      kérésből. A kérés (desired) és a tényleges érték legyen vizuálisan
      megkülönböztethető; constrained válasznál jelezd, hogy a hardver kevesebb
      pontot adott a kértnél.
P1.3  A controller state-jét (PENDING/RETUNING/WAITING/STREAMING/ERROR) a
      MEGLÉVŐ státusz-readoutokon jelenítsd meg, ne vezess be új UI-keretet.
P1.4  Ha viewport_control=false (replay / jelenlegi hardveradapterek), NE küldj
      viewport-kérést – csak a grafikus zoom maradjon (supportsViewport() ezt
      kezeli). Őrizd meg a demo, replay, Aaronia és USRP működést.
P1.5  NE módosítsd a globális DC–24 GHz tengelymodellt (FULL_MIN/FULL_MAX,
      lásd SPECTRUM_DATA_FLOW.md). A viewport-kérés azt változtatja, amit a
      hardver MÉR, nem a vizuális tengelyt – csak finomabb mérést kérj a látható
      ablakra.
P1.6  Tesztek a MEGLÉVŐ harnesszel (ne hozz be jestet):
      - frontend: kövesd a tests/frontend/test_viewport_controller.js node-alapú
        (require) mintáját egy BEKÖTÉSI integrációs teszttel: fake canvas, fake
        capabilities, szimulált frame → ellenőrizd, hogy zoom után kimegy a
        kérés, és csak az illeszkedő frame után lesz STREAMING; valamint hogy
        viewport_control=false esetén nem megy ki kérés. Regisztráld a
        scripts/offline-acceptance.sh-ban.
      - backend: a tests/api/test_rf_agent_rest.py mintájára fedd le a viewport
        proxy útvonalat (valid kérés, valamint hibás/elutasított eset).

────────────────────────────────────────────────────────────────────────
P2 – hardening (döntési pontok, külön körben is mehet)
────────────────────────────────────────────────────────────────────────
P2.1  Pydantic ViewportRequest séma a backendben. A configure_rf_agent_viewport
      jelenleg nyers dict[str, Any]-t fogad validáció nélkül. Adj egy
      ViewportRequest sémát a schemas.py-ba (request_id: str 1..128;
      mode: Literal["fixed","sweep"]; center_frequency_hz, span_hz: pozitív int;
      maximum_points: int >=2; desired_rbw_hz: opcionális float), és a routerben
      ezt használd. Frissítsd az OpenAPI snapshotot, ha szükséges
      (tests/test_openapi_snapshot.py / fixtures/openapi_snapshot.json).
P2.2  rbw_hz a C++ viewport-válaszban – DÖNTÉSI PONT, alapból HAGYD KI.
      A handler ma step_frequency_hz-t és num_points-ot ad vissza, rbw_hz-t nem.
      Megfontolás: a szinkron viewport-válasz csak BECSLÉST tudna adni (a valódi
      RBW az FFT-hossztól és ablakfüggvénytől függ, és csak frame-időben áll elő
      a fft_pipeline-ban). A hiteles RBW már megérkezik a frame-ben (rbw_hz).
      Ezért az ALAPÉRTELMEZÉS: ne módosítsd a választ, a UI a frame-ből dolgozzon.
      CSAK akkor add hozzá a válaszhoz a {"rbw_hz", (double)step} becsült mezőt,
      ha kifejezetten szükséges; ebben az esetben jelöld a mezőt becslésként
      (pl. predicted), és tartsd meg, hogy a kijelzett tényleges érték továbbra
      is a frame step_frequency_hz-jéből jön. Ne vezess be ettől eltérő wire-
      formátumot.

────────────────────────────────────────────────────────────────────────
TILOS
────────────────────────────────────────────────────────────────────────
- bináris WebSocket vagy shared memory bevezetése;
- a globális tengelymodell vagy a jelenlegi adatút-architektúra átírása;
- a meglévő, kész és tesztelt viewport-controller.js logikájának újraírása.
