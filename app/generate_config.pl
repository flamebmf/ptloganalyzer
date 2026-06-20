#!/usr/bin/env perl
# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
use strict;
use warnings;
use File::Basename;
use Cwd 'abs_path';
use YAML::XS qw(DumpFile);

sub yn { !!($_[0] // '' =~ /^(1|true|yes)$/i) }
sub intv { int($_[0] // $_[1]) }

my %cfg;

my $version = $ENV{APP_VERSION};
if (!$version) {
  my $vf = do {
    local $/ = undef;
    open my $fh, '<', File::Basename::dirname(File::Basename::dirname(Cwd::abs_path($0))) . '/VERSION' or return undef;
    <$fh>;
  };
  chomp $vf if $vf;
  $version = $vf // '0.0.0';
}

$cfg{app} = {
  name     => 'ptloganalyzer',
  version  => $version,
  data_dir => $ENV{INSTALL_DIR}  // '/srv/ptloganalyzer',
  log_level => 'info',
};

$cfg{database} = {
  host     => $ENV{DB_HOST}   // 'localhost',
  port     => intv($ENV{DB_PORT}, 5432),
  name     => $ENV{DB_NAME}   // 'ptloganalyzer',
  user     => $ENV{DB_USER}   // 'ptlog',
  password => '${DB_PASSWORD}',
  pool_min => 5,
  pool_max => 20,
};

$cfg{collector} = {
  enabled        => yn($ENV{COMP_COLLECTOR}),
  udp            => yn($ENV{COLLECTOR_UDP} // 'true'),
  tcp            => yn($ENV{COLLECTOR_TCP} // 'true'),
  port           => intv($ENV{COLLECTOR_PORT}, 514),
  bind           => $ENV{COLLECTOR_BIND}  // '0.0.0.0',
  recv_buffer    => 65536,
  batch_size     => intv($ENV{COLLECTOR_BATCH_SIZE}, 500),
  batch_interval => $ENV{COLLECTOR_BATCH_INTERVAL} // 1.0,
};

$cfg{ai} = {
  enabled  => yn($ENV{COMP_AI}),
  provider => $ENV{AI_PROVIDER} // 'routerai',
  openai => {
    api_key        => '${OPENAI_API_KEY}',
    base_url       => $ENV{AI_OPENAI_URL}     // 'https://api.openai.com/v1',
    chat_model     => $ENV{AI_OPENAI_MODEL}   // 'gpt-4o-mini',
    embedding_model => $ENV{AI_OPENAI_EMBED}  // 'text-embedding-3-small',
    embedding_dims => 1536,
    timeout        => $ENV{AI_OPENAI_TIMEOUT}  // 180,
  },
  ollama => {
    base_url       => $ENV{AI_OLLAMA_URL}     // 'http://localhost:11434',
    chat_model     => $ENV{AI_OLLAMA_MODEL}     // 'llama3.2:1b',
    embedding_model => $ENV{AI_OLLAMA_EMBED}  // 'nomic-embed-text',
    embedding_dims => 768,
    timeout        => $ENV{AI_OLLAMA_TIMEOUT}  // 600,
  },
  routerai => {
    api_key        => '${ROUTERAI_API_KEY}',
    base_url       => $ENV{AI_ROUTERAI_URL}     // 'https://api.routerai.ai/v1',
    chat_model     => $ENV{AI_ROUTERAI_MODEL}   // 'deepseek/deepseek-v4-pro',
    embedding_model => $ENV{AI_ROUTERAI_EMBED}  // 'text-embedding-3-small',
    embedding_dims => 1536,
    timeout        => $ENV{AI_ROUTERAI_TIMEOUT}  // 180,
  },
  providers => {
    ollama => {
        name => 'Ollama',
        models => {
            'llama3.2:1b' => 'Llama 3.2 1B',
            'llama3.2:3b' => 'Llama 3.2 3B',
            'qwen2.5:7b' => 'Qwen 2.5 7B',
            'qwen3:4b' => 'Qwen 3 4B',
            'deepseek-r1:1.5b' => 'DeepSeek R1 1.5B',
            'nomic-embed-text' => 'Nomic Embed Text',
        },
    },
    openai => {
        name => 'OpenAI',
        models => {
            'gpt-4o-mini' => 'GPT-4o Mini',
            'gpt-4o' => 'GPT-4o',
            'text-embedding-3-small' => 'Text Embedding 3 Small',
        },
    },
    routerai => {
        name => 'RouterAI',
        api_key_env => 'ROUTERAI_API_KEY',
        models => {
            'qwen/qwen3.5-9b' => 'Qwen 3.5 9B',
            'deepseek/deepseek-v4-pro' => 'DeepSeek V4 Pro',
            'openai/text-embedding-3-small' => 'Text Embedding 3 Small',
        },
    },
  },
  summarization => {
    interval_minutes   => 60,
    max_logs_per_batch => 1000,
    provider           => $ENV{AI_SUMMARIZATION_PROVIDER} // 'routerai',
    model              => $ENV{AI_SUMMARIZATION_MODEL}    // 'qwen/qwen3.5-9b',
  },
  anomaly_detection => {
    interval_minutes => 15,
    sensitivity      => 'medium',
    min_severity     => 'info',
    provider         => $ENV{AI_ANOMALY_PROVIDER} // 'routerai',
    model            => $ENV{AI_ANOMALY_MODEL}    // 'qwen/qwen3.5-9b',
  },
  embeddings => {
    provider => $ENV{AI_EMBEDDINGS_PROVIDER} // 'routerai',
    model    => $ENV{AI_EMBEDDINGS_MODEL}    // 'openai/text-embedding-3-small',
  },
  language => $ENV{AI_LANGUAGE} // 'ru',
};

$cfg{web} = {
  enabled      => yn($ENV{COMP_WEB}),
  serve_static => yn($ENV{WEB_SERVE_STATIC}),
  api_port     => intv($ENV{API_PORT}, 8000),
  web_port     => intv($ENV{WEB_PORT}, 80),
  language     => $ENV{LANG} // 'ru',
};

$cfg{devices} = [];

my $out = shift || die "Usage: $0 <output.yaml>\n";

DumpFile($out, \%cfg);
print "config.yaml -> $out\n";
