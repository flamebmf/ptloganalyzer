import asyncio
import structlog

from app.config import Config
from app.collector.parser import parse_syslog


class SyslogServer:
    def __init__(self, config: Config):
        self.cfg = config
        self.log = structlog.get_logger()
        self._udp_server: asyncio.DatagramServer | None = None
        self._tcp_server: asyncio.Server | None = None
        self._batch: list[tuple] = []
        self._batch_lock = asyncio.Lock()
        self._db_pool = None
        self._running = True

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
                data = await reader.readline()
                if not data:
                    break
                await self._handle_message(data, addr)
        except (ConnectionResetError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    async def _handle_message(self, data: bytes, addr):
        parsed = parse_syslog(data, addr)
        if not parsed:
            return

        async with self._batch_lock:
            self._batch.append((
                parsed["hostname"],
                parsed["timestamp"],
                parsed["facility"],
                parsed["severity"],
                parsed["app_name"],
                parsed["msgid"],
                parsed["message"],
                parsed["raw"],
                parsed.get("source_ip", "0.0.0.0"),
            ))

        if len(self._batch) >= self.cfg.collector_batch_size:
            asyncio.ensure_future(self._flush_batch())

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
                        did = await conn.fetchval(
                            "INSERT INTO devices (hostname, ip) VALUES ($1, $2::inet) RETURNING id",
                            hn, sip,
                        )
                        device_map[sip] = did

                records = [
                    (
                        device_map[r[8]], r[1], r[2], r[3],
                        r[4], r[5], r[6], r[7],
                    )
                    for r in batch
                    if r[8] in device_map
                ]

                if records:
                    await conn.executemany(
                        "INSERT INTO syslog_messages "
                        "(device_id, ts, facility, severity, app_name, msgid, message, raw) "
                        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
                        records,
                    )
                    self.log.info("batch_inserted", count=len(records))
        except Exception as e:
            self.log.error("batch_insert_failed", error=str(e))
            # Re-queue failed batch to avoid data loss
            async with self._batch_lock:
                self._batch = batch + self._batch
