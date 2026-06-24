# Automatikus USRP és HackRF hardverkezelés

A hardveres stack `RF_SOURCE_MODE=auto` módban öt másodpercenként ellenőrzi az
IQ-képes SDR-eket. A prioritás USRP, HackRF, majd Aaronia. Ha az USRP vagy a
HackRF eltűnik, a rendszer visszaáll az Aaronia forrásra.

## USRP X310

Az X310 Ethernetes, nem USB-s eszköz. UHD-kompatibilis FPGA és a használt
porttal azonos alhálózatra konfigurált dedikált host NIC szükséges. Gyári
alapértékeknél tipikusan:

- 1 GbE Port 0: USRP `192.168.10.2`, host `192.168.10.1/24`;
- 10 GbE Port 0: USRP `192.168.30.2`, host `192.168.30.1/24`;
- 10 GbE Port 1: USRP `192.168.40.2`, host `192.168.40.1/24`.

A hálózat egyszeri beállítása után az rf-agent host network módban UHD
broadcasttal automatikusan felismeri az eszközt. Több USRP esetén állítsd be az
`USRP_DEVICE_ARGS` értékét, például `type=x300,addr=192.168.30.2`.

## USRP X410

Az X410 kezelő RJ45 interfésze alapértelmezetten DHCP-t használ. A hostnak és az
X410-nek azonos alhálózaton kell lennie; nagy sebességű IQ streaminghez 10/100
GbE adatkapcsolat szükséges. Több eszköznél használható például:
`USRP_DEVICE_ARGS=type=x4xx,addr=<IP>`.

## HackRF One

A HackRF One USB-n csatlakozik. A Compose stack átadja a `/dev/bus/usb`
eszközöket, telepíti a libhackrf/SoapyHackRF drivert, és a `SDR_DEVICE_GID`
csoporttal ad hozzáférést. Ennek alapértéke ezen a gépen `46` (`plugdev`).

## Hang

USRP és HackRF esetén a nyers IQ-adatból natív AM, NFM vagy WFM demoduláció
készül, 48 kHz-es mono PCM-ként a meglévő böngészős hangútba továbbítva. Az
Aaronia spektrumút változatlan; ahhoz továbbra sincs nyers IQ-forrás.

A hardver nélküli tesztek a driver-, fallback-, spektrum- és API-szerződést
ellenőrzik. A tényleges RF szinteket, túlcsordulást, mintavesztést és hangot az
adott X310/X410 daughterboarddal, hálózattal vagy HackRF példánnyal külön kell
validálni.
