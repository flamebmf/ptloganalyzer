# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
"""App-level parsers extract structured data from log messages.

Each parser receives the raw message text and returns:
    (app_id: str, fields: dict) or None if it doesn't match.
"""

import re

# ── zimbramon (Carbonio/Zimbra zmstat) ──
# Matches: "zimbramon[PID]: PID:info: zmstat METRIC.csv: HEADERS:: VALUES"
_ZIMBRAMON_RE = re.compile(
    r"zimbramon\[\d+\]:\s+\d+:info:\s+"
    r"zmstat\s+(\S+)\.csv:\s+"
    r"(.*?)::\s*(.*)"
)


def parse_zimbramon(message: str) -> tuple[str, dict] | None:
    m = _ZIMBRAMON_RE.search(message)
    if not m:
        return None
    metric = m.group(1)
    headers = m.group(2)
    values = m.group(3)
    csv_headers = [h.strip() for h in headers.split(",")] if headers else []
    csv_values = [v.strip() for v in values.split(",")] if values else []
    fields = {}
    for i, h in enumerate(csv_headers):
        if i < len(csv_values):
            v = csv_values[i]
            try:
                fields[h] = float(v) if "." in v else int(v)
            except (ValueError, TypeError):
                fields[h] = v
        else:
            fields[h] = None
    fields["_metric"] = metric
    return ("zimbramon", fields)


# ── Registry ──
APP_PARSERS: dict[str, callable] = {
    "zimbramon": parse_zimbramon,
}
