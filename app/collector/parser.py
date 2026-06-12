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
        return {
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
        }

    m = RFC3164_RE.match(raw)
    if m:
        pri = int(m.group(1))
        facility, severity = parse_priority(pri)
        ts = parse_timestamp(m.group(2))
        hostname = m.group(3)
        msg = m.group(4) or ""
        return {
            "facility": facility,
            "severity": severity,
            "timestamp": ts,
            "hostname": hostname,
            "app_name": "-",
            "process_id": "",
            "msgid": "",
            "message": msg,
            "raw": raw,
            "source_ip": source_addr[0] if source_addr else None,
        }

    # Fallback: just store raw
    return {
        "facility": 0,
        "severity": 0,
        "timestamp": datetime.now(timezone.utc),
        "hostname": source_addr[0] if source_addr else "unknown",
        "app_name": "-",
        "process_id": "",
        "msgid": "",
        "message": raw,
        "raw": raw,
        "source_ip": source_addr[0] if source_addr else None,
    }


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
