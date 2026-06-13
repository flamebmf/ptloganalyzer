#!/usr/bin/env bash
# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
# ptloganalyzer — wrapper, actual logic in setup.pl (Perl)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec perl "$DIR/setup.pl" "$@"
