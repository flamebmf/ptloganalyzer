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

# ── fortigate (FortiOS structured key=value logs) ──
# Matches: "type=\"traffic\" subtype=\"forward\" ... logid=\"0000000013\" ..."
# Requires BOTH type= AND logid= to avoid false positives
_FORTI_RE = re.compile(r'\btype="?(\w+)"?\b')
_FORTI_LOGID_RE = re.compile(r'\blogid="?(\d+)"?')
_FORTI_KV_RE = re.compile(r'(\w[\w-]*)=(?:"([^"]*)"|(\S+))')


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


def _parse_keys(msg: str) -> dict:
    fields = {}
    for m in _FORTI_KV_RE.finditer(msg):
        key = m.group(1)
        val = m.group(2) if m.group(2) is not None else (m.group(3) or "")
        try:
            fields[key] = int(val)
        except (ValueError, TypeError):
            try:
                fields[key] = float(val) if "." in val else val
            except (ValueError, TypeError):
                fields[key] = val
    return fields


def parse_fortigate(message: str) -> tuple[str, dict] | None:
    msg = message.lstrip("- ").strip()
    if not _FORTI_RE.search(msg):
        return None
    if not _FORTI_LOGID_RE.search(msg):
        return None
    fields = _parse_keys(msg)
    if "type" not in fields:
        return None
    return ("fortigate", fields)


# ── postfix (Carbonio/Zimbra postfix mail logs) ──
# Matches:
#   postfix/postscreen[PID]: CONNECT from [IP]:PORT to [IP]:PORT
#   postfix/postscreen[PID]: ALLOWLISTED [IP]:PORT
#   postfix/postscreen[PID]: PASS OLD [IP]:PORT
#   postfix/smtpd[PID]: connect from HOST[IP]
#   postfix/smtpd[PID]: disconnect from HOST[IP] ehlo=N quit=N commands=N
#   postfix/smtpd[PID]: NOQUEUE: lost connection after CONNECT from HOST[IP]
_POSTFIX_RE = re.compile(
    r"postfix/(\w+)\[\d+\]:\s+(.*)"
)
_POSTFIX_CONNECT_RE = re.compile(
    r"CONNECT from \[([^\]]+)\]:(\d+)\s+to\s+\[([^\]]+)\]:(\d+)"
)
_POSTFIX_CLIENT_RE = re.compile(
    r"(?:connect|disconnect) from (\S+?)\[([^\]]+)\]"
)
_POSTFIX_DISCONNECT_KV = re.compile(r'(\w+)=(\d+)')
_POSTFIX_SINGLE_IP_RE = re.compile(
    r"(?:ALLOWLISTED|PASS OLD)\s+\[([^\]]+)\]:(\d+)"
)


def parse_postfix(message: str) -> tuple[str, dict] | None:
    m = _POSTFIX_RE.search(message)
    if not m:
        return None
    process = m.group(1)
    detail = m.group(2)
    fields = {"_process": process}

    cm = _POSTFIX_CONNECT_RE.search(detail)
    if cm:
        fields["event"] = "connect"
        fields["src_ip"] = cm.group(1)
        fields["src_port"] = int(cm.group(2))
        fields["dst_ip"] = cm.group(3)
        fields["dst_port"] = int(cm.group(4))
        return ("postfix", fields)

    sim = _POSTFIX_SINGLE_IP_RE.search(detail)
    if sim:
        fields["event"] = "allowlist" if "ALLOWLISTED" in detail else "pass_old"
        fields["peer_ip"] = sim.group(1)
        fields["peer_port"] = int(sim.group(2))
        return ("postfix", fields)

    clm = _POSTFIX_CLIENT_RE.search(detail)
    if clm:
        fields["host"] = clm.group(1)
        fields["peer_ip"] = clm.group(2)
        if "connect" in detail:
            fields["event"] = "smtp_connect"
        elif "disconnect" in detail:
            fields["event"] = "smtp_disconnect"
            for dkm in _POSTFIX_DISCONNECT_KV.finditer(detail):
                fields[dkm.group(1)] = int(dkm.group(2))
        return ("postfix", fields)

    if "NOQUEUE" in detail:
        fields["event"] = "noqueue"
        clm2 = _POSTFIX_CLIENT_RE.search(detail)
        if clm2:
            fields["host"] = clm2.group(1)
            fields["peer_ip"] = clm2.group(2)
        return ("postfix", fields)

    return None


# ── Registry ──
APP_PARSERS: dict[str, callable] = {
    "zimbramon": parse_zimbramon,
    "fortigate": parse_fortigate,
    "postfix": parse_postfix,
}
