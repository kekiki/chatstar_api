"""Filter ChatStar's JSON output or a stream from `fly logs --json`."""
import argparse
import json
import signal
import sys
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.logging_config import LEVELS, redact

HIGHLIGHTS = (
    "route", "method", "status", "duration_ms", "reason", "error_type", "google_status",
    "order_no", "google_order_id", "diamonds_granted", "diamonds_revoked", "request_id",
)


def read_records(lines):
    """Fly CLI may pretty-print each outer record across multiple lines."""
    buffer = []
    size = 0
    for line in lines:
        if not buffer and line.strip() == "{":
            buffer = [line]
            size = len(line)
            continue
        if buffer:
            buffer.append(line)
            size += len(line)
            if size > 256_000:
                buffer.clear()
                continue
            if line.rstrip() != "}":
                continue
            line = "".join(buffer)
            buffer.clear()
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        if isinstance(entry.get("event"), str):
            yield entry
            continue
        # Fly wraps stdout in `message`; retain non-JSON Fly/startup logs too.
        message = entry.get("message")
        if not isinstance(message, str):
            continue
        try:
            record = json.loads(message)
        except ValueError:
            record = None
        if isinstance(record, dict) and isinstance(record.get("event"), str):
            yield record
        else:
            yield {"timestamp": entry.get("timestamp", ""), "level": str(entry.get("level", "INFO")).upper(),
                   "event": "fly.log", "message": redact(message)}


def matches(record, args):
    level = str(record.get("level", "INFO")).upper()
    level = "WARNING" if level == "WARN" else level
    return (
        LEVELS.get(level, 0) >= (LEVELS[args.level] if args.level else 0)
        and (not args.event or any(record["event"] == prefix or record["event"].startswith(prefix + ".") for prefix in args.event))
        and (not args.route or record.get("route") == args.route)
        and (not args.request_id or record.get("request_id") == args.request_id)
        and (not args.order or args.order in (record.get("order_no"), record.get("google_order_id")))
    )


def format_record(record, timezone):
    timestamp = record.get("timestamp", "")
    if timestamp and timezone:
        try:
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(timezone).isoformat(timespec="milliseconds")
        except ValueError:
            pass
    fields = [key for key in HIGHLIGHTS if key in record]
    fields += sorted(record.keys() - set(fields) - {"timestamp", "level", "event", "logger"})
    details = " ".join(f"{key}={json.dumps(record[key], ensure_ascii=False)}" for key in fields)
    return f"{timestamp} {record.get('level', 'INFO'):<8} {record['event']} {details}".rstrip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", action="append", help="Event name or dotted prefix; repeat to match any")
    parser.add_argument("--route", help="Exact route template, e.g. /api/order/verify")
    parser.add_argument("--order", help="Exact internal order number or Google GPA ID")
    parser.add_argument("--request-id", help="Exact X-Request-ID")
    parser.add_argument("--level", choices=LEVELS, help="Minimum severity")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="Print normalized JSON lines")
    output.add_argument("--timezone", metavar="IANA_ZONE", help="Render timestamps in this time zone")
    args = parser.parse_args()
    try:
        tz = ZoneInfo(args.timezone) if args.timezone else None
    except ZoneInfoNotFoundError:
        parser.error("unknown IANA timezone; e.g. Asia/Shanghai")
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    for record in read_records(sys.stdin):
        if matches(record, args):
            print(json.dumps(record, ensure_ascii=False) if args.json else format_record(record, tz), flush=True)


if __name__ == "__main__":
    main()
