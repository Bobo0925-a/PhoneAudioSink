# -*- coding: utf-8 -*-
"""
WiFi 网络链路：TCP 音频服务端 + UDP 局域网自动发现响应。

- TCP：PC 作为服务端监听固定端口，手机 App 作为客户端连入。
- UDP：监听发现端口，收到手机的发现广播后回复本机名称与 TCP 端口，供自动发现。
"""

import socket
import threading
import logging

import protocol

logger = logging.getLogger("net-link")


def local_ip() -> str:
    """取本机用于局域网通信的 IPv4 地址（不实际发包）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class DiscoveryResponder(threading.Thread):
    """UDP 发现响应线程：答复手机的自动发现请求。"""

    def __init__(self, discover_port: int, tcp_port: int, hostname: str | None = None) -> None:
        super().__init__(daemon=True)
        self.discover_port = discover_port
        self.tcp_port = tcp_port
        self.hostname = hostname or socket.gethostname()
        self._sock: socket.socket | None = None
        self._running = False

    def run(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("", self.discover_port))
        self._sock.settimeout(1.0)
        self._running = True
        logger.info("UDP 发现服务监听端口 %d，TCP 端口 %d", self.discover_port, self.tcp_port)

        while self._running:
            try:
                data, addr = self._sock.recvfrom(1024)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                text = data.decode("utf-8", errors="ignore").strip()
            except Exception:
                continue
            if protocol.DISCOVER_REQUEST in text:
                reply = f"{protocol.DISCOVER_REPLY_PREFIX}|{self.hostname}|{self.tcp_port}"
                try:
                    self._sock.sendto(reply.encode("utf-8"), addr)
                    logger.info("响应发现请求: %s <- %s", addr[0], reply)
                except OSError as e:
                    logger.warning("发现响应发送失败: %s", e)

    def stop(self) -> None:
        self._running = False
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass


class TcpServer:
    """TCP 音频服务端，一次对接一个手机客户端。"""

    def __init__(self, host: str = "0.0.0.0", port: int = 42101) -> None:
        self.port = port
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind((host, port))
        self._srv.listen(1)
        self._client: socket.socket | None = None
        logger.info("TCP 音频服务监听 %s:%d", host, port)

    def accept(self, timeout: float | None = None):
        """返回 (客户端socket, 地址)；供上层自行管理生命周期。"""
        self._srv.settimeout(timeout)
        sock, addr = self._srv.accept()
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8192)
        self._client = sock
        logger.info("手机已连接: %s（TCP_NODELAY 已开启，发送缓冲 8KB）", addr)
        return sock, addr

    def wait_for_client(self, timeout: float | None = None):
        self._srv.settimeout(timeout)
        self._client, addr = self._srv.accept()
        # 关闭 Nagle 算法：20ms 音频小包立即发出，避免攒包增加端到端延迟。
        self._client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # 限制内核发送缓冲，避免发送侧长时间积压几秒旧数据。
        self._client.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8192)
        logger.info("手机已连接: %s（TCP_NODELAY 已开启，发送缓冲 8KB）", addr)
        return addr

    @property
    def connected(self) -> bool:
        return self._client is not None

    def send_all(self, data: bytes) -> None:
        if self._client is None:
            raise RuntimeError("TCP 未连接")
        self._client.sendall(data)

    def close_client(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except OSError:
                pass
            self._client = None

    def close(self) -> None:
        self.close_client()
        try:
            self._srv.close()
        except OSError:
            pass
