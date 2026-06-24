# Valós idejű demodulációs passband — fejlesztői beszámoló

Ez a dokumentum a Spectrum Monitor és a Moduláció panel összekapcsolását írja le:
egy professzionális spektrumanalizátorokhoz hasonló, közvetlenül a spektrumon
szerkeszthető demodulációs passband, kétirányú panel-szinkronnal és az aktív
SDRangel csatorna valós idejű frissítésével.

## 1. Hogyan működött korábban a Moduláció panel

A panel önállóan, a spektrumtól elszigetelten működött. A jobb kattintásos
„Hangolás és demoduláció" beírta a frekvenciát a `sdrangelFrequency` mezőbe, a
`startSdrangelDemod()` pedig egymás után hívta a `/api/rf-agent/sdrangel/tune` és
a `/api/rf-agent/sdrangel/demod/start` végpontokat (demodulator, bandwidth_hz,
squelch_db, audio sample rate, audio device, volume mezőkkel). A böngésző 48 kHz
mono PCM hangot kapott.

## 2. Miért nem volt kapcsolata a Spectrum Monitorral

A panel és a spektrum **külön frekvencia- és bandwidth-értéken** dolgozott: a sávot
a spektrum nem rajzolta ki, az indítás után a bandwidth-mező módosítása nem hatott
az aktív SDRangel csatornára, és nem létezett élő (update) végpont — csak start és
stop. A spektrumadat (teljesítményspektrum) és a demoduláció (IQ-adatút) **két külön
adatút**; a `SpectrumFrame`-ből önmagában nem demodulálható hang, ezt a megoldás
végig tiszteletben tartja.

## 3. Hogyan tárolódik az új közös demodulációs állapot

Egyetlen igazságforrás: a `demodState` objektum (`DemodPassband.createDemodState()`).
A Spectrum Monitor és a panel is ebből dolgozik, nincs külön frekvencia/bandwidth a
két helyen. Az állapot a kívánt és a tényleges értékeket is külön tartja:
`requestedFrequencyHz` / `appliedFrequencyHz`, `requestedBandwidthHz` /
`appliedBandwidthHz`, valamint `deviceCenterFrequencyHz`, `inputFrequencyOffsetHz`,
`captureBandwidthHz`, `channelIndex`, `pendingUpdate`, `lastError`.

A geometria-, snap-, hitbox-, hangolásterv- és debounce/sequence-logika egy tiszta,
DOM-mentes modulban él (`static/demod-passband.js`), amely Node alatt önállóan
egységtesztelt (`tests/frontend/test_demod_passband.js`, 35 assertion). Az
`index.html` csak a rajzolást és az egéreseményeket köti rá.

## 4. Hogyan rajzolódik a passband

A `drawDemodPassband()` a `drawMarkers()` előtt fut, a grid és az unmeasured overlay
után, a spektrumgörbével kompatibilis rétegben — nem keveredik az NMHH referenciával,
ismert jelekkel, maxholddal, referenciaeltéréssel vagy a kijelölési zoom téglalappal.
Tartalom: középfrekvencia-vonal, bal/jobb sávhatár (fogantyú-markerekkel), áttetsző
kitöltés (a görbe alatta látszik) és felirat `NFM | 12.5 kHz | 145.500000 MHz`
formában. Inaktív, kiválasztott állapotban halvány; aktív demodulációnál kiemelt;
hiba esetén piros, pending állapotban szaggatott.

## 5. Hogyan kezelhetők a sávszélek

Demod módban a passband külön hitboxokkal rendelkezik: `leftHandle`, `rightHandle`,
`centerLine`, `body`. Prioritás: bal fogantyú > jobb fogantyú > középvonal > sáv
belseje > normál spektrumkattintás. A fogantyúk minimum ~11 képernyőpixel szélesek,
így 500 Hz-es CW-sávnál is megfoghatók (`hitTestPassband`). A bal/jobb él húzása a
`bandwidthFromEdge()` szerint módosítja a sávszélességet, a középvonal/body húzása a
frekvenciát, miközben a sávszélesség marad.

