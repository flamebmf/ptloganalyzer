#!/usr/bin/env perl
# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
use strict;
use warnings;
use v5.16;
use File::Basename;
use File::Copy;
use Cwd 'abs_path';

# Suppress Perl locale warnings (rare on container hosts)
$ENV{LC_ALL} = 'C';

# ──────────────────────────────────────────────
# Config & State
# ──────────────────────────────────────────────
my $SCRIPT_DIR = dirname(abs_path($0));
my $DATA_DIR   = '/srv/ptloganalyzer';
my $LOG_FILE   = '/tmp/ptlog-setup.log';

# Redirect stdout/stderr to log
open my $log_fh, '>>', $LOG_FILE or die "Cannot write $LOG_FILE: $!";
select((select(STDOUT), $|=1)[0]);
*STDERR = *STDOUT;

my $MODE        = '';
my $INSTALL_DIR = $DATA_DIR;
my $REBUILD     = 0;
my $PUSH        = 0;
my $PULL        = 0;
my $REGISTRY    = $ENV{DOCKER_REGISTRY} || 'docker.io/pltec/ptloganalyzer';

my %comp = map { $_ => 0 } qw(infra collector app ai web ollama);
my %db   = (host=>'', port=>5432, name=>'ptloganalyzer', user=>'ptlog', pass=>'', local=>1);
my %coll = (port=>514, bind=>'0.0.0.0', udp=>1, tcp=>1, batch_size=>500, batch_interval=>'1.0');
my %ai   = (enabled=>0, provider=>'ollama',
  openai_url=>'https://api.openai.com/v1', openai_key=>'', openai_model=>'gpt-4o-mini', openai_embed=>'text-embedding-3-small',
  ollama_url=>'http://ollama.ptlog:11434', ollama_model=>'llama3.2:1b', ollama_embed=>'nomic-embed-text',
  routerai_url=>'https://api.routerai.ai/v1', routerai_key=>'', routerai_model=>'deepseek/deepseek-v4-pro', routerai_embed=>'text-embedding-3-small');
my %web  = (api_port=>8000, web_port=>80, serve_static=>0);
my $LANG = 'ru';
my $DEVICES_CFG = '';

# ──────────────────────────────────────────────
# i18n — translations
# ──────────────────────────────────────────────
my %T = (
  ru => {
    lang_select => "Выберите язык установки / Choose language [ru/en]",
    lang_ok => "Язык установки: русский",
    existing_title => "Обнаружена конфигурация",
    existing_opt1 => "Пересобрать и развернуть заново",
    existing_opt1d => "(перегенерация pod'ов, пересборка образов, деплой)",
    existing_opt2 => "Удалить старый конфиг и настроить заново",
    existing_q => "Выход",
    existing_prompt => "Ваш выбор [1/2/q]",
    existing_invalid => "Неверный выбор. Введите 1, 2 или q",
    mode_title => "Выберите режим развёртывания",
    m1 => "Полный стек",
    m1d => "collector + app + AI + web + DB",
    m2 => "Сервер (без collector)",
    m2d => "app + AI + web + DB",
    m3 => "Только collector",
    m3d => "syslog-приёмник + внешняя БД",
    m4 => "Без AI",
    m4d => "collector + app + web + DB",
    m5 => "Без reverse proxy",
    m5d => "collector + app + AI + DB — статику раздаёт FastAPI",
    m6 => "Только БД",
    m6d => "Инициализация PostgreSQL + pgvector",
    m_q => "Выход",
    mode_prompt => "Ваш выбор [1-6/q]",
    mode_invalid => "Неверный выбор",
    mode_ok => "Режим",
    mode_step => "Компоненты",
    db_title => "База данных",
    db_coll_only => "Режим collector — только внешняя БД",
    db_local_q => "PostgreSQL локально (в pod'e) или внешний? [local/external]",
    db_local_ok => "PostgreSQL будет запущен в pod'е ptlog-infra (сеть ptlog)",
    db_data_dir => "Директория данных",
    db_host => "PostgreSQL host",
    db_port => "PostgreSQL port",
    db_name => "Database name",
    db_user => "Username",
    db_pass => "Password",
    db_repeat => "Repeat",
    db_mismatch => "Пароли не совпадают",
    coll_title => "Коллектор (syslog)",
    coll_port => "Порт",
    coll_bind => "Bind address",
    coll_udp => "Принимать UDP?",
    coll_tcp => "Принимать TCP?",
    coll_bsize => "Batch size (сообщений)",
    coll_bint => "Batch interval (секунд)",
    ai_title => "AI Engine",
    ai_choose => "Выберите AI провайдера",
    ai_o1 => "Ollama (локально)",
    ai_o2 => "OpenAI / Azure OpenAI",
    ai_o3 => "RouterAI (маршрутизация моделей)",
    ai_prompt => "Ваш выбор [1/2/3]",
    ai_ok => "Ollama API доступен",
    ai_fail => "Ollama не отвечает по адресу",
    ai_retry => "Попробовать другой URL? [Y/n]",
    ai_url => "URL",
    ai_key => "API key",
    ai_model => "Chat модель",
    ai_embed => "Embedding модель",
    ai_ollama_pod => "Запустить Ollama в pod'е?",
    web_title_proxy => "Web (nginx reverse proxy)",
    web_http => "HTTP порт",
    web_title_api => "API порт (статику раздаёт FastAPI)",
    web_api => "API порт",
    dev_title => "Устройства",
    dev_intro => "Укажите устройства, с которых будет приём логов.",
    dev_now => "Сейчас добавить?",
    dev_host => "Хостнейм устройства @1 (Enter — закончить)",
    dev_name => "Имя (опционально)",
    dev_ip => "IP (опционально)",
    dev_type => "Тип (router/switch/server/other)",
    sum_title => "Сводка конфигурации",
    sum_mode => "Режим",
    sum_dir => "Директория",
    sum_comp => "Компоненты",
    sum_collector => "Collector",
    sum_batch => "Batch",
    sum_api => "API порт",
    sum_ai => "AI провайдер",
    sum_web => "Web порт",
    sum_lang => "Язык AI отчётов",
    conf_prompt => "Всё верно? [Y/e/d/N] (Enter = да)",
    conf_no => "Отменено",
    conf_edit => "Редактирование вручную — измените переменные и запустите заново",
    conf_def => "Конфигурация сохранена, развёртывание отложено",
    conf_cfg => "Конфиги в",
    conf_pod => "Pod-файлы в",
    conf_run => "Запустите: podman play kube --network ptlog <файл>.kube",
    done_title => "Готово!",
    done_deployed => "ptloganalyzer развёрнут",
    done_cfg => "Конфиги",
    done_data => "Данные",
    done_web => "Web UI",
    done_api => "API",
    done_commands => "Команды",
    done_c1 => "podman pod list              # список подов",
    done_c2 => "podman logs -f ptlog-<pod>   # логи",
    done_c3 => "podman pod stop ptlog-<pod>  # остановка",
    done_c4 => "./setup.pl                   # повторный запуск",
    done_c5 => "./setup.pl --update=app      # обновить только app",
    done_c6 => "./setup.pl --update=all      # обновить всё",
    done_c7 => "./setup.pl --push            # собрать + опубликовать в @1",
    done_c8 => "./setup.pl --pull            # загрузить готовые образы из @1",
    done_c9 => "./setup.pl --rebuild         # принудительная пересборка base",
    done_log => "Полный лог",
  },
  en => {
    lang_select => "Choose installation language / Выберите язык установки [en/ru]",
    lang_ok => "Installation language: English",
    existing_title => "Existing configuration detected",
    existing_opt1 => "Rebuild and redeploy",
    existing_opt1d => "(regenerate pods, rebuild images, deploy)",
    existing_opt2 => "Delete old config and start fresh",
    existing_q => "Quit",
    existing_prompt => "Your choice [1/2/q]",
    existing_invalid => "Invalid choice. Enter 1, 2 or q",
    mode_title => "Select deployment mode",
    m1 => "Full stack",
    m1d => "collector + app + AI + web + DB",
    m2 => "Server (no collector)",
    m2d => "app + AI + web + DB",
    m3 => "Collector only",
    m3d => "syslog receiver + external DB",
    m4 => "No AI",
    m4d => "collector + app + web + DB",
    m5 => "No reverse proxy",
    m5d => "collector + app + AI + DB — FastAPI serves static",
    m6 => "DB only",
    m6d => "PostgreSQL + pgvector initialization",
    m_q => "Quit",
    mode_prompt => "Your choice [1-6/q]",
    mode_invalid => "Invalid choice",
    mode_ok => "Mode",
    mode_step => "Components",
    db_title => "Database",
    db_coll_only => "Collector mode — external DB only",
    db_local_q => "PostgreSQL local (in pod) or external? [local/external]",
    db_local_ok => "PostgreSQL will run in ptlog-infra pod (ptlog network)",
    db_data_dir => "Data directory",
    db_host => "PostgreSQL host",
    db_port => "PostgreSQL port",
    db_name => "Database name",
    db_user => "Username",
    db_pass => "Password",
    db_repeat => "Repeat",
    db_mismatch => "Passwords do not match",
    coll_title => "Collector (syslog)",
    coll_port => "Port",
    coll_bind => "Bind address",
    coll_udp => "Accept UDP?",
    coll_tcp => "Accept TCP?",
    coll_bsize => "Batch size (messages)",
    coll_bint => "Batch interval (seconds)",
    ai_title => "AI Engine",
    ai_choose => "Choose AI provider",
    ai_o1 => "Ollama (local)",
    ai_o2 => "OpenAI / Azure OpenAI",
    ai_o3 => "RouterAI (model routing)",
    ai_prompt => "Your choice [1/2/3]",
    ai_ok => "Ollama API is available",
    ai_fail => "Ollama not responding at",
    ai_retry => "Try different URL? [Y/n]",
    ai_url => "URL",
    ai_key => "API key",
    ai_model => "Chat model",
    ai_embed => "Embedding model",
    ai_ollama_pod => "Run Ollama in a pod?",
    web_title_proxy => "Web (nginx reverse proxy)",
    web_http => "HTTP port",
    web_title_api => "API port (FastAPI serves static)",
    web_api => "API port",
    dev_title => "Devices",
    dev_intro => "Specify devices that will send logs.",
    dev_now => "Add now?",
    dev_host => "Device @1 hostname (Enter to finish)",
    dev_name => "Name (optional)",
    dev_ip => "IP (optional)",
    dev_type => "Type (router/switch/server/other)",
    sum_title => "Configuration summary",
    sum_mode => "Mode",
    sum_dir => "Directory",
    sum_comp => "Components",
    sum_collector => "Collector",
    sum_batch => "Batch",
    sum_api => "API port",
    sum_ai => "AI provider",
    sum_web => "Web port",
    sum_lang => "AI report language",
    conf_prompt => "Is everything correct? [Y/e/d/N] (Enter = yes)",
    conf_no => "Cancelled",
    conf_edit => "Manual editing — modify variables and re-run",
    conf_def => "Configuration saved, deployment deferred",
    conf_cfg => "Configs in",
    conf_pod => "Pod files in",
    conf_run => "Run: podman play kube --network ptlog <file>.kube",
    done_title => "Done!",
    done_deployed => "ptloganalyzer deployed",
    done_cfg => "Configs",
    done_data => "Data",
    done_web => "Web UI",
    done_api => "API",
    done_commands => "Commands",
    done_c1 => "podman pod list              # list pods",
    done_c2 => "podman logs -f ptlog-<pod>   # view logs",
    done_c3 => "podman pod stop ptlog-<pod>  # stop pod",
    done_c4 => "./setup.pl                   # re-run setup",
    done_c5 => "./setup.pl --update=app      # update app only",
    done_c6 => "./setup.pl --update=all      # update all",
    done_c7 => "./setup.pl --push            # build + publish to @1",
    done_c8 => "./setup.pl --pull            # pull pre-built images from @1",
    done_c9 => "./setup.pl --rebuild         # force base rebuild",
    done_log => "Full log",
  },
);

