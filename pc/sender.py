# -*- coding: utf-8 -*-
"""
PC 端命令行入口：抓取系统声音 → Opus 编码 → 经 TCP 推送到 Android 手机。

需要图形托盘时请运行 ``tray_app.py``；本入口适合无界面环境或调试。

用法
----
列出音频设备::

    python sender.py --list-devices

按配置文件运行::

    python sender.py --config config.json
"""

import argparse
import logging
import signal
import sys
import threading

from app_core import AppState, Worker, list_input_devices, load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="PC → 手机 WiFi 音频发送端（命令行）")
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--list-devices", action="store_true", help="列出音频设备后退出")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.list_devices:
        for idx, name in list_input_devices():
            print(f"{idx:3d}  {name}")
        return

    cfg = load_config(args.config)
    state = AppState(cfg)
    stop_event = threading.Event()

    def _on_signal(signum, frame):
        logging.getLogger("sender").info("收到退出信号，正在停止 ...")
        stop_event.set()

    signal.signal(signal.SIGINT, _on_signal)
    try:
        signal.signal(signal.SIGTERM, _on_signal)
    except (AttributeError, ValueError):
        pass

    worker = Worker(cfg, state, stop_event)
    worker.start()

    try:
        while worker.is_alive() and not stop_event.is_set():
            worker.join(timeout=0.5)
    finally:
        stop_event.set()
        worker.join(timeout=3.0)

    logging.getLogger("sender").info("已退出。")


if __name__ == "__main__":
    sys.exit(main())
