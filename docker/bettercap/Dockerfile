FROM golang:1.24-alpine AS build

ENV DEBIAN_FRONTEND=noninteractive
ARG BETTERCAP_VERSION=v2.41.7
WORKDIR /src

RUN apk add --no-cache \
    bash \
    build-base \
    git \
    libpcap-dev \
    libusb-dev \
    linux-headers \
    libnetfilter_queue-dev

RUN git clone --branch "${BETTERCAP_VERSION}" --depth 1 https://github.com/bettercap/bettercap.git . \
  && make

FROM alpine:3.20

RUN apk add --no-cache \
    ca-certificates \
    curl \
    libpcap \
    libusb \
    libnetfilter_queue

COPY --from=build /src/bettercap /usr/local/bin/bettercap
COPY docker/bettercap/start-bettercap.sh /usr/local/bin/start-bettercap.sh
RUN chmod +x /usr/local/bin/start-bettercap.sh \
  && mkdir -p /etc/bettercap

EXPOSE 8081
ENTRYPOINT ["/usr/local/bin/start-bettercap.sh"]
