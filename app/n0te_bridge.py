from __future__ import annotations
import json, socket, itertools, threading, time
from dataclasses import dataclass
from typing import Any

@dataclass
class BridgeConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    connect_timeout: float = 1.5
    timeout: float = 12.0
    max_bytes: int = 8 * 1024 * 1024

class AbletonBridge:
    def __init__(self, config: BridgeConfig | None = None):
        self.config = config or BridgeConfig()
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": next(self._ids),
            "method": method,
            "params": params or {},
        }
        line = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        with self._lock:
            with socket.create_connection((self.config.host, self.config.port), self.config.connect_timeout) as sock:
                sock.settimeout(float((params or {}).get("timeout") or self.config.timeout))
                sock.sendall(line)
                response = self._read_line(sock)
        msg = json.loads(response.decode("utf-8"))
        if "error" in msg:
            err = msg["error"]
            raise RuntimeError(f"{err.get('code', -32000)} {err.get('message','Ableton bridge error')}")
        return msg.get("result")

    def _read_line(self, sock: socket.socket) -> bytes:
        chunks = []
        total = 0
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > self.config.max_bytes:
                raise RuntimeError("Ableton bridge response too large")
            if b"\n" in chunk:
                break
        data = b"".join(chunks)
        return data.split(b"\n", 1)[0]
