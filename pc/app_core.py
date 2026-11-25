# -*- coding: utf-8 -*-
"""
PC 端核心逻辑：共享状态 + 后台采集/发送 Worker。

支持两种工作模式：
- listen：本机做 TCP 服务端，手机 App 主动连入（默认）
- connect：输入手机 IP，本机主动连过去（手机端需处于监听接收状态）
"""

import collections
import json
import logging
import os
import socket
import threading
import time

import numpy as np

import protocol
from audio_capture import AudioCapture
from net_link import DiscoveryResponder, TcpServer, local_ip
from opus_encoder import OpusEncoder

# ---- 运行状态 ----
IDLE = "idle"            # 已就绪，等待连接
CONNECTED = "connected"  # 已连接，正在推流
ERROR = "error"          # 最近一次连接/传输出错
STOPPING = "stopping"    # 正在退出

STATUS_TEXT = {
    IDLE: "等待连接",
    CONNECTED: "正在推流",
    ERROR: "连接异常",
    STOPPING: "正在停止",
}

DEFAULT_CONFIG = {
    "tcp_port": 42101,
    "discover_port": 42100,
    "sample_rate": 48000,
    "channels": 2,
    "codec": 1,
    "frame_size": 960,
    "bitrate": 64000,
    "input_device": "",
    "ping_interval_sec": 1.5,
    "volume": 1.0,
    "show_window_on_start": True,
    "reduce_motion": False,
}

logger = logging.getLogger("core")


