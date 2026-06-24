FROM timescale/timescaledb:2.17.2-pg16

ARG PGVECTOR_VERSION=v0.8.3

RUN set -eux; \
    apk add --no-cache --virtual .pgvector-build-deps \
        build-base \
        git \
        postgresql16-dev \
        clang \
        llvm \
        llvm-dev; \
    git clone \
        --depth 1 \
        --branch "${PGVECTOR_VERSION}" \
        https://github.com/pgvector/pgvector.git \
        /tmp/pgvector; \
    cd /tmp/pgvector; \
    make clean; \
    make OPTFLAGS=""; \
    make install; \
    cd /; \
    rm -rf /tmp/pgvector; \
    apk del .pgvector-build-deps

LABEL org.opencontainers.image.title="Diploma TimescaleDB with pgvector"
LABEL org.opencontainers.image.version="2.17.2-pg16-pgvector-0.8.3"
