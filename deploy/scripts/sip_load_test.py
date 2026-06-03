#!/usr/bin/env python3
"""
PyGBSentry SIP Load Test Tool.

Simulates SIP REGISTER/MESSAGE traffic to validate platform capacity.
Requires: pip install aiohttp

Usage:
    python sip_load_test.py --host 127.0.0.1 --port 5060 --devices 100 --duration 60
    python sip_load_test.py --host 127.0.0.1 --port 5060 --devices 500 --rate 10

WARNING: Use only against your own test infrastructure.
"""

import argparse
import asyncio
import hashlib
import random
import socket
import string
import sys
import time
from dataclasses import dataclass, field


@dataclass
class LoadTestResult:
    total_sent: int = 0
    total_received: int = 0
    total_errors: int = 0
    latencies: list = field(default_factory=list)
    start_time: float = 0
    end_time: float = 0

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time if self.end_time else 0

    @property
    def rps(self) -> float:
        return self.total_sent / self.duration if self.duration > 0 else 0

    @property
    def p50(self) -> float:
        return self._percentile(50)

    @property
    def p95(self) -> float:
        return self._percentile(95)

    @property
    def p99(self) -> float:
        return self._percentile(99)

    def _percentile(self, pct: int) -> float:
        if not self.latencies:
            return 0
        sorted_lat = sorted(self.latencies)
        idx = int(len(sorted_lat) * pct / 100)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]


def build_register_message(sip_server: str, sip_port: int, device_id: str, domain: str, nonce: str = "") -> bytes:
    """Build a SIP REGISTER message."""
    call_id = "".join(random.choices(string.hexdigits, k=16)).lower()
    branch = f"z9hG4bK-{call_id}"
    cseq = random.randint(1, 9999)

    msg = (
        f"REGISTER sip:{domain} SIP/2.0\r\n"
        f"Via: SIP/2.0/UDP {sip_server}:{sip_port};branch={branch};rport\r\n"
        f"From: <sip:{device_id}@{domain}>;tag={call_id[:8]}\r\n"
        f"To: <sip:{device_id}@{domain}>\r\n"
        f"Call-ID: {call_id}@{sip_server}\r\n"
        f"CSeq: {cseq} REGISTER\r\n"
        f"Contact: <sip:{device_id}@{sip_server}:{sip_port}>\r\n"
        f"Max-Forwards: 70\r\n"
        f"User-Agent: PyGBSentry-LoadTest/1.0\r\n"
        f"Expires: 3600\r\n"
        f"Allow: REGISTER, INVITE, ACK, BYE, CANCEL, MESSAGE, NOTIFY, SUBSCRIBE\r\n"
        f"Content-Length: 0\r\n"
        f"\r\n"
    )
    return msg.encode("utf-8")


def build_keepalive_message(sip_server: str, sip_port: int, device_id: str, domain: str) -> bytes:
    """Build a SIP MESSAGE (keepalive/heartbeat) message."""
    call_id = "".join(random.choices(string.hexdigits, k=16)).lower()
    branch = f"z9hG4bK-{call_id}"
    cseq = random.randint(1, 9999)

    msg = (
        f"MESSAGE sip:{domain} SIP/2.0\r\n"
        f"Via: SIP/2.0/UDP {sip_server}:{sip_port};branch={branch};rport\r\n"
        f"From: <sip:{device_id}@{domain}>;tag={call_id[:8]}\r\n"
        f"To: <sip:{domain}>\r\n"
        f"Call-ID: {call_id}@{sip_server}\r\n"
        f"CSeq: {cseq} MESSAGE\r\n"
        f"Max-Forwards: 70\r\n"
        f"User-Agent: PyGBSentry-LoadTest/1.0\r\n"
        f"Content-Type: Application/MANSCDP+xml\r\n"
        f"Content-Length: 0\r\n"
        f"\r\n"
    )
    return msg.encode("utf-8")


