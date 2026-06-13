#!/usr/bin/env perl
# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
use strict;
use warnings;
use File::Basename;
use Cwd 'abs_path';

sub yn { $_[0] // '' =~ /^(1|true|yes)$/i ? 'true' : 'false' }
sub intv { int($_[0] // $_[1]) }
sub esc {
  my $v = shift;
  return $v if $v =~ /^(true|false|\d+(?:\.\d+)?)$/;
  $v =~ s/"/\\"/g; return "\"$v\"";
}

sub yaml {
  my ($data, $indent) = @_;
  $indent //= 0;
  my $out = '';
  my $pad = ' ' x $indent;
  for my $k (sort keys %$data) {
    my $v = $data->{$k};
    if (ref $v eq 'HASH') {
      $out .= "${pad}${k}:\n" . yaml($v, $indent + 2);
    } elsif (ref $v eq 'ARRAY') {
      $out .= "${pad}${k}:\n";
      for my $item (@$v) {
        if (ref $item eq 'HASH') {
          my $first = 1;
          for my $ik (sort keys %$item) {
            $out .= $first ? "${pad}- ${ik}: " : "${pad}  ${ik}: ";
            $out .= esc($item->{$ik}) . "\n";
            $first = 0;
          }
        } else {
          $out .= "${pad}- " . esc($item) . "\n";
        }
      }
    } else {
      $out .= "${pad}${k}: " . esc($v) . "\n";
    }
  }
  return $out;
}

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
  provider => $ENV{AI_PROVIDER} // 'ollama',
  openai => {
    api_key        => '${OPENAI_API_KEY}',
    base_url       => $ENV{AI_OPENAI_URL}     // 'https://api.openai.com/v1',
    chat_model     => $ENV{AI_OPENAI_MODEL}   // 'gpt-4o-mini',
    embedding_model => $ENV{AI_OPENAI_EMBED}  // 'text-embedding-3-small',
    embedding_dims => 1536,
  },
  ollama => {
    base_url       => $ENV{AI_OLLAMA_URL}     // 'http://ollama.ptlog:11434',
    chat_model     => $ENV{AI_OLLAMA_MODEL}     // 'llama3.2:1b',
    embedding_model => $ENV{AI_OLLAMA_EMBED}  // 'nomic-embed-text',
    embedding_dims => 768,
  },
  routerai => {
    api_key        => '${ROUTERAI_API_KEY}',
    base_url       => $ENV{AI_ROUTERAI_URL}     // 'https://api.routerai.ai/v1',
    chat_model     => $ENV{AI_ROUTERAI_MODEL}   // 'deepseek/deepseek-v4-pro',
    embedding_model => $ENV{AI_ROUTERAI_EMBED}  // 'text-embedding-3-small',
    embedding_dims => 1536,
  },
  summarization => {
    interval_minutes   => 60,
    max_logs_per_batch => 1000,
  },
  anomaly_detection => {
    interval_minutes => 15,
    sensitivity      => 'medium',
  },
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

open my $fh, '>', $out or die "Cannot write $out: $!";
print $fh yaml(\%cfg);
close $fh;
print "config.yaml -> $out\n";
