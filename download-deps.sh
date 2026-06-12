#!/usr/bin/env bash
set -uo pipefail
# ptloganalyzer — предзагрузка Python-зависимостей на хосте
# Использование:  bash download-deps.sh
# Результат:      /srv/ptloganalyzer/wheelhouse/ — все .whl файлы

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WHEEL_DIR="${WHEEL_DIR:-/srv/ptloganalyzer/wheelhouse}"

if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
  echo "[ERR] Python не найден"
  exit 1
fi
PY=$(command -v python3 || command -v python)
echo "[INFO] Python: $($PY --version)"
echo "[INFO] Wheel dir: $WHEEL_DIR"

mkdir -p "$WHEEL_DIR"
$PY -m pip download --no-cache-dir -d "$WHEEL_DIR" -r "$SCRIPT_DIR/requirements.txt" 2>&1

echo ""
echo "[OK] Зависимости сохранены в $WHEEL_DIR"
echo "  Файлов: $(ls -1 "$WHEEL_DIR" | wc -l)"
echo ""
echo "  Затем соберите образ:"
echo "  PIP_NO_INDEX=true PIP_FIND_LINKS=$WHEEL_DIR ./setup.sh --rebuild"