async def send_sip_message(
    sock: socket.socket, target: tuple, message: bytes, timeout: float = 5.0
) -> tuple[bool, float]:
    """Send a SIP message and wait for response. Returns (success, latency_ms)."""
    loop = asyncio.get_event_loop()
    start = time.monotonic()
    try:
        await loop.sock_sendto(sock, message, target)
        # Wait for response with timeout
        sock.settimeout(timeout)
        try:
            data, addr = sock.recvfrom(4096)
            latency = (time.monotonic() - start) * 1000
            response = data.decode("utf-8", errors="ignore")
            success = "SIP/2.0" in response and any(
                code in response for code in ["200", "401", "403", "404"]
            )
            return success, latency
        except socket.timeout:
            return False, (time.monotonic() - start) * 1000
    except Exception:
        return False, (time.monotonic() - start) * 1000


async def run_load_test(
    host: str, port: int, num_devices: int, duration: int, rate: int, domain: str
) -> LoadTestResult:
    """Run the SIP load test."""
    result = LoadTestResult()
    target = (host, port)

    print(f"Starting SIP load test:")
    print(f"  Target: {host}:{port}")
    print(f"  Devices: {num_devices}")
    print(f"  Duration: {duration}s")
    print(f"  Rate: {rate} msg/s")
    print()

    device_ids = [
        f"3402000000132{random.randint(1000000, 9999999)}" for _ in range(num_devices)
    ]

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)

    result.start_time = time.monotonic()
    end_time = result.start_time + duration
    interval = 1.0 / rate if rate > 0 else 0.01

    tasks = []
    sent_count = 0

    while time.monotonic() < end_time:
        device_id = random.choice(device_ids)
        if random.random() < 0.3:
            message = build_register_message(host, port, device_id, domain)
        else:
            message = build_keepalive_message(host, port, device_id, domain)

        task = asyncio.create_task(send_sip_message(sock, target, message))
        tasks.append(task)
        result.total_sent += 1
        sent_count += 1

        if sent_count % 100 == 0:
            elapsed = time.monotonic() - result.start_time
            print(f"  [{elapsed:.0f}s] Sent: {result.total_sent}, Errors: {result.total_errors}")

        await asyncio.sleep(interval)

    # Wait for remaining responses
    for task in asyncio.as_completed(tasks):
        try:
            success, latency = await task
            if success:
                result.total_received += 1
                result.latencies.append(latency)
            else:
                result.total_errors += 1
        except Exception:
            result.total_errors += 1

    result.end_time = time.monotonic()
    sock.close()
    return result


def main():
    parser = argparse.ArgumentParser(description="PyGBSentry SIP Load Test")
    parser.add_argument("--host", default="127.0.0.1", help="SIP server host")
    parser.add_argument("--port", type=int, default=5060, help="SIP server port")
    parser.add_argument("--devices", type=int, default=100, help="Number of simulated devices")
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds")
    parser.add_argument("--rate", type=int, default=10, help="Messages per second")
    parser.add_argument("--domain", default="3402000000", help="SIP domain")
    args = parser.parse_args()

    result = asyncio.run(
        run_load_test(args.host, args.port, args.devices, args.duration, args.rate, args.domain)
    )

    print("\n" + "=" * 60)
    print("  SIP Load Test Results")
    print("=" * 60)
    print(f"  Duration:        {result.duration:.1f}s")
    print(f"  Total sent:      {result.total_sent}")
    print(f"  Total received:  {result.total_received}")
    print(f"  Total errors:    {result.total_errors}")
    print(f"  Error rate:      {result.total_errors / max(result.total_sent, 1) * 100:.1f}%")
    print(f"  Throughput:      {result.rps:.1f} msg/s")
    if result.latencies:
        print(f"  Latency P50:     {result.p50:.1f}ms")
        print(f"  Latency P95:     {result.p95:.1f}ms")
        print(f"  Latency P99:     {result.p99:.1f}ms")
    print("=" * 60)


if __name__ == "__main__":
    main()