## 6. Hogyan működik az USB és LSB aszimmetrikus sáv

A `computePassbandEdges()` mód szerint:
- szimmetrikus (AM, NFM, WFM, BFM, DSB, DSD, M17, DAB, FREEDV, CW):
  `start = f − bw/2`, `stop = f + bw/2`;
- USB: `start = f`, `stop = f + bw` (jobbra egyoldalas);
- LSB: `start = f − bw`, `stop = f` (balra egyoldalas);
- CW: keskeny, középre igazított (szimmetrikus geometria).

A rajzolás minden esetben a tényleges SDRangel szűrőviselkedést tükrözi. A backend
oldalon az SSB-családnál a `lowCutoff` előjele (LSB negatív) és a `dsb` flag is ennek
megfelelően áll be.

## 7. Hogyan frissül valós időben az SDRangel csatorna

Inaktív demodulációnál a passband szerkesztése csak a frontend állapotot és a
panelmezőket változtatja — nincs API-hívás. Aktív demodulációnál
(`demodState.active` és érvényes `channelIndex`) a `scheduleDemodUpdateIfActive()`
egy `PATCH /api/rf-agent/sdrangel/demod/update` kérést állít össze, amelyet a
debounce-os scheduler küld ki. A demodulátor NEM áll le és NEM jön létre újra; a
meglévő csatorna settings végpontja PATCH-elődik. Hiba esetén a hang nem áll le, az
utolsó igazolt beállítás marad, a channel index megmarad, és a passband jelzi a
kívánt/alkalmazott eltérést.

## 8. Milyen SDRangel settings mezők kerülnek PATCH-elésre

A `buildDemodulatorChannelSettings()` (megosztott, hálózatmentes helper) a plugin
által ténylegesen támogatott mezőket választja ki a pillanatnyi settings alapján:
- `inputFrequencyOffset`
- `rfBandwidth` / `bandwidth` / `rfBandwidthHz` (LSB-nél negatív)
- SSB geometria: `lowCutoff` (LSB negatív, CW=100, egyébként 300) és `dsb`
- `squelch` / `squelchDB` / `squelchDb`
- `volume` / `audioVolume`
- csak indításkor: `audioMute`/`mute`, `audioDeviceName`/`audioDevice`,
  `audioSampleRate`/`audioSampleRateHz`, BFM-nél `audioStereo`/`stereo`.

Élő frissítésnél az audio-routing (eszköz/mintavétel/mute/stereo) NEM kerül újra
beállításra, hogy egy passband-húzás ne konfigurálja át a hangkimenetet.

## 9. Mikor történik DeviceSet retune és mikor csak channel offset update

A `planChannelTuning()` dönt:
- ha a kiválasztott frekvencia az IQ-forrás aktuális capture tartományán belül van:
  `channel offset = kiválasztott frekvencia − device center`, és csak az
  `inputFrequencyOffset` módosul;
- ha kívül esik: a DeviceSet áthangolása az új középfrekvenciára, offset = 0;
- ha a capture tartomány nem állapítható meg megbízhatóan: konzervatív fallback —
  retune a kiválasztott középfrekvenciára, offset 0 (ez rövid hangkimaradást
  okozhat). A backend a `retune_device_center_hz` mező jelenlétéből tudja, hogy a
  központi frekvenciát is hangolnia kell.

## 10. Hogyan lett elkerülve a request storm

A `createUpdateScheduler()` ~150 ms debounce-szal dolgozik: a vizuális sáv minden
egérmozdulatnál frissül, de az SDRangel update csak a debounce letelte után fut. Sok
mousemove egyetlen kérést eredményez. Monoton sequence szám védi a sorrendet: ha egy
régi (lassú) válasz az újabb után érkezik, a scheduler eldobja, így nem írja felül az
újabb állapotot.

## 11. Milyen tesztek futottak