sub t {
  my ($key, @args) = @_;
  my $s = $T{$LANG}{$key} // $T{ru}{$key} // $key;
  if (@args) {
    my $i = 1;
    $s =~ s/\@$i/$args[$i-1]/g && $i++ for 1..@args;
  }
  return $s;
}


# Colors
my ($R,$G,$Y,$C,$B,$N) = map {"\e[" . $_ . "m"} qw(0;31 0;32 1;33 0;36 1 0);

# Forward declarations
sub info; sub ok; sub warn_msg; sub err; sub title; sub step;

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
sub info  { say "${C}[INFO]${N}  @_" }
sub ok    { say "${G}[OK]${N}    @_" }
sub warn_msg { say "${Y}[WARN]${N}  @_" }
sub err   { say "${R}[ERR]${N}   @_" }
sub title { say "\n${C}══════════════════════════════════════════════════${N}";
            say "${C}  @_${N}";
            say "${C}══════════════════════════════════════════════════${N}\n" }
sub step  { say "\n${B}── @_${N}" }

sub prompt {
  my ($msg, $default) = @_;
  my $display;
  if (defined $default && length $default) {
    $display = "$msg [$default]: ";
  } else {
    $display = "$msg: ";
  }
  print "  $display";
  my $ans = <STDIN> // '';
  chomp $ans;
  return length($ans) ? $ans : ($default // '');
}

sub prompt_yn {
  my ($msg, $default) = @_;
  $default //= 'y';
  my $label = $default eq 'y' ? 'Y/n' : 'y/N';
  my $ans = prompt("$msg [$label]: ", $default);
  return $ans =~ /^(y|yes|д|да)$/i ? 1 : 0;
}

sub bool_val {
  my $v = shift // '';
  return $v =~ /^(1|true|yes)$/i ? 'true' : 'false';
}

sub run_cmd {
  my ($desc, @cmd) = @_;
  info $desc;
  system(@cmd) == 0 or do {
    warn_msg "Команда завершилась с кодом $?: @cmd";
    return 0;
  };
  return 1;
}

sub capture {
  my @cmd = @_;
  my $out = `@cmd 2>/dev/null` // '';
  chomp $out;
  return wantarray ? split("\n", $out) : $out;
}

# ──────────────────────────────────────────────
# Prerequisites
# ──────────────────────────────────────────────
sub check_prereqs {
  title "Проверка зависимостей";

  my $podman_ver = capture('podman --version');
  if ($podman_ver) {
    ok "podman: $podman_ver";
  } else {
    err "podman не найден. Установите: dnf install -y podman"; exit 1;
  }

  for my $cmd (qw(curl sed openssl)) {
    my $path = capture("which $cmd 2>/dev/null || command -v $cmd");
    $path ? ok("$cmd: $path") : (err("$cmd не найден"), exit 1);
  }

  if ($> != 0) {
    warn_msg "Запуск не от root. Podman на RHEL/Fedora с SELinux может блокировать bind-mount.";
    warn_msg "Рекомендуется: sudo ./setup.pl";
  }

  if (capture('command -v selinuxenabled 2>/dev/null') && capture('selinuxenabled && echo 1')) {
    info "SELinux включён. Проверяю контекст директорий...";
    if (-d "$INSTALL_DIR/config") {
      my $ctx = capture("stat -c %C $INSTALL_DIR/config 2>/dev/null");
      $ctx =~ s/.*://; $ctx =~ s/:.*//; chomp $ctx;
      if ($ctx ne 'container_file_t' && $ctx ne 'svirt_sandbox_file_t') {
        warn_msg "Контекст SELinux: $ctx. Исправляю...";
        for my $d (qw(config web initdb data)) {
          next unless -d "$INSTALL_DIR/$d";
          system("chcon -Rt container_file_t $INSTALL_DIR/$d 2>/dev/null");
          system("chcon -Rt svirt_sandbox_file_t $INSTALL_DIR/$d 2>/dev/null");
        }
        ok "SELinux контекст исправлен";
      } else { ok "SELinux контекст: $ctx" }
    }
  }

  my $net = capture('podman network exists ptlog 2>/dev/null && echo 1');
  $net ? ok("Сеть ptlog уже существует") : info("Сеть ptlog будет создана при деплое");
}

# ──────────────────────────────────────────────
# Read existing config from deploy.yaml
# ──────────────────────────────────────────────
sub read_deploy_yaml {
  my $cfg = "$INSTALL_DIR/config/deploy.yaml";
  return 0 unless -f $cfg;

  open my $fh, '<', $cfg or return 0;
  my $section = '';
  while (<$fh>) {
    chomp;
    if (/^(\w+):/) { $section = $1; next }
    if ($section eq 'ports' && /^\s+(\w+):\s+(\S+)/) {
      if ($1 eq 'collector') { $coll{port} = $2 }
      elsif ($1 eq 'api')    { $web{api_port} = $2 }
      elsif ($1 eq 'web')    { $web{web_port} = $2 }
    }
    elsif ($section eq 'components' && /^\s+(\w+):\s+(\S+)/) {
      $comp{$1} = ($2 eq 'true') ? 1 : 0;
    }
    elsif ($section eq 'ai' && /^\s+(\w+):\s+(\S+)/) {
      if ($1 eq 'provider')    { $ai{provider} = $2 }
      elsif ($1 eq 'ollama_url') { $ai{ollama_url} = $2 }
      elsif ($1 eq 'openai_url') { $ai{openai_url} = $2 }
      elsif ($1 eq 'routerai_url') { $ai{routerai_url} = $2 }
    }
    elsif ($section eq '' && /^mode:\s+(\S+)/) { $MODE = $1 }
    elsif ($section eq '' && /^data_dir:\s+(\S+)/) { $INSTALL_DIR = $1 }
  }
  close $fh;

  # Read config.yaml values if valid
  my $old_cfg = "$INSTALL_DIR/config/config.yaml";
  if (-f $old_cfg) {
    open my $fh2, '<', $old_cfg or return 1;
    local $/ = undef;
    my $content = <$fh2>;
    close $fh2;
    if ($content =~ /^app:/m) {
      # Strip YAML quotes from captured values
      my $uq = sub { my $v = shift; $v =~ s/^"//; $v =~ s/"$//; $v };
      # First, extract database section port
      if ($content =~ /^database:\s*\n(?:.*\n)*?\s+port:\s+(\S+)/m) { $db{port} = $uq->($1) }
      if ($content =~ /^\s+host:\s+(\S+)/m)      { $db{host} = $uq->($1) }
      if ($content =~ /^\s+user:\s+(\S+)/m)       { $db{user} = $uq->($1) }
      if ($content =~ /^\s+name:\s+(\S+)/m)       { $db{name} = $uq->($1) }
      if ($content =~ /^\s+provider:\s+(\S+)/m)   { $ai{provider} = $uq->($1) }
      if ($content =~ /^collector:\s*\n(?:.*\n)*?\s+port:\s+(\S+)/m) { $coll{port} = $uq->($1) }
      if ($content =~ /^ai:\s*\n(?:.*\n)*?ollama:\s*\n(?:.*\n)*?\s+base_url:\s+(\S+)/m) { $ai{ollama_url} = $uq->($1) }
      if ($content =~ /^ai:\s*\n(?:.*\n)*?\s+enabled:\s+(\S+)/m) { $ai{enabled} = $1 eq 'true' ? 1 : 0 }
      if ($content =~ /^ai:\s*\n(?:.*\n)*?openai:\s*\n(?:.*\n)*?\s+base_url:\s+(\S+)/m) { $ai{openai_url} = $uq->($1) }
      if ($content =~ /^ai:\s*\n(?:.*\n)*?openai:\s*\n(?:.*\n)*?\s+api_key:\s+(\S+)/m) { $ai{openai_key} = $uq->($1) }
      if ($content =~ /^ai:\s*\n(?:.*\n)*?routerai:\s*\n(?:.*\n)*?\s+base_url:\s+(\S+)/m) { $ai{routerai_url} = $uq->($1) }
      if ($content =~ /^ai:\s*\n(?:.*\n)*?routerai:\s*\n(?:.*\n)*?\s+api_key:\s+(\S+)/m) { $ai{routerai_key} = $uq->($1) }
    } else { warn_msg "config.yaml повреждён, используем значения по умолчанию" }
  }

  # DB_HOST default
  $db{host} ||= 'localhost';
  if ($comp{infra} && $db{host} eq 'localhost') { $db{host} = 'ptlog-infra' }
  $db{port}  ||= 5432;
  $db{name}  ||= 'ptloganalyzer';
  $db{user}  ||= 'ptlog';
  $coll{port}  ||= 514;
  $web{api_port} ||= 8000;
  $web{web_port} ||= 8080;
  $web{serve_static} = $comp{web} ? 0 : 1;

  # Secrets from .env
  my $env_file = "$INSTALL_DIR/config/.env";
  if (-f $env_file) {
    open my $efh, '<', $env_file or return 1;
    while (<$efh>) {
      chomp;
      $db{pass} = $1 if /^DB_PASSWORD=(.+)/;
      $ai{openai_key} = $1 if /^OPENAI_API_KEY=(.+)/;
      $ai{routerai_key} = $1 if /^ROUTERAI_API_KEY=(.+)/;
    }
    close $efh;
  }

  info "Режим: $MODE, пересборка с существующими настройками";
  return 1;
}

# ──────────────────────────────────────────────
# Detect existing config
# ──────────────────────────────────────────────
sub detect_existing {
  my $cfg = "$INSTALL_DIR/config/deploy.yaml";
  return 0 unless -f $cfg;

  title t('existing_title');
  say "  $cfg\n";
  say "  ${B}1)${N} " . t('existing_opt1');
  say "     " . t('existing_opt1d') . "\n";
  say "  ${B}2)${N} " . t('existing_opt2') . "\n";
  say "  ${B}q)${N} " . t('existing_q') . "\n";

  while (1) {
    my $ans = prompt(t('existing_prompt'), '1');
    if ($ans eq '1') { read_deploy_yaml(); return 1 }
    elsif ($ans eq '2') { unlink $cfg; return 0 }
    elsif ($ans =~ /^q/i) { exit 0 }
    else { warn_msg t('existing_invalid') }
  }
}

# ──────────────────────────────────────────────
# Mode selection
# ──────────────────────────────────────────────
sub select_mode {
  title t('mode_title');

  say "  ${B}1)${N} " . t('m1');
  say "     " . t('m1d') . "\n";
  say "  ${B}2)${N} " . t('m2');
  say "     " . t('m2d') . "\n";
  say "  ${B}3)${N} " . t('m3');
  say "     " . t('m3d') . "\n";
  say "  ${B}4)${N} " . t('m4');
  say "     " . t('m4d') . "\n";
  say "  ${B}5)${N} " . t('m5');
  say "     " . t('m5d') . "\n";
  say "  ${B}6)${N} " . t('m6');
  say "     " . t('m6d') . "\n";
  say "  ${B}q)${N} " . t('m_q') . "\n";

  while (1) {
    my $ans = prompt(t('mode_prompt'), '1');
    %comp = map { $_ => 0 } qw(infra collector app ai web ollama);
    if ($ans eq '1') { $MODE='full-stack'; $comp{infra}=$comp{collector}=$comp{app}=$comp{ai}=$comp{web}=1; last }
    elsif ($ans eq '2') { $MODE='server'; $comp{infra}=$comp{app}=$comp{ai}=$comp{web}=1; last }
    elsif ($ans eq '3') { $MODE='collector'; $comp{collector}=1; last }
    elsif ($ans eq '4') { $MODE='no-ai'; $comp{infra}=$comp{collector}=$comp{app}=$comp{web}=1; last }
    elsif ($ans eq '5') { $MODE='no-proxy'; $comp{infra}=$comp{collector}=$comp{app}=$comp{ai}=1; $web{serve_static}=1; last }
    elsif ($ans eq '6') { $MODE='db-only'; $comp{infra}=1; last }
    elsif ($ans =~ /^q/i) { say t('m_q'); exit 0 }
    else { warn_msg t('mode_invalid') }
  }
  ok t('mode_ok') . ": $MODE";
  step t('mode_step') . ": infra=$comp{infra} collector=$comp{collector} app=$comp{app} ai=$comp{ai} web=$comp{web}";
}

# ──────────────────────────────────────────────
# Database questions
# ──────────────────────────────────────────────
sub ask_database {
  title t('db_title');

  $db{local} = 1;
  if ($MODE eq 'collector') {
    $db{local} = 0;
    info t('db_coll_only');
  }
  elsif ($comp{infra} && $MODE ne 'collector') {
    my $ans = prompt(t('db_local_q'), 'local');
    $db{local} = 0 if $ans =~ /^e/i;
  }

  if ($db{local}) {
    $db{host} = 'ptlog-infra';
    info t('db_local_ok');
    my $ans = prompt(t('db_data_dir'), $INSTALL_DIR);
    $INSTALL_DIR = $ans if length $ans;
  } else {
    $db{host} = prompt(t('db_host'), '');
    $db{port} = prompt(t('db_port'), 5432);
    $db{name} = prompt(t('db_name'), 'ptloganalyzer');
    $db{user} = prompt(t('db_user'), 'ptlog');
    while (1) {
      print "  " . t('db_pass') . ": "; system('stty -echo'); chomp(my $p1 = <STDIN>); system('stty echo'); say '';
      print "  " . t('db_repeat') . ":   "; system('stty -echo'); chomp(my $p2 = <STDIN>); system('stty echo'); say '';
      if ($p1 eq $p2) { $db{pass} = $p1; last }
      warn_msg t('db_mismatch');
    }
  }

  if ($db{local} && !$db{pass}) {
    $db{pass} = capture('openssl rand -base64 18 | tr -dc a-zA-Z0-9');
  }
}

# ──────────────────────────────────────────────
# Collector questions
# ──────────────────────────────────────────────
sub ask_collector {
  title t('coll_title');
  $coll{port} = prompt(t('coll_port'), 514);
  $coll{bind} = prompt(t('coll_bind'), '0.0.0.0');
  $coll{udp} = prompt_yn(t('coll_udp'), 'y') ? 1 : 0;
  $coll{tcp} = prompt_yn(t('coll_tcp'), 'y') ? 1 : 0;
  $coll{batch_size} = prompt(t('coll_bsize'), 500);
  $coll{batch_interval} = prompt(t('coll_bint'), '1.0');
}

# ──────────────────────────────────────────────
# AI questions
# ──────────────────────────────────────────────
sub ask_ai {
  title t('ai_title');
  say "  " . t('ai_choose') . ":";
  say "    1) " . t('ai_o1');
  say "    2) " . t('ai_o2');
  say "    3) " . t('ai_o3') . "\n";
  my $ans = prompt(t('ai_prompt'), '1');
  if ($ans eq '2') {
    $ai{provider} = 'openai';
    $ai{openai_key} = prompt(t('ai_key') . ": ", '');
    $ai{openai_url} = prompt(t('ai_url'), $ai{openai_url});
    $ai{openai_model} = prompt(t('ai_model'), $ai{openai_model});
    $ai{openai_embed} = prompt(t('ai_embed'), $ai{openai_embed});
    $comp{ollama} = 0;
  } elsif ($ans eq '3') {
    $ai{provider} = 'routerai';
    $ai{routerai_key} = prompt(t('ai_key') . ": ", '');
    $ai{routerai_url} = prompt(t('ai_url'), $ai{routerai_url});
    $ai{routerai_model} = prompt(t('ai_model'), $ai{routerai_model});
    $ai{routerai_embed} = prompt(t('ai_embed'), $ai{routerai_embed});
    $comp{ollama} = 0;
  } else {
    $ai{provider} = 'ollama';
    while (1) {
      $ai{ollama_url} = prompt(t('ai_url'), $ai{ollama_url});
      $ai{ollama_url} =~ s|/+$||;
      last if $ai{ollama_url} !~ /^http/;
      my $check_url = "$ai{ollama_url}/api/tags";
      my $ok = system("curl -sf --max-time 5 '$check_url' >/dev/null 2>&1") == 0;
      if ($ok) { info t('ai_ok'); last }
      warn_msg t('ai_fail') . " $check_url";
      my $retry = prompt(t('ai_retry'), 'y');
      last if $retry =~ /^n/i;
    }
    $ai{ollama_model} = prompt(t('ai_model'), $ai{ollama_model});
    $ai{ollama_embed} = prompt(t('ai_embed'), $ai{ollama_embed});
    $comp{ollama} = prompt_yn(t('ai_ollama_pod'), 'n') ? 1 : 0;
  }
}

# ──────────────────────────────────────────────
# Web questions
# ──────────────────────────────────────────────
sub ask_web {
  if ($comp{web}) {
    title t('web_title_proxy');
    $web{web_port} = prompt(t('web_http'), 80);
  }
  if ($web{serve_static}) {
    title t('web_title_api');
    $web{api_port} = prompt(t('web_api'), 8000);
  }
  if ($comp{app} && !$comp{web} && !$web{serve_static}) {
    $web{api_port} = prompt(t('web_api'), 8000);
  }
}

# ──────────────────────────────────────────────
# Devices
# ──────────────────────────────────────────────
sub ask_devices {
  title t('dev_title');
  say "  " . t('dev_intro');
  my $ans = prompt_yn(t('dev_now'), 'n');
  return unless $ans;

  $DEVICES_CFG = '';
  my $i = 1;
  while (1) {
    say '';
    my $hostname = prompt(t('dev_host', $i), '');
    last unless length $hostname;
    my $name = prompt(t('dev_name') . ": ", '');
    my $ip   = prompt(t('dev_ip') . ": ", '');
    my $dtype = prompt(t('dev_type'), 'other');
    $DEVICES_CFG .= "  - hostname: $hostname\n";
    $DEVICES_CFG .= "    name: $name\n" if length $name;
    $DEVICES_CFG .= "    ip: $ip\n" if length $ip;
    $DEVICES_CFG .= "    device_type: $dtype\n";
    $i++;
  }
}

# ──────────────────────────────────────────────
# Generate configs (deploy.yaml, .env, config.yaml)
# ──────────────────────────────────────────────
sub generate_configs {
  title "Генерация конфигурации";

  my $cfg_dir = "$INSTALL_DIR/config";
  for my $d ($cfg_dir, "$INSTALL_DIR/data/pgdata", "$INSTALL_DIR/web", "$INSTALL_DIR/ollama") {
    mkdir $d unless -d $d;
  }

  # SELinux
  if (capture('command -v selinuxenabled 2>/dev/null') && capture('selinuxenabled && echo 1')) {
    info "SELinux: обновляю контекст...";
    for my $d (qw(config initdb data web)) {
      next unless -d "$INSTALL_DIR/$d";
      system("chcon -Rt container_file_t $INSTALL_DIR/$d 2>/dev/null");
      system("chcon -Rt svirt_sandbox_file_t $INSTALL_DIR/$d 2>/dev/null");
    }
  }

  # ── deploy.yaml ──
  open my $dfh, '>', "$cfg_dir/deploy.yaml" or die "Cannot write deploy.yaml: $!";
  printf $dfh "# ptloganalyzer — deploy configuration\n";
  printf $dfh "# Generated by setup.pl %s\n", scalar localtime;
  printf $dfh "mode: %s\n", $MODE;
  printf $dfh "data_dir: %s\n", $INSTALL_DIR;
  printf $dfh "ports:\n  collector: %s\n  api: %s\n  web: %s\n", $coll{port}, $web{api_port}, $web{web_port};
  printf $dfh "components:\n";
  for my $c (qw(infra collector app ai web ollama)) {
    printf $dfh "  %s: %s\n", $c, bool_val($comp{$c});
  }
  printf $dfh "ai:\n  provider: %s\n", $ai{provider};
  printf $dfh "  ollama_url: %s\n", $ai{ollama_url};
  if ($ai{provider} eq 'openai') {
    printf $dfh "  openai_url: %s\n", $ai{openai_url};
  }
  if ($ai{provider} eq 'routerai') {
    printf $dfh "  routerai_url: %s\n", $ai{routerai_url};
  }
  close $dfh;
  ok "deploy.yaml создан";

  # ── .env ──
  # Only generate fresh password on initial setup; during updates keep existing
  my $env_path = "$cfg_dir/.env";
  my $is_update = -f $env_path;
  my $existing_pass = '';
  if ($is_update) {
    open my $ef, '<', $env_path;
    while (<$ef>) { $existing_pass = $1 if /^DB_PASSWORD=(.+)/ }
    close $ef;
    $db{pass} = $existing_pass if $existing_pass;
  }
  open my $efh, '>', $env_path or die "Cannot write .env: $!";
  printf $efh "# ptloganalyzer — secrets\nDB_PASSWORD=%s\n", $db{pass};
  if ($ai{provider} eq 'openai' && $ai{openai_key}) {
    printf $efh "OPENAI_API_KEY=%s\n", $ai{openai_key};
  }
  if ($ai{provider} eq 'routerai' && $ai{routerai_key}) {
    printf $efh "ROUTERAI_API_KEY=%s\n", $ai{routerai_key};
  }
  close $efh;
  ok ".env создан";

  # ── config.yaml via Perl generator ──
  # Export env vars for generate_config.pl
  my $version = do { open my $vf, '<', "$SCRIPT_DIR/VERSION"; my $v = <$vf>; chomp $v; close $vf; $v // '0.0.0' };
  $ENV{APP_VERSION}         = $version;
  $ENV{INSTALL_DIR}         = $INSTALL_DIR;
  $ENV{DB_HOST}             = $db{host};
  $ENV{DB_PORT}             = $db{port};
  $ENV{DB_NAME}             = $db{name};
  $ENV{DB_USER}             = $db{user};
  $ENV{COMP_COLLECTOR}      = bool_val($comp{collector});
  $ENV{COLLECTOR_UDP}       = bool_val($coll{udp});
  $ENV{COLLECTOR_TCP}       = bool_val($coll{tcp});
  $ENV{COLLECTOR_PORT}      = $coll{port};
  $ENV{COLLECTOR_BIND}      = $coll{bind};
  $ENV{COLLECTOR_BATCH_SIZE} = $coll{batch_size};
  $ENV{COLLECTOR_BATCH_INTERVAL} = $coll{batch_interval};
  $ENV{COMP_AI}             = bool_val($comp{ai});
  $ENV{AI_PROVIDER}         = $ai{provider};
  $ENV{AI_OPENAI_URL}       = $ai{openai_url};
  $ENV{AI_OPENAI_MODEL}     = $ai{openai_model};
  $ENV{AI_OPENAI_EMBED}     = $ai{openai_embed};
  $ENV{AI_OLLAMA_URL}       = $ai{ollama_url};
  $ENV{AI_OLLAMA_MODEL}     = $ai{ollama_model};
  $ENV{AI_OLLAMA_EMBED}     = $ai{ollama_embed};
  $ENV{AI_ROUTERAI_URL}     = $ai{routerai_url};
  $ENV{AI_ROUTERAI_MODEL}   = $ai{routerai_model};
  $ENV{AI_ROUTERAI_EMBED}   = $ai{routerai_embed};
  $ENV{COMP_WEB}            = bool_val($comp{web});
  $ENV{WEB_SERVE_STATIC}    = bool_val($web{serve_static});
  $ENV{API_PORT}            = $web{api_port};
  $ENV{WEB_PORT}            = $web{web_port};
  $ENV{LANG}                = $LANG;
  $ENV{AI_LANGUAGE}         = $LANG;

  my $gen_cmd = "perl $SCRIPT_DIR/app/generate_config.pl $cfg_dir/config.yaml";
  my $rc = system($gen_cmd);
  if ($rc == 0) {
    ok "config.yaml создан";
  } else {
    err "generate_config.pl вернул код $rc";
    exit 1;
  }

  # Fix permissions
  chmod 0755, grep {-d} "$INSTALL_DIR", "$INSTALL_DIR/data", "$INSTALL_DIR/initdb", "$INSTALL_DIR/web", $cfg_dir;
  for my $f (grep {-f && !/\.env$/} glob("$cfg_dir/*")) { chmod 0644, $f }
  my $env_file = "$cfg_dir/.env";
  chmod 0640, $env_file if -f $env_file;
  ok "права на config/ поправлены (755+644)";
}

# ──────────────────────────────────────────────
# Generate pod kube files with var substitution
# ──────────────────────────────────────────────
sub generate_pods {
  title "Генерация pod-файлов";

  my $pod_dir = "$INSTALL_DIR/pod";
  mkdir $pod_dir unless -d $pod_dir;
  my $src_pod_dir = "$SCRIPT_DIR/pod";

  my %subst = (
    '__DATA_DIR__'       => $INSTALL_DIR,
    '__COLLECTOR_PORT__' => $coll{port},
    '__API_PORT__'       => $web{api_port},
    '__WEB_PORT__'       => $web{web_port},
    '__APP_HOST__'       => 'app.ptlog',
    '__APP_PORT__'       => '8000',
  );

  for my $tmpl (qw(infra collector app ai web ollama)) {
    my $src = "$src_pod_dir/$tmpl.kube";
    next unless -f $src;
    next unless $comp{$tmpl};

    open my $sfh, '<', $src or do { warn_msg "Ошибка чтения $src"; next };
    local $/ = undef;
    my $content = <$sfh>;
    close $sfh;

    $content =~ s/$_/$subst{$_}/g for keys %subst;

    open my $dfh, '>', "$pod_dir/$tmpl.kube" or   do { warn_msg "Ошибка записи $pod_dir/$tmpl.kube"; next };
    print $dfh $content;
    close $dfh;
    ok "pod/$tmpl.kube сгенерирован";
  }

  # nginx config
  if ($comp{web} && -f "$src_pod_dir/web-nginx.conf") {
    open my $sfh, '<', "$src_pod_dir/web-nginx.conf" or return;
    local $/ = undef;
    my $content = <$sfh>;
    close $sfh;
    $content =~ s/__APP_HOST__/app.ptlog/g;
    $content =~ s/__APP_PORT__/8000/g;
    open my $dfh, '>', "$INSTALL_DIR/config/web-nginx.conf" or return;
    print $dfh $content;
    close $dfh;
    ok "nginx config сгенерирован";
  }
}

# ──────────────────────────────────────────────
# Copy web static
# ──────────────────────────────────────────────
sub copy_web {
  return unless -d "$SCRIPT_DIR/web";
  step "Копирование web-статики";
  system("cp -r $SCRIPT_DIR/web/* $INSTALL_DIR/web/ 2>/dev/null");

  my $version = $ENV{APP_VERSION};
  if (!$version) {
    my $vf = "$SCRIPT_DIR/VERSION";
    if (-f $vf) { open my $fh, '<', $vf; $version = <$fh>; chomp $version; close $fh }
    $version //= '0.0.0';
  }

  for my $html (glob("$INSTALL_DIR/web/*.html")) {
    next unless -f $html;
    open my $fh, '<', $html or next;
    local $/ = undef;
    my $content = <$fh>;
    close $fh;
    next unless $content =~ /__APP_VERSION__/;
    $content =~ s/__APP_VERSION__/$version/g;
    open my $ofh, '>', $html or next;
    print $ofh $content;
    close $ofh;
  }

  ok "web-статика скопирована в $INSTALL_DIR/web/";
}

# ──────────────────────────────────────────────
# Copy DB schema
# ──────────────────────────────────────────────
sub copy_schema {
  return unless -f "$SCRIPT_DIR/app/db/schema.sql";
  step "Копирование схемы БД";
  mkdir "$INSTALL_DIR/initdb" unless -d "$INSTALL_DIR/initdb";
  copy("$SCRIPT_DIR/app/db/schema.sql", "$INSTALL_DIR/initdb/000_schema.sql");
  copy("$SCRIPT_DIR/app/db/001_superuser.sql", "$INSTALL_DIR/initdb/001_superuser.sql") if -f "$SCRIPT_DIR/app/db/001_superuser.sql";
  copy("$SCRIPT_DIR/app/db/003_create_admin.sql", "$INSTALL_DIR/initdb/003_create_admin.sql") if -f "$SCRIPT_DIR/app/db/003_create_admin.sql";

  # 002_set_password.sql — прямой ALTER USER
  open my $pfh, '>', "$INSTALL_DIR/initdb/002_set_password.sql" or warn_msg "Cannot write 002: $!";
  printf $pfh "ALTER USER ptlog WITH PASSWORD '%s';\n", $db{pass};
  close $pfh;

  chmod 0755, "$INSTALL_DIR/initdb" if -d "$INSTALL_DIR/initdb";
  chmod 0644, glob("$INSTALL_DIR/initdb/*.sql");
  ok "Схема и init-скрипты скопированы в initdb/";
}

# ──────────────────────────────────────────────
# Build Docker images
# ──────────────────────────────────────────────
sub build_image {
  title "Сборка Docker-образов";

  return if !$comp{collector} && !$comp{app} && !$comp{ai};

  my $dockerfile = "$SCRIPT_DIR/Dockerfile";
  unless (-f $dockerfile) { err "Dockerfile не найден"; exit 1 }

  my $version = do { open my $vf, '<', "$SCRIPT_DIR/VERSION"; my $v = <$vf>; chomp $v; close $vf; $v // '0.0.0' };
  my $build_date = scalar gmtime;
  $build_date =~ s/ /-/g;
  my $git_commit = capture("cd $SCRIPT_DIR && git rev-parse --short HEAD 2>/dev/null") || 'unknown';

  my @build_args = (
    "--build-arg=VERSION=$version", "--build-arg=BUILD_DATE=$build_date",
    "--build-arg=COMMIT=$git_commit",
    "--build-arg=PIP_INDEX_URL=" . ($ENV{PIP_INDEX_URL} // 'https://pypi.org/simple/'),
    "--build-arg=PIP_NO_INDEX=" . ($ENV{PIP_NO_INDEX} // 'false'),
  );
  push @build_args, "--build-arg=PIP_TRUSTED_HOST=$ENV{PIP_TRUSTED_HOST}" if $ENV{PIP_TRUSTED_HOST};
  push @build_args, "--build-arg=PIP_FIND_LINKS=$ENV{PIP_FIND_LINKS}" if $ENV{PIP_FIND_LINKS};

  info "Версия: $version, build: $build_date";
  my $net = $ENV{PIP_NETWORK} // 'host';

  # ── Base image ──
  if ($REBUILD) {
    info "Принудительная пересборка base...";
    system("podman rmi ptlog-base:latest 2>/dev/null");
    system("podman rmi ptlog-base:$version 2>/dev/null");
  }

  my $base_exists = capture("podman image exists ptlog-base:$version 2>/dev/null && echo 1");
  if ($base_exists) {
    ok "Base-образ ptlog-base:$version уже есть, используем";
  } else {
    info "Сборка base-образа (зависимости, 1 раз)...";
    my $rc = system('podman', 'build', '--network', $net, @build_args,
      '-t', "ptlog-base:$version", '-t', 'ptlog-base:latest',
      '--target', 'base', '-f', $dockerfile, $SCRIPT_DIR);
    if ($rc != 0) {
      err "Сборка base-образа провалилась. Проверьте доступность pypi.org или укажите PIP_INDEX_URL=<mirror>";
      exit 1;
    }
    ok "Base-образ собран: ptlog-base:$version";
  }

  # ── App image ──
  my $app_checksum = capture("cd $SCRIPT_DIR && find app/ Dockerfile requirements.txt VERSION web/ -type f -not -path '*__pycache__*' -exec md5sum {} \\; 2>/dev/null | md5sum | cut -d' ' -f1");
  my $checksum_file = "$INSTALL_DIR/config/build-checksum";
  my $old_checksum = '';
  if (-f $checksum_file) { open my $cf, '<', $checksum_file; $old_checksum = <$cf>; chomp $old_checksum; close $cf }

  my $server_exists = capture("podman image exists ptlog-server:latest 2>/dev/null && echo 1");
  if ($REBUILD || $app_checksum ne $old_checksum || !$server_exists) {
    info "Сборка app-образа (изменения обнаружены)...";
    my $rc = system('podman', 'build', '--network', $net, @build_args,
      '-t', "ptlog-server:$version", '-t', 'ptlog-server:latest',
      '--target', 'app', '-f', $dockerfile, $SCRIPT_DIR);
    if ($rc != 0) { err "Сборка app-образа провалилась"; exit 1 }
    open my $cf, '>', $checksum_file; print $cf $app_checksum; close $cf;
    ok "Образ ptlog-server:$version собран";
  } else {
    ok "App-образ ptlog-server:latest уже актуален, сборка пропущена";
  }

  # version.json
  my $ver_dir = "$INSTALL_DIR/config";
  mkdir $ver_dir unless -d $ver_dir;
  open my $vjh, '>', "$ver_dir/version.json" or return;
  printf $vjh qq|{"version":"%s","build_date":"%s","commit":"%s","vendor":"Plurumtech.com","components":{"base_image":"ptlog-base:%s","app_image":"ptlog-server:%s"}}\n|,
    $version, $build_date, $git_commit, $version, $version;
  close $vjh;
  ok "Версия записана: $ver_dir/version.json";

  # Push to registry if --push
  if ($PUSH) {
    push_images($version);
  }
}

# ──────────────────────────────────────────────
# Push images to registry
# ──────────────────────────────────────────────
sub push_images {
  my ($version) = @_;
  title "Публикация образов в $REGISTRY";

  # Warn about secrets in image layers
  my $pip_url = $ENV{PIP_INDEX_URL} // '';
  if ($pip_url =~ /@/) {
    warn_msg "ВНИМАНИЕ: PIP_INDEX_URL содержит credentials ($pip_url) — они попадут в слой образа!";
    my $ans = prompt("Продолжить публикацию? [y/N]: ", 'n');
    return unless $ans =~ /^[yY]/;
  }

  for my $img (qw(ptlog-base ptlog-server)) {
    for my $tag ($version, 'latest') {
      my $remote = "$REGISTRY:$tag-$img";
      info "Тегирование $img:$tag -> $remote";
      system('podman', 'tag', "$img:$tag", $remote);
      info "Push $remote ...";
      my $rc = system('podman', 'push', $remote);
      if ($rc != 0) {
        err "Push $remote провалился. Проверьте podman login.";
        next;
      }
      ok "$remote опубликован";
    }
  }
}

# ──────────────────────────────────────────────
# Pull pre-built images from registry
# ──────────────────────────────────────────────
sub pull_images {
  my ($version) = @_;
  unless ($version) {
    $version = do { open my $vf, '<', "$SCRIPT_DIR/VERSION"; my $v = <$vf>; chomp $v; close $vf; $v // '0.0.0' };
  }
  title "Загрузка образов из $REGISTRY";

  for my $img (qw(ptlog-base ptlog-server)) {
    my $tag = "$REGISTRY:$version-$img";
    info "Pull $tag ...";
    my $rc = system('podman', 'pull', $tag);
    if ($rc != 0) {
      err "Pull $tag провалился. Проверьте доступность registry.";
      next;
    }
    system('podman', 'tag', $tag, "$img:$version");
    system('podman', 'tag', $tag, "$img:latest");
    ok "$img:$version загружен и тегирован";
  }
}

# ──────────────────────────────────────────────
# Deploy pods
# ──────────────────────────────────────────────
sub play_kube {
  my $kube = shift;
  my $pw = $db{pass} // '';
  my $key = $ai{openai_key} // '';
  my $rkey = $ai{routerai_key} // '';
  my $cmd = "cat '$kube'";
  $cmd = "sed 's/__DB_PASSWORD__/$pw/g' '$kube'" if $pw;
  $cmd .= " | sed 's/__OPENAI_API_KEY__/$key/g'" if $key;
  $cmd .= " | sed 's/__ROUTERAI_API_KEY__/$rkey/g'" if $rkey;
  $cmd .= " | podman play kube --network ptlog -";
  system("$cmd 2>/dev/null");
}

sub ensure_ollama_models {
  return if $ai{provider} ne 'ollama';
  my $url   = $ai{ollama_url};
  my $chat  = $ai{ollama_model};
  my $embed = $ai{ollama_embed};
  info "Проверка моделей Ollama...";
  for my $model ($chat, $embed) {
    next unless $model;
    my $check_url = "$url/api/tags";
    my $tags = capture("curl -sf --max-time 5 '$check_url' 2>/dev/null");
    next unless $tags;
    if ($tags =~ /\Q$model\E/) {
      ok "Модель $model уже загружена";
      next;
    }
    info "Загрузка модели $model (может занять время)...";
    system("curl -sf -X POST '$url/api/pull' -d '{\"name\":\"$model\"}' --max-time 600 >/dev/null 2>&1");
    if ($? == 0) { ok "Модель $model загружена" }
    else         { warn_msg "Не удалось загрузить модель $model" }
  }
}

sub deploy {
  title "Развёртывание";

  my $pod_dir = "$INSTALL_DIR/pod";

  # Network
  unless (capture("podman network exists ptlog 2>/dev/null && echo 1")) {
    info "Создание сети ptlog...";
    system("podman network create ptlog 2>/dev/null");
    ok "Сеть ptlog создана";
  }

  for my $comp (qw(infra collector app ai web ollama)) {
    next unless $comp{$comp};
    my $kube = "$pod_dir/$comp.kube";
    next unless -f $kube;

    my $pod_name = "ptlog-$comp";
    if (capture("podman pod exists $pod_name 2>/dev/null && echo 1")) {
      my $ans = prompt("Pod $pod_name уже существует. Пересоздать? [y/N]: ", 'n');
      if ($ans =~ /^(y|yes|д|да)$/i) {
        system("podman pod stop $pod_name 2>/dev/null");
        system("podman pod rm $pod_name 2>/dev/null");
        play_kube($kube);
        ok "$comp развёрнут";
      } else {
        ok "$comp пропущен (существующий)";
        next;
      }
    } else {
      play_kube($kube);
      ok "$comp развёрнут";
    }

    # Password sync after infra deploy
    if ($comp eq 'infra') {
      my $pg = 'ptlog-infra-postgres';
      info "Ожидание готовности PostgreSQL...";
      for (1..30) {
        last if capture("podman exec $pg pg_isready -q 2>/dev/null && echo 1");
        sleep 1;
      }

      # peer → trust
      system(qq(podman exec $pg sh -c "sed -i '/^local\\s\\+all\\s\\+all\\s\\+/s/[^ ]*$/trust/' /var/lib/postgresql/data/pg_hba.conf") . ' 2>/dev/null');
      system("podman exec $pg kill -HUP 1 2>/dev/null");
      sleep 1;

      # Find psql
      my $psql = capture("podman exec $pg find /usr -name psql -type f 2>/dev/null | head -1");
      if (!$psql) {
        warn_msg "psql не найден в контейнере $pg";
      } elsif (system("podman exec $pg $psql -U ptlog -d ptloganalyzer -c \"ALTER USER ptlog WITH PASSWORD '$db{pass}';\" >/dev/null 2>&1") == 0) {
        ok "Пароль ptlog синхронизирован";
      } else {
        warn_msg "Не удалось синхронизировать пароль ptlog";
      }
    }
  }

  # Pull Ollama models
  ensure_ollama_models if $comp{ai};

  say '';
  info "Проверка статуса:";
  my $list = capture("podman pod list 2>/dev/null | grep ptlog");
  if ($list) {
    say($_) for split("\n", $list);
  } else {
    info "Нет активных pod'ов ptlog";
  }
}

# ──────────────────────────────────────────────
# Show summary
# ──────────────────────────────────────────────
sub show_summary {
  title t('sum_title');
  say "  " . t('sum_mode') . ":       $MODE";
  say "  " . t('sum_dir') . ":        $INSTALL_DIR\n";
  say "  " . t('sum_comp') . ":";
  say "    infra (БД):      " . bool_val($comp{infra});
  say "    collector:       " . bool_val($comp{collector});
  say "    app:             " . bool_val($comp{app});
  say "    ai:              " . bool_val($comp{ai});
  say "    web:             " . bool_val($comp{web});
  say "    ollama:          " . bool_val($comp{ollama});
  say '';
  if ($comp{collector}) {
    say "  " . t('sum_collector') . ":   $coll{bind}:$coll{port} (UDP:" . bool_val($coll{udp}) . " TCP:" . bool_val($coll{tcp}) . ")";
    say "  " . t('sum_batch') . ":       $coll{batch_size}msgs / $coll{batch_interval}s";
  }
  say "  " . t('sum_api') . ":     $web{api_port}" if $comp{app};
  say "  " . t('sum_ai') . ":     $ai{provider}" if $comp{ai};
  say "  " . t('sum_web') . ":     $web{web_port}" if $comp{web};
  say "  " . t('sum_lang') . ": $LANG";
  say '';
}

# ──────────────────────────────────────────────
# Update single component
# ──────────────────────────────────────────────
sub update_component {
  my $target = shift;
  title "Обновление компонента: $target";

  # Read existing config
  read_deploy_yaml() or do { err "Нет deploy.yaml в $INSTALL_DIR/config/"; exit 1 };

  if ($target eq 'all') {
    generate_configs;
    generate_pods;
    copy_web;
    copy_schema;
    build_image;
    deploy;
    return;
  }

  unless ($comp{$target}) {
    err "Компонент '$target' не включён в конфигурации (не был развёрнут)";
    exit 1;
  }

  # Regenerate configs (reads fresh VERSION)
  generate_configs;

  # Copy files that may have changed
  copy_web if $target eq 'web' || $target eq 'app' || $target eq 'ai';
  copy_schema if $target eq 'infra';

  # Rebuild image if needed
  if ($target =~ /^(app|collector|ai)$/) {
    # Temporarily enable only the needed component for build_image
    my %saved = %comp;
    %comp = map { $_ => $_ eq $target ? 1 : 0 } keys %comp;
    build_image;
    %comp = %saved;
  }

  # Regenerate pod file
  generate_pods;

  # Redeploy single pod
  my $pod_name = "ptlog-$target";
  my $kube = "$INSTALL_DIR/pod/$target.kube";
  unless (-f $kube) { err "Pod-файл не найден: $kube"; exit 1 }

  step "Пересоздание pod'а $pod_name";
  system("podman pod stop $pod_name 2>/dev/null");
  system("podman pod rm $pod_name 2>/dev/null");
  play_kube($kube);
  ok "$target обновлён";

  ensure_ollama_models if $target eq 'ai';

  # Re-deploy app pod after AI update (config changed, app needs restart)
  if ($target eq 'ai' && $comp{app}) {
    my $app_kube = "$INSTALL_DIR/pod/app.kube";
    if (-f $app_kube) {
      step "Перезапуск app pod (изменения AI конфига)";
      system("podman pod stop ptlog-app 2>/dev/null");
      system("podman pod rm ptlog-app 2>/dev/null");
      play_kube($app_kube);
      ok "app перезапущен";
    }
  }

  # Password sync after infra update
  if ($target eq 'infra') {
    my $pg = 'ptlog-infra-postgres';
    info "Ожидание готовности PostgreSQL...";
    for (1..30) {
      last if capture("podman exec $pg pg_isready -q 2>/dev/null && echo 1");
      sleep 1;
    }
    system(qq(podman exec $pg sh -c "sed -i '/^local\\s\\+all\\s\\+all\\s\\+/s/[^ ]*$/trust/' /var/lib/postgresql/data/pg_hba.conf") . ' 2>/dev/null');
    system("podman exec $pg kill -HUP 1 2>/dev/null");
    sleep 1;
    my $psql = capture("podman exec $pg find /usr -name psql -type f 2>/dev/null | head -1");
    if ($psql) {
      system("podman exec $pg $psql -U ptlog -d ptloganalyzer -c \"ALTER USER ptlog WITH PASSWORD '$db{pass}';\" >/dev/null 2>&1");
    }
  }

  # Re-deploy dependent pods after infra update
  if ($target eq 'infra') {
    for my $dep (qw(collector app ai web)) {
      next unless $comp{$dep};
      my $dep_kube = "$INSTALL_DIR/pod/$dep.kube";
      next unless -f $dep_kube;
      step "Перезапуск зависимого $dep...";
      system("podman pod stop ptlog-$dep 2>/dev/null");
      system("podman pod rm ptlog-$dep 2>/dev/null");
      play_kube($dep_kube);
      ok "$dep перезапущен";
    }
  }
}

# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
sub main {
  title "ptloganalyzer Setup v0.3 (Perl)  © Plurumtech.com";
  say "  Log analysis system with AI summarization";
  say "  " . t('done_log') . ": $LOG_FILE\n";

  # Language selection
  my $lang_ans = lc prompt(t('lang_select'), 'ru');
  $LANG = ($lang_ans eq 'en') ? 'en' : 'ru';
  info t('lang_ok');

  $REBUILD = (grep { $_ eq '--rebuild' } @ARGV) ? 1 : 0;
  info "Флаг --rebuild: принудительная пересборка base-образа" if $REBUILD;

  $PUSH = (grep { $_ eq '--push' } @ARGV) ? 1 : 0;
  info "Флаг --push: публикация образов в registry ($REGISTRY)" if $PUSH;

  $PULL = (grep { $_ eq '--pull' } @ARGV) ? 1 : 0;
  if ($PULL) {
    info "Флаг --pull: загрузка готовых образов из $REGISTRY";
    step "Проверка зависимостей";
    check_prereqs;
    pull_images;
    title "Готово!";
    exit 0;
  }

  # Parse --update=<comp> (comma-separated or single)
  my ($update_raw) = map { /^--update=(.+)/ ? $1 : () } @ARGV;
  if ($update_raw) {
    my @update_targets = split /[,+]\s*/, lc $update_raw;
    my @valid = qw(infra collector app ai web ollama all);
    for my $t (@update_targets) {
      unless (grep { $_ eq $t } @valid) {
        err "Неверный компонент: $t. Допустимые: " . join(', ', @valid);
        exit 1;
      }
    }
    step "Проверка зависимостей";
    check_prereqs;
    for my $t (@update_targets) {
      update_component($t);
      info "Компонент $t обновлён";
    }
    title "Готово!";
    exit 0;
  }

  step "Проверка зависимостей";
  check_prereqs;

  if (detect_existing()) {
    # Mode 1: rebuild with existing settings
    read_deploy_yaml();
    step "Пересборка pod-файлов и образов";
    generate_configs;
    generate_pods;
    copy_web;
    copy_schema;
    build_image;
    deploy;
  } else {
    # Mode 2 or no config: fresh setup
    step "Выбор режима";
    select_mode;

    step "Настройка БД";
    ask_database;

    step "Настройка коллектора" if $comp{collector};
    ask_collector if $comp{collector};

    step "Настройка AI" if $comp{ai};
    ask_ai if $comp{ai};

    step "Настройка Web/API";
    ask_web;

    step "Настройка устройств" if $comp{collector} || $comp{app};

    show_summary;

    my $ans = prompt(t('conf_prompt'), 'y');
    if ($ans =~ /^[nN]/) { info t('conf_no'); exit 0 }
    elsif ($ans =~ /^[eE]/) { warn_msg t('conf_edit'); exit 0 }
    elsif ($ans =~ /^[dD]/) {
      info t('conf_def');
      generate_configs;
      generate_pods;
      copy_web;
      copy_schema;
      info t('conf_cfg') . ": $INSTALL_DIR/config/";
      info t('conf_pod') . ": $INSTALL_DIR/pod/";
      info t('conf_run');
      exit 0;
    } else {
      generate_configs;
      generate_pods;
      copy_web;
      copy_schema;
      build_image;
      deploy;
    }
  }

  title t('done_title');
  say "$G┌─────────────────────────────────────────────────────┐${N}";
  say "$G│${N}  " . t('done_deployed');
  say "$G│${N}  " . t('done_cfg') . ": $INSTALL_DIR/config/";
  say "$G│${N}  " . t('done_data') . ":  $INSTALL_DIR/data/";
  say "$G│${N}  " . t('done_web') . ":  http://localhost:$web{web_port}" if $comp{web};
  say "$G│${N}  " . t('done_api') . ":     http://localhost:$web{api_port}" if $comp{app} && !$comp{web};
  say "$G│${N}";
  say "$G│${N}  " . t('done_commands') . ":";
  say "$G│${N}    " . t('done_c1');
  say "$G│${N}    " . t('done_c2');
  say "$G│${N}    " . t('done_c3');
  say "$G│${N}    " . t('done_c4');
  say "$G│${N}    " . t('done_c5');
  say "$G│${N}    " . t('done_c6');
  say "$G│${N}    " . t('done_c7', $REGISTRY);
  say "$G│${N}    " . t('done_c8', $REGISTRY);
  say "$G│${N}    " . t('done_c9');
  say "$G└─────────────────────────────────────────────────────┘${N}";
  say '';
  info t('done_log') . ": $LOG_FILE";
}

main(@ARGV);
