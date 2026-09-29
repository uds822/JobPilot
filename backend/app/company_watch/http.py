"""Bounded public HTTP with address checks at the actual TCP connection."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx
from httpcore._backends.auto import AutoBackend


def validate_destination(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public HTTP(S) destinations without credentials are allowed")
    if parsed.port not in {None, 80, 443}:
        raise ValueError("Nonstandard destination ports are blocked")
    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")) or "." not in host:
        raise ValueError("Internal destination is blocked")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if not address.is_global:
        raise ValueError("Nonpublic destination is blocked")
    return host


class PublicNetworkBackend(AutoBackend):
    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        addresses = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM),
            timeout=timeout or 5,
        )
        ips = list(dict.fromkeys(record[4][0] for record in addresses))
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise httpcore.ConnectError("DNS resolved to a nonpublic destination")
        # Connect to the checked address, not the hostname: no second DNS lookup.
        # httpcore retains the original hostname for TLS and certificate checks.
        return await super().connect_tcp(ips[0], port, timeout, local_address, socket_options)


def public_client() -> httpx.AsyncClient:
    transport = httpx.AsyncHTTPTransport(trust_env=False, retries=0)
    # httpx does not expose network_backend; isolate this integration here.
    transport._pool._network_backend = PublicNetworkBackend()
    return httpx.AsyncClient(
        transport=transport, trust_env=False, follow_redirects=False,
        timeout=httpx.Timeout(15, connect=5),
        headers={"User-Agent": "JobAuto-CompanyWatch/1.0", "Accept": "text/html,application/json", "Accept-Encoding": "identity"},
    )


@dataclass
class RequestBudget:
    remaining: int = 40
    max_bytes: int = 2_000_000
    max_redirects: int = 4


async def request_public(client, url, *, budget=None, method="GET", json=None, semaphore=None, hosts=None):
    budget = budget or RequestBudget()
    chain = []
    current = url
    for _ in range(budget.max_redirects + 1):
        host = validate_destination(current)
        if budget.remaining <= 0:
            raise ValueError("Request budget exhausted")
        budget.remaining -= 1
        host_lock = hosts.setdefault(host, asyncio.Semaphore(2)) if hosts is not None else asyncio.Semaphore(1)
        async with semaphore or asyncio.Semaphore(1), host_lock:
            async with client.stream(method, current, json=json, follow_redirects=False) as response:
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > budget.max_bytes:
                        raise ValueError("Response exceeds page-size budget")
                    chunks.append(chunk)
                # aiter_bytes already decoded compression; don't decode it again.
                headers = {key: value for key, value in response.headers.items() if key.lower() not in {"content-encoding", "content-length"}}
                buffered = httpx.Response(response.status_code, headers=headers, content=b"".join(chunks), request=response.request)
        chain.append(current)
        if buffered.status_code in {301, 302, 303, 307, 308}:
            location = buffered.headers.get("location")
            if not location:
                raise ValueError("Redirect missing destination")
            current = urljoin(current, location)
            if buffered.status_code in {301, 302, 303}:
                method, json = "GET", None
            continue
        buffered.extensions["redirect_chain"] = chain
        return buffered
    raise ValueError("Redirect budget exhausted")