def app_dir() -> str:
    """配置/日志所在目录：打包后为 exe 同目录，源码运行时为本文件目录。"""
    if getattr(os.sys, "frozen", False):
        return os.path.dirname(os.sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def load_config(path: str | None = None) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    path = path or os.path.join(app_dir(), "config.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("配置文件读取失败，使用默认值: %s", exc)
    else:
        save_config(cfg, path)
    return cfg


def save_config(cfg: dict, path: str | None = None) -> None:
    path = path or os.path.join(app_dir(), "config.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.warning("配置写入失败: %s", exc)


def list_input_devices() -> list[tuple[int, str]]:
    """返回可采集的输入设备 [(索引, 名称)]。"""
    import sounddevice as sd
    out: list[tuple[int, str]] = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) > 0:
            out.append((idx, dev["name"]))
    return out


class _LogHandler(logging.Handler):
    """把最近日志投入内存队列，供界面/排障查看。"""

    def __init__(self, sink: collections.deque) -> None:
        super().__init__()
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._sink.append(self.format(record))
        except Exception:
            pass


class AppState:
    """跨线程共享的运行状态（所有读写都过锁）。"""

    def __init__(self, cfg: dict) -> None:
        self._lock = threading.Lock()
        self.status = IDLE
        self.local_ip = local_ip()
        self.client_addr = ""
        self.device_name = cfg.get("input_device") or ""
        self.frames_sent = 0
        self.bytes_sent = 0
        self.dropped_blocks = 0
        self.last_error = ""
        self.pending_device: str | None = None
        self.gain = float(cfg.get("volume", 1.0))
        self.mode = "listen"
        self.remote_host = ""
        self.started_at = time.monotonic()
        self.log_lines: collections.deque[str] = collections.deque(maxlen=300)

    # --- 写入 ---
    def set_status(self, status: str, **fields) -> None:
        with self._lock:
            self.status = status
            for k, v in fields.items():
                setattr(self, k, v)

    def note_error(self, exc: Exception) -> None:
        with self._lock:
            self.status = ERROR
            self.last_error = f"{type(exc).__name__}: {exc}"

    def add_stats(self, opus_len: int) -> None:
        with self._lock:
            self.frames_sent += 1
            self.bytes_sent += opus_len

    def request_device(self, name: str) -> None:
        with self._lock:
            self.pending_device = name

    def set_gain(self, value: float) -> None:
        with self._lock:
            self.gain = max(0.0, min(1.5, float(value)))

    def set_mode(self, mode: str, host: str = "") -> None:
        with self._lock:
            self.mode = mode
            self.remote_host = host

    # --- 读取 ---
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "status": self.status,
                "status_text": STATUS_TEXT.get(self.status, self.status),
                "local_ip": self.local_ip,
                "client_addr": self.client_addr,
                "device_name": self.device_name or "默认设备",
                "frames_sent": self.frames_sent,
                "bytes_sent": self.bytes_sent,
                "dropped_blocks": self.dropped_blocks,
                "last_error": self.last_error,
                "pending_device": self.pending_device,
                "gain": self.gain,
                "mode": self.mode,
                "remote_host": self.remote_host,
                "uptime": time.monotonic() - self.started_at,
            }

    def log_text(self) -> str:
        with self._lock:
            return "\n".join(self.log_lines)


class _Link:
    """对 socket 的轻量封装，统一 listen / connect 两种来源。"""

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock

    def send_all(self, data: bytes) -> None:
        self.sock.sendall(data)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class Worker(threading.Thread):
    """后台线程：采集 → Opus 编码 → TCP 发送。"""

    def __init__(self, cfg: dict, state: AppState, stop_event: threading.Event,
                 mode: str = "listen", host: str = "") -> None:
        super().__init__(name="audio-worker", daemon=True)
        self.cfg = cfg
        self.state = state
        self.stop_event = stop_event
        self.mode = mode
        self.host = host
        self._responder: DiscoveryResponder | None = None
        self._server: TcpServer | None = None
        self._encoder: OpusEncoder | None = None

    # ---- 入口 ----
    def run(self) -> None:
        self.state.set_mode(self.mode, self.host)
        tcp_port = int(self.cfg.get("tcp_port", 42101))

        self._encoder = OpusEncoder(
            sample_rate=int(self.cfg["sample_rate"]),
            channels=int(self.cfg["channels"]),
            bitrate=int(self.cfg["bitrate"]),
            frame_size=int(self.cfg["frame_size"]),
        )

        if self.mode == "connect":
            self._run_client(tcp_port)
        else:
            self._run_server(tcp_port)

        self._cleanup()

    def _run_server(self, tcp_port: int) -> None:
        discover_port = int(self.cfg.get("discover_port", 42100))
        self._responder = DiscoveryResponder(discover_port, tcp_port)
        self._responder.start()

        try:
            self._server = TcpServer(port=tcp_port)
        except OSError as exc:
            self.state.note_error(exc)
            logger.error("TCP 端口 %d 绑定失败: %s", tcp_port, exc)
            return

        logger.info("本机局域网地址 %s，正在监听 %d 等待手机连接 ...",
                    self.state.local_ip, tcp_port)

        while not self.stop_event.is_set():
            try:
                sock, addr = self._server.accept(timeout=1.0)
            except socket.timeout:
                continue
            except OSError as exc:
                if self.stop_event.is_set():
                    break
                self.state.note_error(exc)
                logger.error("监听中断: %s", exc)
                time.sleep(1.0)
                continue
            if sock is None:
                continue

            link = _Link(sock)
            try:
                self._session(link, f"{addr[0]}:{addr[1]}")
            except (OSError, RuntimeError, ValueError) as exc:
                self.state.note_error(exc)
                logger.warning("连接/传输中断: %s", exc)
            finally:
                self._send_bye(link)
                link.close()
                if not self.stop_event.is_set():
                    self.state.set_status(IDLE, client_addr="")
                    logger.info("已回到等待状态 ...")

    def _run_client(self, tcp_port: int) -> None:
        logger.info("准备主动连接手机 %s:%d ...", self.host, tcp_port)
        while not self.stop_event.is_set():
            link = None
            try:
                sock = socket.create_connection((self.host, tcp_port), timeout=3.0)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8192)
                link = _Link(sock)
                self._session(link, f"{self.host}:{tcp_port}")
            except (OSError, RuntimeError, ValueError) as exc:
                self.state.note_error(exc)
                logger.warning("连接 %s 失败: %s", self.host, exc)
            finally:
                if link is not None:
                    self._send_bye(link)
                    link.close()
                if not self.stop_event.is_set():
                    self.state.set_status(IDLE, client_addr="")
                    logger.info("2 秒后重试连接 ...")
                    self.stop_event.wait(2.0)

    # ---- 会话 ----
    def _session(self, link: _Link, addr_text: str) -> None:
        assert self._encoder is not None

        with self.state._lock:
            if self.state.pending_device is not None:
                self.cfg["input_device"] = self.state.pending_device
                self.state.pending_device = None
        device = self.cfg.get("input_device") or None

        capture = AudioCapture(
            sample_rate=int(self.cfg["sample_rate"]),
            channels=int(self.cfg["channels"]),
            blocksize=int(self.cfg["frame_size"]),
            device=device,
        )

        hello = protocol.pack_hello(
            sample_rate=int(self.cfg["sample_rate"]),
            channels=int(self.cfg["channels"]),
            codec=protocol.CODEC_OPUS,
            frame_size=int(self.cfg["frame_size"]),
            bitrate=int(self.cfg["bitrate"]),
        )
        link.send_all(hello)
        self.state.set_status(
            CONNECTED,
            client_addr=addr_text,
            device_name=self.cfg.get("input_device") or "默认设备",
            last_error="",
        )
        logger.info("已连接 %s，发送 HELLO: %dHz / %d声道 / Opus / 帧长 %d / %d bps",
                    addr_text, self.cfg["sample_rate"], self.cfg["channels"],
                    self.cfg["frame_size"], self.cfg["bitrate"])

        capture.start()
        last_ping = time.monotonic()
        ping_interval = float(self.cfg.get("ping_interval_sec", 1.5))

        try:
            while not self.stop_event.is_set():
                with self.state._lock:
                    pending = self.state.pending_device
                    gain = self.state.gain

                if pending is not None:
                    logger.info("切换采集设备: %s", pending)
                    break

                pcm = capture.read(timeout=1.0)
                if pcm is None:
                    if time.monotonic() - last_ping >= ping_interval:
                        link.send_all(protocol.pack_ping())
                        last_ping = time.monotonic()
                    continue

                if gain != 1.0:
                    pcm = self._apply_gain(pcm, gain)

                opus_pkt = self._encoder.encode(pcm)
                link.send_all(protocol.pack_audio(opus_pkt))
                self.state.add_stats(len(opus_pkt))

                if time.monotonic() - last_ping >= ping_interval:
                    link.send_all(protocol.pack_ping())
                    last_ping = time.monotonic()
        finally:
            capture.stop()
            with self.state._lock:
                self.state.dropped_blocks += capture._dropped

    @staticmethod
    def _apply_gain(pcm: bytes, gain: float) -> bytes:
        arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        arr *= gain
        np.clip(arr, -32768, 32767, out=arr)
        return arr.astype(np.int16).tobytes()

    def _send_bye(self, link: _Link) -> None:
        try:
            link.send_all(protocol.pack_bye())
        except Exception:
            pass

    def _cleanup(self) -> None:
        self.state.set_status(STOPPING)
        if self._responder is not None:
            self._responder.stop()
        if self._server is not None:
            self._server.close()
        if self._encoder is not None:
            self._encoder.close()
        logger.info("Worker 已退出。")
