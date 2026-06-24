#!/bin/sh
set -eu

BETTERCAP_BLE_INTERFACE="${BETTERCAP_BLE_INTERFACE:-hci1}"
BETTERCAP_USERNAME="${BETTERCAP_USERNAME:-user}"
BETTERCAP_PASSWORD="${BETTERCAP_PASSWORD:-pass}"
BETTERCAP_REST_ADDRESS="${BETTERCAP_REST_ADDRESS:-0.0.0.0}"
BETTERCAP_REST_PORT="${BETTERCAP_REST_PORT:-8081}"
CAPLET_PATH=/etc/bettercap/passive-ble.cap

case "${BETTERCAP_BLE_INTERFACE}" in
    hci[0-9]*)
        BLE_DEVICE_INDEX="${BETTERCAP_BLE_INTERFACE#hci}"
        ;;
    *)
        echo "WARNING: BETTERCAP_BLE_INTERFACE='${BETTERCAP_BLE_INTERFACE}' is not in 'hciN' form; falling back to ble.device autodetect (-1)." >&2
        BLE_DEVICE_INDEX="-1"
        ;;
esac

# Passive-only caplet: exposes the REST API (consumed by the backend) and
# starts BLE discovery. Deliberately does not enable any spoofing,
# deauthentication, MITM or packet-injection module.
cat > "${CAPLET_PATH}" <<CAPLET
set api.rest.address ${BETTERCAP_REST_ADDRESS}
set api.rest.port ${BETTERCAP_REST_PORT}
set api.rest.username ${BETTERCAP_USERNAME}
set api.rest.password ${BETTERCAP_PASSWORD}
set ble.device ${BLE_DEVICE_INDEX}
api.rest on
ble.recon on
CAPLET

exec bettercap -no-colors -caplet "${CAPLET_PATH}"
