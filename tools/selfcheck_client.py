# -*- coding: utf-8 -*-
"""
自检脚本：在本机起一个假"手机"服务端，让 PC 端以 connect 模式推流，
统计收到的帧类型，验证 直连模式 + HELLO/PING/AUDIO 通路是否正常。

用法：python tools/selfcheck_client.py
"""

import collections
import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pc"))

import app_core  # noqa: E402
import protocol  # noqa: E402

PORT = 42199
RUN_SECONDS = 6
MSG_HELLO, MSG_AUDIO, MSG_PING = 0x01, 0x02, 0x03

counts = collections.Counter()
first_audio_len = 0
done = threading.Event()


def fake_phone() -> None:
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", PORT))
    srv.listen(1)
    try:
        conn, _ = srv.accept()
    except OSError:
        return
    conn.settimeout(2.0)
    deadline = time.monotonic() + RUN_SECONDS
    buf = b""
    try:
        while time.monotonic() < deadline:
            try:
                chunk = conn.recv(8192)
            except socket.timeout:
                continue
            if not chunk:
                break
            buf += chunk
            while len(buf) >= 6:
                if buf[0] != 0xAA or buf[1] != 0x55:
                    buf = buf[1:]
                    continue
                ftype = buf[3]
                length = int.from_bytes(buf[4:6], "big")
                if len(buf) < 6 + length:
                    break
                payload = buf[6:6 + length]
                buf = buf[6 + length:]
                counts[ftype] += 1
                if ftype == MSG_AUDIO:
                    global first_audio_len
                    if first_audio_len == 0:
                        first_audio_len = len(payload)
    finally:
        conn.close()
        srv.close()
        done.set()


def main() -> int:
    thread = threading.Thread(target=fake_phone, daemon=True)
    thread.start()
    time.sleep(0.3)

    cfg = dict(app_core.DEFAULT_CONFIG)
    cfg["tcp_port"] = PORT
    cfg["ping_interval_sec"] = 1.0
    state = app_core.AppState(cfg)
    stop = threading.Event()
    worker = app_core.Worker(cfg, state, stop, mode="connect", host="127.0.0.1")
    worker.start()

    time.sleep(RUN_SECONDS)
    stop.set()
    worker.join(timeout=3)
    done.wait(timeout=3)

    names = {
        MSG_HELLO: "HELLO",
        MSG_AUDIO: "AUDIO",
        MSG_PING: "PING",
    }
    print("connect 模式收到帧：")
    for t, n in sorted(counts.items()):
        print(f"  {names.get(t, t)} = {n}")
    print(f"首帧 Opus 负载 {first_audio_len} 字节")
    print("状态快照：", {k: state.snapshot()[k] for k in ("status", "client_addr", "frames_sent")})

    ok = counts[MSG_HELLO] >= 1 and counts[MSG_AUDIO] > 10
    print("结论：", "直连通路正常" if ok else "直连通路异常")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
