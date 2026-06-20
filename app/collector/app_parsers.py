# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
"""App-level parsers extract structured data from log messages.

Each parser receives the raw message text and returns:
    (app_id: str, fields: dict) or None if it doesn't match.

Parsers are defined in manifests/*.json.  Two types:
  - "builtin": references a parser function from this module
  - "kv":      generic key=value extractor, fully declarative
"""

import json
import re
from pathlib import Path

_MANIFEST_DIR = Path(__file__).resolve().parent.parent / "manifests"

# ── Generic key=value extractor ──
_KV_RE = re.compile(r'(\w[\w-]*)=(?:"([^"]*)"|(\S+))')


def _parse_keys(msg: str) -> dict:
    fields = {}
    for m in _KV_RE.finditer(msg):
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


def _make_kv_parser(app_id: str, match_fields: list[str], strip_prefix: str | None = None):
    """Create a parser from declarative config: require N fields, extract all KV pairs."""
    field_res = [re.compile(rf'\b{f}="?\w+"?\b') for f in match_fields]

    def parse(message: str) -> tuple[str, dict] | None:
        msg = message
        if strip_prefix:
            msg = msg.lstrip(strip_prefix).strip()
        for fre in field_res:
            if not fre.search(msg):
                return None
        fields = _parse_keys(msg)
        for f in match_fields:
            if f not in fields:
                return None
        return (app_id, fields)

    return parse


# ── zimbramon (Carbonio/Zimbra zmstat) ──
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


# ── postfix (Carbonio/Zimbra postfix mail logs) ──
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


# ── Builtin registry (referenced by "builtin" manifests) ──
_BUILTIN_PARSERS: dict[str, callable] = {
    "zimbramon": parse_zimbramon,
    "postfix": parse_postfix,
}


def _load_manifests() -> dict[str, callable]:
    parsers: dict[str, callable] = {}
    if not _MANIFEST_DIR.is_dir():
        return parsers
    for fpath in sorted(_MANIFEST_DIR.glob("*.json")):
        try:
            m = json.loads(fpath.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        app_id = m.get("app_id")
        if not app_id:
            continue
        pcfg = m.get("parser", {})
        ptype = pcfg.get("type", "")
        if ptype == "kv":
            parsers[app_id] = _make_kv_parser(
                app_id,
                pcfg["match_fields"],
                pcfg.get("strip_prefix"),
            )
        elif ptype == "builtin":
            name = pcfg.get("name", "")
            if name in _BUILTIN_PARSERS:
                parsers[app_id] = _BUILTIN_PARSERS[name]
    return parsers


# ── Public registry ──
APP_PARSERS: dict[str, callable] = _load_manifests()
