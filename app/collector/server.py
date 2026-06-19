# Copyright (c) 2026 PlurumTech.com
# SPDX-License-Identifier: LicenseRef-Personal-Use-Only
import asyncio
import structlog
from collections import Counter
from datetime import datetime, timezone

from app.config import Config
from app.collector.parser import parse_syslog, parse_with_template
from app.collector.app_parsers import APP_PARSERS


class SyslogServer:
    CACHE_TTL = 300  # seconds before re-fetching device_apps/template cache

    def __init__(self, config: Config):
        self.cfg = config
        self.log = structlog.get_logger()
        self._udp_server: asyncio.DatagramServer | None = None
        self._tcp_server: asyncio.Server | None = None
        self._batch: list[tuple] = []
        self._batch_lock = asyncio.Lock()
        self._db_pool = None
        self._running = True
        self._template_cache: dict[str, tuple[str, float]] = {}  # source_ip -> (parser_type, ts)
        self._device_apps_cache: dict[int, tuple[list[str], float]] = {}  # device_id -> ([app_id], ts)

    async def start(self):
        import asyncpg

        dsn = self.cfg.db_dsn
        self._db_pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=2,
            max_size=5,
            command_timeout=10,
        )

        # Start batch flusher
        asyncio.create_task(self._batch_flusher())
        # Periodic cache refresh
        asyncio.create_task(self._cache_refresher())

        if self.cfg.collector_udp:
            try:
                await self._start_udp()
            except Exception as e:
                self.log.error("udp_start_failed", error=str(e))
        if self.cfg.collector_tcp:
            try:
                await self._start_tcp()
            except Exception as e:
                self.log.error("tcp_start_failed", error=str(e))

    async def stop(self):
        self._running = False
        await self._flush_batch()
        if self._udp_server:
            self._udp_server.close()
        if self._tcp_server:
            self._tcp_server.close()
        if self._db_pool:
            await self._db_pool.close()

    async def _start_udp(self):
        loop = asyncio.get_running_loop()

        class UDPProtocol(asyncio.DatagramProtocol):
            def __init__(self, handler):
                self.handler = handler

            def connection_made(self, transport):
                self.transport = transport

            def datagram_received(self, data, addr):
                asyncio.ensure_future(self.handler(data, addr))

        transport, protocol = await loop.create_datagram_endpoint(
            lambda: UDPProtocol(self._handle_message),
            local_addr=(self.cfg.collector_bind, self.cfg.collector_port),
            allow_broadcast=True,
        )
        self._udp_server = transport
        self.log.info("udp_listening", addr=self.cfg.collector_bind,
                       port=self.cfg.collector_port)

    async def _start_tcp(self):
        self._tcp_server = await asyncio.start_server(
            self._handle_tcp_client,
            host=self.cfg.collector_bind,
            port=self.cfg.collector_port,
        )
        self.log.info("tcp_listening", addr=self.cfg.collector_bind,
                       port=self.cfg.collector_port)

    async def _handle_tcp_client(self, reader: asyncio.StreamReader, writer):
        addr = writer.get_extra_info("peername")
        try:
            while self._running:
                # RFC 6584 octet-counted: "NNN <msg>" or plain newline-delimited
                first = await reader.read(1)
                if not first:
                    break
                if first.isdigit():
                    rest = await reader.readuntil(b' ')
                    count = int(first + rest[:-1])
                    msg = await reader.readexactly(count)
                    data = msg.rstrip(b'\n')
                else:
                    rest = await reader.readuntil(b'\n')
                    data = first + rest[:-1]
                await self._handle_message(data, addr)
        except (asyncio.IncompleteReadError, ConnectionResetError, asyncio.LimitOverrunError):
            pass
        except Exception:
            pass
        finally:
            writer.close()

    def _get_cached_template(self, source_ip: str) -> str | None:
        entry = self._template_cache.get(source_ip)
        if entry:
            pt, ts = entry
            if datetime.now(timezone.utc).timestamp() - ts <= self.CACHE_TTL:
                return pt
            del self._template_cache[source_ip]
        return None

    def _set_cached_template(self, source_ip: str, parser_type: str):
        self._template_cache[source_ip] = (
            parser_type, datetime.now(timezone.utc).timestamp()
        )

    def _get_cached_apps(self, device_id: int) -> list[str] | None:
        entry = self._device_apps_cache.get(device_id)
        if entry:
            apps, ts = entry
            if datetime.now(timezone.utc).timestamp() - ts <= self.CACHE_TTL:
                return apps
            del self._device_apps_cache[device_id]
        return None

    def _set_cached_apps(self, device_id: int, apps: list[str]):
        self._device_apps_cache[device_id] = (
            apps, datetime.now(timezone.utc).timestamp()
        )

    async def _handle_message(self, data: bytes, addr):
        source_ip = addr[0] if addr else "0.0.0.0"
        parser_type = self._get_cached_template(source_ip)
        if parser_type:
            parsed = parse_with_template(parser_type, data, addr)
        else:
            parsed = parse_syslog(data, addr)
        if not parsed:
            return

        msg = parsed["message"]
        # Try all registered app parsers on the message
        app_hits = []
        for app_id, parse_fn in APP_PARSERS.items():
            result = parse_fn(msg)
            if result:
                app_hits.append((app_id, result[1]))

        async with self._batch_lock:
            self._batch.append((
                parsed["hostname"],
                parsed["timestamp"],
                parsed["facility"],
                parsed["severity"],
                parsed["app_name"],
                parsed["msgid"],
                msg,
                parsed["raw"],
                parsed.get("source_ip", "0.0.0.0"),
                parsed.get("linked_ips", []),
                parsed.get("linked_names", []),
                app_hits,  # 12th element: list of (app_id, fields)
            ))

        if len(self._batch) >= self.cfg.collector_batch_size:
            asyncio.ensure_future(self._flush_batch())

    async def _cache_refresher(self):
        while self._running:
            await asyncio.sleep(self.CACHE_TTL)
            now = datetime.now(timezone.utc).timestamp()
            # Clear stale template entries
            stale_tpl = [k for k, (_, ts) in self._template_cache.items() if now - ts > self.CACHE_TTL]
            for k in stale_tpl:
                del self._template_cache[k]
            # Clear stale device_apps entries
            stale_apps = [k for k, (_, ts) in self._device_apps_cache.items() if now - ts > self.CACHE_TTL]
            for k in stale_apps:
                del self._device_apps_cache[k]
            if stale_tpl or stale_apps:
                self.log.info("cache_refresh", templates=len(stale_tpl), device_apps=len(stale_apps))

    async def _batch_flusher(self):
        while self._running:
            await asyncio.sleep(self.cfg.collector_batch_interval)
            await self._flush_batch()

    async def _flush_batch(self):
        async with self._batch_lock:
            if not self._batch:
                return
            batch = self._batch[:]
            self._batch.clear()

        if not self._db_pool:
            return

        try:
            async with self._db_pool.acquire() as conn:
                source_ips = set(r[8] for r in batch)
                self.log.info("batch_source_ips", ips=list(source_ips))
                device_map = {}
                for sip in source_ips:
                    hn = next((r[0] for r in batch if r[8] == sip), sip)
                    row = await conn.fetchrow(
                        "SELECT id FROM devices WHERE host(ip) = $1", sip
                    )
                    if row:
                        device_map[sip] = row["id"]
                        await conn.execute(
                            "UPDATE devices SET hostname = $1 WHERE id = $2 AND hostname != $1",
                            hn, row["id"],
                        )
                    else:
                        # Not found by IP — try by hostname (device may have changed IP)
                        row = None
                        if hn and hn != sip:
                            row = await conn.fetchrow(
                                "SELECT id FROM devices WHERE hostname = $1", hn
                            )
                        if row:
                            # Same hostname, different IP — update IP
                            device_map[sip] = row["id"]
                            await conn.execute(
                                "UPDATE devices SET ip = $1::inet WHERE id = $2",
                                sip, row["id"],
                            )
                        else:
                            try:
                                did = await conn.fetchval(
                                    "INSERT INTO devices (hostname, ip) VALUES ($1, $2::inet) RETURNING id",
                                    hn, sip,
                                )
                                device_map[sip] = did
                            except Exception:
                                row2 = await conn.fetchrow(
                                    "SELECT id FROM devices WHERE host(ip) = $1", sip
                                )
                                if row2:
                                    device_map[sip] = row2["id"]
                                else:
                                    device_map[sip] = 0

                skipped = [r[8] for r in batch if r[8] not in device_map]
                if skipped:
                    self.log.warning("batch_skip_unknown_source", ips=set(skipped),
                                      device_map_keys=list(device_map.keys()))
                records = [
                    (
                        device_map[r[8]], r[1], r[2], r[3],
                        r[4], r[5], r[6], r[7],
                        r[8],  # source_ip
                        r[9], r[10],
                    )
                    for r in batch
                    if r[8] in device_map
                ]

                if records:
                    await conn.copy_records_to_table(
                        "syslog_messages",
                        records=records,
                        columns=["device_id","ts","facility","severity",
                                 "app_name","msgid","message","raw",
                                 "source_ip",
                                 "linked_ips","linked_names"],
                    )
                    # Insert app_metrics for matched app parsers
                    app_rows = []
                    for r in batch:
                        did = device_map.get(r[8])
                        if not did or not r[11]:
                            continue
                        enabled = self._get_cached_apps(did)
                        if enabled is None:
                            en_rows = await conn.fetch(
                                "SELECT app_id FROM device_apps "
                                "WHERE device_id = $1 AND enabled = true",
                                did,
                            )
                            enabled = [e["app_id"] for e in en_rows]
                            self._set_cached_apps(did, enabled)
                        for app_id, fields in r[11]:
                            if app_id in enabled:
                                app_rows.append((did, app_id, r[1], fields))
                    if app_rows:
                        await conn.executemany(
                            "INSERT INTO app_metrics (device_id, app_id, ts, fields) "
                            "VALUES ($1, $2, $3, $4::jsonb)",
                            app_rows,
                        )

                    # Update hourly stats
                    stats_counter = Counter()
                    for r in records:
                        hour = r[1].replace(minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
                        if hour.tzinfo is None:
                            hour = hour.replace(tzinfo=timezone.utc)
                        stats_counter[(r[0], hour, r[3])] += 1
                    if stats_counter:
                        await conn.executemany(
                            "INSERT INTO log_stats_hourly (device_id, hour, severity, count) "
                            "VALUES ($1, $2, $3, $4) "
                            "ON CONFLICT (device_id, hour, severity) "
                            "DO UPDATE SET count = log_stats_hourly.count + EXCLUDED.count",
                            [(k[0], k[1], k[2], v) for k, v in stats_counter.items()],
                        )

                    # Update template cache for known devices
                    dids = set(r[0] for r in records)
                    tpl_rows = await conn.fetch(
                        "SELECT d.id, t.parser_type "
                        "FROM devices d "
                        "LEFT JOIN parse_templates t ON t.id = d.template_id "
                        "WHERE d.id = ANY($1::int[]) AND t.parser_type IS NOT NULL",
                        list(dids),
                    )
                    sip_to_did = {r[8]: r[0] for r in records}
                    for tpl_row in tpl_rows:
                        did = tpl_row["id"]
                        ptype = tpl_row["parser_type"]
                        for sip, d in sip_to_did.items():
                            if d == did:
                                self._set_cached_template(sip, ptype)

                    # Update device_last_seen for online tracking
                    max_ts = {}
                    for r in records:
                        did = r[0]
                        if did not in max_ts or r[1] > max_ts[did]:
                            max_ts[did] = r[1]
                    if max_ts:
                        await conn.executemany(
                            "INSERT INTO device_last_seen (device_id, ts) "
                            "VALUES ($1, $2) "
                            "ON CONFLICT (device_id) "
                            "DO UPDATE SET ts = EXCLUDED.ts",
                            [(d, t) for d, t in max_ts.items()],
                        )

                    dev_ids = set(r[0] for r in records)
                    self.log.info("batch_inserted", count=len(records), device_ids=list(dev_ids))
        except Exception as e:
            self.log.error("batch_insert_failed", error=str(e))
            # Re-queue failed batch to avoid data loss
            async with self._batch_lock:
                self._batch = batch + self._batch
