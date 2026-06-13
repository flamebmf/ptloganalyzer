// Copyright (c) 2026 PlurumTech.com
// SPDX-License-Identifier: LicenseRef-Personal-Use-Only
const LANG_RU = {
  dashboard: 'Панель управления',
  devices: 'Устройства',
  logs: 'Логи',
  anomalies: 'Аномалии',
  settings: 'Настройки',
  search: 'Поиск',
  filter: 'Фильтр',
  apply: 'Применить',
  cancel: 'Отмена',
  save: 'Сохранить',
  delete: 'Удалить',
  total_devices: 'Всего устройств',
  active_devices: 'Активны (1ч)',
  logs_per_hour: 'Логов за час',
  anomalies_24h: 'Аномалий за 24ч',
  last_seen: 'Последний раз',
  severity: 'Важность',
  message: 'Сообщение',
  app_name: 'Приложение',
  hostname: 'Хост',
  volume: 'Объём логов',
  distribution: 'Распределение',
  ai_summary: 'AI Сводка',
  no_data: 'Нет данных',
  loading: 'Загрузка...',
  error: 'Ошибка',
  success: 'Успешно',
  lang: 'Язык',
  ai_provider: 'AI провайдер',
  enable_ai: 'Включить AI',
  refresh: 'Обновить',
};

const LANG_EN = {
  dashboard: 'Dashboard',
  devices: 'Devices',
  logs: 'Logs',
  anomalies: 'Anomalies',
  settings: 'Settings',
  search: 'Search',
  filter: 'Filter',
  apply: 'Apply',
  cancel: 'Cancel',
  save: 'Save',
  delete: 'Delete',
  total_devices: 'Total Devices',
  active_devices: 'Active (1h)',
  logs_per_hour: 'Logs / Hour',
  anomalies_24h: 'Anomalies / 24h',
  last_seen: 'Last Seen',
  severity: 'Severity',
  message: 'Message',
  app_name: 'App',
  hostname: 'Host',
  volume: 'Log Volume',
  distribution: 'Distribution',
  ai_summary: 'AI Summary',
  no_data: 'No data',
  loading: 'Loading...',
  error: 'Error',
  success: 'Success',
  lang: 'Language',
  ai_provider: 'AI Provider',
  enable_ai: 'Enable AI',
  refresh: 'Refresh',
};

async function loadLanguage(lang) {
  const map = lang === 'ru' ? LANG_RU : LANG_EN;
  window.LANG = map;
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (map[key]) el.textContent = map[key];
  });
}
