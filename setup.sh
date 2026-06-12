#!/usr/bin/env bash
# ptloganalyzer — wrapper, actual logic in setup.pl (Perl)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec perl "$DIR/setup.pl" "$@"