Ebben a környezetben ténylegesen lefuttatva:
- **Frontend modul (Node):** `tests/frontend/test_demod_passband.js` — 35 assertion
  PASS. Lefedi: spektrumkattintás → demod frekvencia; panel ↔ passband azonosság;
  NFM szimmetria, USB jobbra, LSB balra; bal/jobb fogantyú bandwidth; body drag
  center; binre igazítás és durva felbontás jelzése; hitbox-prioritás keskeny sávnál;
  bandwidth clamp (negatív/nulla/min/max/capture); offset vs retune terv; debounce
  egyetlen kérésbe vonja a sok mozdulatot; régi válasz nem ír felül.
- **Megosztott C++ settings helper:** `rf-agent/tests/test_sdrangel_demod_settings.cpp`
  — 20 check PASS (g++ -std=c++17 -Wall -Wextra -Wpedantic). Lefedi a helyes
  plugin-mezők kiválasztását: update vs start mezőkészlet, LSB negatív bandwidth +
  lowCutoff, DSB dsb=1, CW 500 Hz default, ismeretlen mező kihagyása, „default"
  audio eszköz kihagyása.
- **Backend (pytest):** `tests/test_sdrangel_demod_update.py` — 6 PASS. PATCH proxy a
  helyes útvonalra és metódussal; érvénytelen bandwidth és hiányzó/negatív channel
  index elutasítása; opcionális mezők kihagyása; rf-agent elérhetetlenség → 503.
- **Regresszió:** a teljes Python csomag **65 passed** (korábbi 59 + 6 új), mindhárom
  korábbi JS teszt zöld.

CI-ben fordulnak (itt boost hiányában nem fordítva): a `test_sdrangel_client.cpp`
kiegészült az `updateDemodulator` letiltott/hiányzó-channel validációval.

## 12. Történt-e élő IQ/hangteszt

Nem. Ebben a környezetben nincs SDRangel, sem IQ-képes hardver, így élő hang/IQ teszt
nem futott. A control-plane logika hálózatmentesen tesztelt (settings-mezők, állapot,
debounce/sequence). Az élő PATCH-frissítés a valós SDRangel példánnyal a helyszínen
ellenőrizendő.

## 13. Milyen hardver szolgáltatta a spektrumot

Ebben a fejlesztői munkamenetben semmilyen — a frontend a meglévő SpectrumFrame
adatutat használja (Aaronia SPECTRAN V6 / USRP X410 / CSV import). A megoldás
forrásfüggetlen: a passband a `startFrequencyHz`/`stepFrequencyHz`/`numPoints` natív
rácsra igazít, függetlenül attól, mi adja a frame-et.

## 14. Milyen hardver szolgáltatta az IQ-adatot

Egyik sem (nincs élő teszt). A megoldás kifejezetten forrásfüggetlen: a spektrum
jöhet Aaroniából, miközben a demodulációt egy IQ-képes forrás (SDRangel Rx DeviceSet
/ USRP / HackRF / SoapySDR) végzi. A `demodState` és a passband interfész közös,
így a későbbi USRP/HackRF integráció ugyanazt használja.

## 15. Milyen korlát maradt

- Élő SDRangel PATCH-frissítés valós hardveren még nem igazolt (lásd 12. pont).
- A capture-sávszélesség becslése jelenleg a frame `sampleRateHz` mezőjéből vagy a
  `demodState.captureBandwidthHz`-ből jön; ahol ez nem megbízható, a konzervatív
  retune fallback lép életbe (rövid hangkimaradás lehetséges).
- A „Jel BW becslése" (mért jelsávszélesség a spektrumból) interfész elő van
  készítve (`demodState.measuredSignal`, külön szaggatott határ rajzolása, külön
  „Mért jel BW" vs „Demod filter BW" kijelzés), de az automatikus becslő gomb
  bekötése és kalibrálása valós jelen még hátravan; a becsült érték a felhasználó
  jóváhagyása nélkül sosem módosítja a demod szűrőt.
- A frontend bandwidth-korlát capability-alapú, de nem helyettesíti a backend
  validációt; a plugin tényleges min/max képességeit élőben érdemes finomítani.
