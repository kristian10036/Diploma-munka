FROM debian:bookworm-slim AS build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    cmake \
    libboost-system-dev \
    libssl-dev \
    libsoapysdr-dev \
    libuhd-dev \
    libzstd-dev \
    nlohmann-json3-dev \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY rf-agent/ ./
RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTING=ON -DENABLE_USRP=ON \
  && cmake --build build --parallel 2

FROM build AS test
RUN ctest --test-dir build --output-on-failure

FROM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    libboost-system1.74.0 \
    libdbus-1-3 \
    libfontconfig1 \
    libgl1 \
    libegl1 \
    libglib2.0-0 \
    libpulse0 \
    libopengl0 \
    libpipewire-0.3-0 \
    libsndfile1 \
    libssl3 \
    libudev1 \
    libusb-1.0-0 \
    hackrf \
    soapysdr-module-hackrf \
    soapysdr-module-uhd \
    soapysdr-tools \
    uhd-host \
    libx11-6 \
    libxkbcommon0 \
    zlib1g \
    libzstd1 \
  && rm -rf /var/lib/apt/lists/*

COPY --from=build /src/build/rf-agent /usr/local/bin/rf-agent
COPY --from=build /src/build/aaronia-probe /usr/local/bin/aaronia-probe
COPY --from=build /src/build/aaronia-worker /usr/local/bin/aaronia-worker
COPY --from=build /src/build/usrp-probe /usr/local/bin/usrp-probe
RUN useradd --system --uid 10001 --create-home rfagent \
  && mkdir -p /recordings \
  && chown rfagent:rfagent /recordings

USER rfagent
EXPOSE 8765
ENTRYPOINT ["/usr/local/bin/rf-agent"]
