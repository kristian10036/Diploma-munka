#!/bin/sh
set -eu

KISMET_SOURCE="${KISMET_SOURCE:-hci0}"
KISMET_SOURCE_NAME="${KISMET_SOURCE_NAME:-bluetooth0}"
KISMET_SOURCES="${KISMET_SOURCES:-}"
KISMET_HTTPD_USERNAME="${KISMET_HTTPD_USERNAME:-kismet}"
KISMET_HTTPD_PASSWORD="${KISMET_HTTPD_PASSWORD:-change_me}"
KISMET_LOG_PREFIX="${KISMET_LOG_PREFIX:-/data/kismet}"
KISMET_SERVER_NAME="${KISMET_SERVER_NAME:-Diploma Kismet Bluetooth RSSI}"

# The vendored /usr/local Kismet build loads site overrides from this path.
cat > /usr/local/etc/kismet_site.conf <<KISMETCONF
server_name=${KISMET_SERVER_NAME}
httpd_bind_address=0.0.0.0
httpd_port=2501
httpd_username=${KISMET_HTTPD_USERNAME}
httpd_password=${KISMET_HTTPD_PASSWORD}
log_prefix=${KISMET_LOG_PREFIX}
server_announce=false
remote_capture_enabled=false
KISMETCONF

if [ -n "${KISMET_SOURCES}" ]; then
    printf '%s\n' "${KISMET_SOURCES}" | tr ',' '\n' | while IFS= read -r source; do
        if [ -n "${source}" ]; then
            printf 'source=%s\n' "${source}" >> /usr/local/etc/kismet_site.conf
        fi
    done
else
    printf 'source=%s:name=%s\n' "${KISMET_SOURCE}" "${KISMET_SOURCE_NAME}" >> /usr/local/etc/kismet_site.conf
fi

exec kismet --no-ncurses --no-line-wrap
