# Natív service-ek

A hardverközeli komponensek a végleges szerveren natívan is futtathatók.

## RF agent

```bash
sudo useradd --system --home /var/lib/rfagent --create-home rfagent || true
sudo install -d -o rfagent -g rfagent /srv/diploma/recordings/spectrum
sudo install -d -m 0750 /etc/diploma
sudo install -m 0644 deploy/systemd/diploma-rf-agent.service /etc/systemd/system/
sudo install -m 0640 deploy/systemd/rf-agent.env.example /etc/diploma/rf-agent.env
sudo systemctl daemon-reload
sudo systemctl enable --now diploma-rf-agent
sudo systemctl status diploma-rf-agent
```

A környezeti fájlt indulás előtt szerkeszteni kell. Az Aaronia és UHD eszközök
jogosultságát udev szabályokkal add meg, ne rootként futtasd az agentet.

## SDRangel Server

A service-fájl példa. Csak akkor aktiváld, ha a natív `sdrangelsrv` ténylegesen
telepítve van, és a saját verziód parancssori kapcsolói megfelelnek az
`ExecStart` sornak. A control plane és a data plane két külön állapot.
