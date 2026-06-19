# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
import re
import socket
from datetime import datetime, timezone


# RFC 5424: <PRI>VERSION TIMESTAMP HOSTNAME APPNAME PROCID MSGID STRUCTURED-DATA MSG
RFC5424_RE = re.compile(
    r"<(\d{1,3})>(\d)\s"                      # PRI + VERSION
    r"(\S+)\s"                                # TIMESTAMP
    r"(\S+)\s"                                # HOSTNAME
    r"(\S+)\s"                                # APPNAME
    r"(\S*)\s?"                               # PROCID
    r"(\S*)\s?"                               # MSGID
    r"(?:\[.*?\]\s)?"                         # STRUCTURED-DATA (optional)
    r"(.*)"                                   # MSG
)

# RFC 3164 (BSD): <PRI>TIMESTAMP HOSTNAME MSG
RFC3164_RE = re.compile(
    r"<(\d{1,3})>"                            # PRI
    r"(\S{3}\s+\d{1,2}\s\d{2}:\d{2}:\d{2})\s"  # TIMESTAMP (e.g. "Jan  1 12:34:56")
    r"(\S+)\s"                                # HOSTNAME
    r"(.*)"                                    # MSG
)

# PRI-only: <PRI>MSG — no timestamp, no hostname (e.g. embedded devices)
PRI_ONLY_RE = re.compile(r"<(\d{1,3})>(.*)")


def parse_priority(pri: int) -> tuple[int, int]:
    facility = pri // 8
    severity = pri % 8
    return facility, severity


def parse_timestamp(ts_str: str) -> datetime:
    formats = [
        ("%Y-%m-%dT%H:%M:%S%z", False),
        ("%Y-%m-%dT%H:%M:%S.%f%z", False),
        ("%b %d %H:%M:%S", True),
        ("%b %e %H:%M:%S", True),
    ]
    for fmt, replace_year in formats:
        try:
            dt = datetime.strptime(ts_str.strip(), fmt)
            if replace_year and dt.year == 1900:
                now = datetime.now(timezone.utc)
                dt = dt.replace(year=now.year)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
            return dt
        except ValueError:
            continue
    return datetime.now(timezone.utc).astimezone()


def _extract_links(result: dict) -> dict:
    """Add linked_ips/linked_names to parsed result from message text."""
    msg = result.get("message") or ""
    ips, names = extract_links(msg)
    result["linked_ips"] = ips
    result["linked_names"] = names
    return result


def parse_syslog(data: bytes, source_addr: tuple | None = None) -> dict | None:
    try:
        raw = data.decode("utf-8", errors="replace").strip()
    except Exception:
        return None

    if not raw:
        return None

    m = RFC5424_RE.match(raw)
    if m:
        pri = int(m.group(1))
        facility, severity = parse_priority(pri)
        ts = parse_timestamp(m.group(3))
        hostname = m.group(4) or (source_addr[0] if source_addr else "unknown")
        app_name = m.group(5) or "-"
        proc_id = m.group(6) or ""
        msg_id = m.group(7) or ""
        msg = m.group(8) or ""
        return _extract_links({
            "facility": facility,
            "severity": severity,
            "timestamp": ts,
            "hostname": hostname,
            "app_name": app_name,
            "process_id": proc_id,
            "msgid": msg_id,
            "message": msg,
            "raw": raw,
            "source_ip": source_addr[0] if source_addr else None,
        })

    m = RFC3164_RE.match(raw)
    if m:
        pri = int(m.group(1))
        facility, severity = parse_priority(pri)
        ts = parse_timestamp(m.group(2))
        hostname = m.group(3)
        msg = m.group(4) or ""
        # Try to extract app_name from "appname[pid]: message" pattern
        app_name = "-"
        proc_id = ""
        app_m = re.match(r"(\S+?)(?:\[(\d+)\])?:\s", msg)
        if app_m:
            app_name = app_m.group(1)
            proc_id = app_m.group(2) or ""
        return _extract_links({
            "facility": facility,
            "severity": severity,
            "timestamp": ts,
            "hostname": hostname,
            "app_name": app_name,
            "process_id": proc_id,
            "msgid": "",
            "message": msg,
            "raw": raw,
            "source_ip": source_addr[0] if source_addr else None,
        })

    # PRI-only: <PRI>MSG without timestamp/hostname (e.g. embedded/SIP devices)
    m = PRI_ONLY_RE.match(raw)
    if m:
        pri = int(m.group(1))
        facility, severity = parse_priority(pri)
        return _extract_links({
            "facility": facility,
            "severity": severity,
            "timestamp": datetime.now(timezone.utc),
            "hostname": source_addr[0] if source_addr else "unknown",
            "app_name": "-",
            "process_id": "",
            "msgid": "",
            "message": m.group(2) or raw,
            "raw": raw,
            "source_ip": source_addr[0] if source_addr else None,
        })

    # Fallback: just store raw (no PRI → default to INFO, not EMERG)
    return _extract_links({
        "facility": 0,
        "severity": 6,
        "timestamp": datetime.now(timezone.utc),
        "hostname": source_addr[0] if source_addr else "unknown",
        "app_name": "-",
        "process_id": "",
        "msgid": "",
        "message": raw,
        "raw": raw,
        "source_ip": source_addr[0] if source_addr else None,
    })


