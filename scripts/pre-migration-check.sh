#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/lib.sh"
load_env

require_command docker
require_command tar
require_command sha256sum
require_command python3

section(){ printf '\n== %s ==\n' "$1"; }
check_dir(){
  local path=$1 label=$2
  if [[ -d "$path" ]]; then
    [[ -r "$path" && -w "$path" ]] && echo "$label: OK ($path)" || echo "$label: NINCS megfelelő jogosultság ($path)"
  else
    echo "$label: hiányzik, létrehozandó ($path)"
  fi
}

section "Operációs rendszer"
echo "OS: $(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-unknown}")"
echo "Kernel: $(uname -srmo)"
echo "Architektúra: $(uname -m)"

section "CPU és memória"
lscpu | awk -F: '/Model name|Architecture|CPU\(s\)|Thread|Core|Socket/{gsub(/^ +/,"",$2); printf "%s: %s\n",$1,$2}'
for flag in avx avx2; do grep -qw "$flag" /proc/cpuinfo && echo "$flag: igen" || echo "$flag: nem"; done
awk '/MemTotal/{printf "RAM: %.1f GiB\n",$2/1024/1024}' /proc/meminfo

section "Tárhely"
df -hT "$PROJECT_ROOT"
for path in "${POSTGRES_DATA_PATH:-postgres-data}" "${UPLOADS_DATA_PATH:-uploads-data}" "${RECORDINGS_ROOT:-$PROJECT_ROOT/recordings}" "${PROMETHEUS_DATA_PATH:-prometheus-data}"; do
  [[ "$path" = /* ]] && check_dir "$path" "Host könyvtár" || echo "Docker named volume vagy relatív út: $path"
done

section "Docker"
docker info >/dev/null
echo "Docker: $(docker version --format '{{.Server.Version}}')"
echo "Compose: $(docker compose version --short)"
compose config --quiet
echo "Compose parse: OK"

section "Portütközések"
for port in "${HTTP_PORT:-8080}"; do
  if command -v ss >/dev/null && ss -ltnH | awk '{print $4}' | grep -Eq "(^|:)$port$"; then
    echo "Port $port: FOGLALT"
  else
    echo "Port $port: szabad"
  fi
done

section "GPU / AI"
if command -v nvidia-smi >/dev/null; then
  nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
  docker info 2>/dev/null | grep -qi nvidia && echo "NVIDIA container runtime: látható" || echo "NVIDIA container runtime: ellenőrizendő"
else
  echo "NVIDIA GPU/driver: nincs vagy nem látható (AI/GPU profil opcionális)"
fi

section "RF függőségek"
command -v uhd_config_info >/dev/null && { echo "UHD: $(uhd_config_info --version 2>&1 | head -1)"; uhd_find_devices 2>/dev/null || true; } || echo "UHD: nincs telepítve"
if [[ -n "${AARONIA_SDK_ROOT:-}" ]]; then
  check_dir "$AARONIA_SDK_ROOT" "Aaronia SDK"
  find "$AARONIA_SDK_ROOT" -maxdepth 3 -type f \( -name '*.so*' -o -name '*.dll' -o -name '*.h' \) | head -20 || true
else
  echo "Aaronia SDK: AARONIA_SDK_ROOT nincs beállítva"
fi
if command -v sdrangelsrv >/dev/null; then sdrangelsrv --version 2>&1 | head -3 || true
elif command -v sdrangel >/dev/null; then sdrangel --version 2>&1 | head -3 || true
else echo "SDRangel: nincs telepítve"; fi

section "Hálózat és időszinkron"
ip -brief link 2>/dev/null || true
if command -v ethtool >/dev/null; then
  while read -r iface _; do
    [[ "$iface" == lo ]] && continue
    speed="$(ethtool "$iface" 2>/dev/null | awk -F: '/Speed:/{gsub(/^[ \t]+/,"",$2);print $2}')"
    [[ -n "$speed" ]] && echo "$iface sebesség: $speed"
  done < <(ip -brief link 2>/dev/null)
fi
if command -v timedatectl >/dev/null; then
  timedatectl show -p NTPSynchronized -p NTP -p Timezone 2>/dev/null || true
fi
command -v ptp4l >/dev/null && echo "PTP: ptp4l telepítve" || echo "PTP: nincs telepítve (csak többvevős precíz időhöz szükséges)"

section "Backup/restore ellenőrzés"
bash scripts/backup.sh
latest="$(find "${BACKUP_ROOT:-$PROJECT_ROOT/backups/runtime}" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort | tail -1 || true)"
if [[ -n "$latest" && -f "$latest/SHA256SUMS" ]]; then
  (cd "$latest" && sha256sum -c SHA256SUMS >/dev/null) && echo "Legutóbbi backup checksum: OK ($latest)"
  [[ -f "$latest/database/postgres.dump" ]] && pg_restore --list "$latest/database/postgres.dump" >/dev/null 2>&1 && echo "PostgreSQL dump katalógus: olvasható" || true
else
  echo "Ellenőrizhető alkalmazott backup még nincs."
fi

echo "Preflight kész. Éles migráció előtt futtasd: bash scripts/backup.sh --apply"
