#!/usr/bin/env bash
# ptloganalyzer — очистка всех данных из БД
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

POD="${1:-ptlog-infra-postgres}"
DB="${2:-ptloganalyzer}"

echo "=== Очистка данных ptloganalyzer ==="
echo "Pod: $POD"
echo "DB:  $DB"
echo ""

read -rp "Удалить ВСЕ логи, аномалии, суммаризации и эмбеддинги? (yes/no): " confirm
if [[ "$confirm" != "yes" ]]; then
  echo "Отменено."
  exit 1
fi

echo ""
echo "Чистка таблиц..."
podman exec "$POD" psql -U ptlog -d "$DB" -c "
TRUNCATE
  syslog_messages,
  syslog_messages_default,
  anomalies,
  summaries,
  log_embeddings
CASCADE;
" 2>&1 || {
  echo "Ошибка: pod '$POD' не найден или команда не удалась"
  echo "Укажите имя pod'а: $0 <pod_name> [db_name]"
  echo ""
  podman ps --format 'table {{.Names}}' 2>/dev/null | grep -i infra || true
  exit 1
}

echo ""
echo "Готово. Все данные очищены."