def parse_syslog_raw(raw: str, source_addr) -> dict | None:
    return parse_syslog(raw.encode("utf-8"), source_addr)


# RFC 3164 with app_name extraction from MSG tag
RFC3164_APP_RE = re.compile(
    r"<(\d{1,3})>"                            # PRI
    r"(\S{3}\s+\d{1,2}\s\d{2}:\d{2}:\d{2})\s" # TIMESTAMP
    r"(\S+)\s"                                # HOSTNAME
    r"(\S+?)(?:\[(\d+)\])?:\s"                # APPNAME[PID]:
    r"(.*)"                                    # MSG
)

# Aruba IAP structured log
ARUBA_RE = re.compile(
    r"<(\d{1,3})>"                            # PRI
    r"(\S{3}\s+\d{1,2}\s\d{2}:\d{2}:\d{2})\s" # TIMESTAMP
    r"(\S+)\s"                                # HOSTNAME
    r"(\S+?)(?:\[(\d+)\])?:\s"                # APPNAME[PID]:
    r"(.*)"                                    # MSG
)


def parse_rfc3164_tag(raw: str, source_addr) -> dict | None:
    m = RFC3164_APP_RE.match(raw)
    if not m:
        return None
    pri = int(m.group(1))
    facility, severity = parse_priority(pri)
    return _extract_links({
        "facility": facility,
        "severity": severity,
        "timestamp": parse_timestamp(m.group(2)),
        "hostname": m.group(3),
        "app_name": m.group(4) or "-",
        "process_id": m.group(5) or "",
        "msgid": "",
        "message": m.group(6) or raw,
        "raw": raw,
        "source_ip": source_addr[0] if source_addr else None,
    })


def parse_aruba_iap(raw: str, source_addr) -> dict | None:
    m = ARUBA_RE.match(raw)
    if not m:
        return None
    pri = int(m.group(1))
    facility, severity = parse_priority(pri)
    msg = m.group(6) or raw
    ap_name = m.group(3)
    app_name = m.group(4) or "-"
    if "|AP " in msg:
        ap_match = re.search(r"\|AP\s+(\S+)", msg)
        if ap_match:
            ap_name = ap_match.group(1).rstrip("@")
    return _extract_links({
        "facility": facility,
        "severity": severity,
        "timestamp": parse_timestamp(m.group(2)),
        "hostname": ap_name,
        "app_name": app_name,
        "process_id": m.group(5) or "",
        "msgid": "",
        "message": msg,
        "raw": raw,
        "source_ip": source_addr[0] if source_addr else None,
    })


