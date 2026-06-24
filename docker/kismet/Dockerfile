FROM debian:bookworm-slim AS build

ENV DEBIAN_FRONTEND=noninteractive
ARG KISMET_BUILD_JOBS=2
WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    git \
    libbluetooth-dev \
    libcap-dev \
    libmosquitto-dev \
    libnl-3-dev \
    libnl-genl-3-dev \
    libpcap-dev \
    libpcre2-dev \
    libprotobuf-dev \
    librtlsdr-dev \
    libsensors-dev \
    libsqlite3-dev \
    libssl-dev \
    libusb-1.0-0-dev \
    libwebsockets-dev \
    pkg-config \
    protobuf-compiler \
    python3 \
    unzip \
    zlib1g-dev \
  && rm -rf /var/lib/apt/lists/*

COPY vendor/kismet-master-bluetooth-rssi.zip /tmp/kismet-master-bluetooth-rssi.zip
RUN unzip -q /tmp/kismet-master-bluetooth-rssi.zip -d /tmp/kismet-src \
  && cd /tmp/kismet-src/kismet-master \
  && ./configure --prefix=/usr/local --with-suidgroup=root
RUN cd /tmp/kismet-src/kismet-master \
  && make -j"${KISMET_BUILD_JOBS}"
RUN cd /tmp/kismet-src/kismet-master \
  && make install

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    bluez \
    ca-certificates \
    dbus \
    iproute2 \
    libbluetooth3 \
    libcap2 \
    libmosquitto1 \
    libnl-3-200 \
    libnl-genl-3-200 \
    libpcap0.8 \
    libpcre2-8-0 \
    libprotobuf32 \
    librtlsdr0 \
    libsensors5 \
    libsqlite3-0 \
    libssl3 \
    libusb-1.0-0 \
    libwebsockets17 \
    procps \
    rfkill \
    rtl-sdr \
    zlib1g \
  && rm -rf /var/lib/apt/lists/*

COPY --from=build /usr/local /usr/local
COPY docker/kismet/start-kismet.sh /usr/local/bin/start-kismet.sh
RUN chmod +x /usr/local/bin/start-kismet.sh \
  && mkdir -p /etc/kismet /data/kismet /var/log/kismet

EXPOSE 2501
ENTRYPOINT ["/usr/local/bin/start-kismet.sh"]