# Zimbra/Carbonio monitor (zimbramon)
# Format:
#   <PRI>TIMESTAMP HOSTNAME zimbramon[PID]: PID:info: zmstat METRIC.csv: HEADERS:: VALUES
ZIMBRAMON_RE = re.compile(
    r"<(\d{1,3})>"                                          # PRI
    r"(\S{3}\s+\d{1,2}\s\d{2}:\d{2}:\d{2})\s"              # TIMESTAMP
    r"(\S+)\s"                                              # HOSTNAME
    r"zimbramon\[\d+\]:\s+\d+:info:\s+"                     # zimbramon[PID]: PID:info:
    r"zmstat\s+(\S+)\.csv:\s+"                              # zmstat METRIC.csv:
    r"(.*?)::\s*(.*)"                                       # HEADERS:: VALUES
)


def parse_zimbramon(raw: str, source_addr) -> dict | None:
    m = ZIMBRAMON_RE.match(raw)
    if not m:
        return None
    pri = int(m.group(1))
    facility, severity = parse_priority(pri)
    metric_name = m.group(4)
    headers = m.group(5)
    values = m.group(6)
    csv_headers = [h.strip() for h in headers.split(",")] if headers else []
    csv_values = [v.strip() for v in values.split(",")] if values else []
    fields = {}
    for i, h in enumerate(csv_headers):
        if i < len(csv_values):
            v = csv_values[i]
            # Try numeric conversion
            try:
                if "." in v:
                    fields[h] = float(v)
                else:
                    fields[h] = int(v)
            except (ValueError, TypeError):
                fields[h] = v
        else:
            fields[h] = None
    msg = f"zmstat {metric_name}: " + ", ".join(f"{h}={v}" for h, v in fields.items())
    return _extract_links({
        "facility": facility,
        "severity": severity,
        "timestamp": parse_timestamp(m.group(2)),
        "hostname": m.group(3),
        "app_name": f"zmstat-{metric_name}",
        "process_id": "",
        "msgid": "",
        "message": msg,
        "raw": raw,
        "source_ip": source_addr[0] if source_addr else None,
        "zmstat_metric": metric_name,
        "zmstat_fields": fields,
    })


PARSERS = {
    "default": lambda raw, addr: parse_syslog_raw(raw, addr),
    "rfc3164_tag": parse_rfc3164_tag,
    "aruba_iap": parse_aruba_iap,
    "zimbramon": parse_zimbramon,
}


def parse_with_template(parser_type: str, data: bytes, source_addr) -> dict:
    parser = PARSERS.get(parser_type)
    text = data.decode("utf-8", errors="replace").strip()
    if parser:
        result = parser(text, source_addr)
        if result:
            return result
    return parse_syslog_raw(text, source_addr)


SEVERITY_NAMES = {
    0: "emerg", 1: "alert", 2: "crit", 3: "error",
    4: "warning", 5: "notice", 6: "info", 7: "debug",
}

FACILITY_NAMES = {
    0: "kern", 1: "user", 2: "mail", 3: "daemon",
    4: "auth", 5: "syslog", 6: "lpr", 7: "news",
    8: "uucp", 9: "cron", 10: "authpriv", 11: "ftp",
    16: "local0", 17: "local1", 18: "local2", 19: "local3",
    20: "local4", 21: "local5", 22: "local6", 23: "local7",
}

# IPv4 address pattern
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# Hostname-like: word containing a dot and at least one letter (FQDN like db01.example.com)
HOSTNAME_RE = re.compile(r"\b([a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}[a-zA-Z0-9.-]*)\b")


def extract_links(message: str) -> tuple[list[str], list[str]]:
    if not message:
        return [], []
    ips = list(set(IP_RE.findall(message)))
    names = list(set(HOSTNAME_RE.findall(message)))
    return ips, names
