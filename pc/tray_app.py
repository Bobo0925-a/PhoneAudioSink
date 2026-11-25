# -*- coding: utf-8 -*-
"""
PC 端托盘入口：后台采集推流，状态显示在 Windows 通知区域（系统托盘）。

运行::

    python tray_app.py

打包为 exe 后双击运行，托盘图标即为本程序；右键打开菜单。
"""

import logging
import os
import sys
import threading
import time

import pystray
from PIL import Image, ImageDraw

from app_core import (
    AppState,
    Worker,
    app_dir,
    list_input_devices,
    load_config,
    save_config,
)

# ---- 状态颜色（底图） ----
_STATUS_COLOR = {
    "idle": (110, 118, 130),
    "connected": (38, 166, 74),
    "error": (209, 62, 62),
    "stopping": (196, 148, 32),
}

LOG_PATH = os.path.join(app_dir(), "phone_audio.log")


def _setup_logging(state: AppState) -> None:
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # 文件日志（排障用）
    try:
        fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        pass

    # 内存日志（托盘菜单查看）
    from app_core import _LogHandler
    mh = _LogHandler(state.log_lines)
    mh.setFormatter(fmt)
    root.addHandler(mh)


def _make_icon(status: str) -> Image.Image:
    """按状态程序化绘制 64x64 托盘图标（彩色底 + 白色喇叭）。"""
    color = _STATUS_COLOR.get(status, _STATUS_COLOR["idle"])
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    d.ellipse((4, 4, 60, 60), fill=color)

    # 喇叭箱体
    d.polygon([(18, 26), (27, 26), (37, 17), (37, 47), (27, 38), (18, 38)],
              fill="white")

    if status == "error":
        # 红底白叉
        d.line((42, 22, 52, 32), fill="white", width=4)
        d.line((52, 22, 42, 32), fill="white", width=4)
    else:
        # 声波弧线
        waves = 2 if status == "connected" else 1
        for i in range(waves):
            x = 42 + i * 6
            d.arc((x - 4, 22, x + 8, 42), start=-55, end=55, fill="white", width=3)

    return img


def _human_size(n: int) -> str:
    if n >= 1 << 20:
        return f"{n / (1 << 20):.1f} MB"
    if n >= 1 << 10:
        return f"{n / (1 << 10):.1f} KB"
    return f"{n} B"


def main() -> None:
    cfg = load_config()
    state = AppState(cfg)
    stop_event = threading.Event()
    _setup_logging(state)

    worker = Worker(cfg, state, stop_event)
    worker.start()

    # 设备列表缓存（避免每秒重查音频子系统）
    dev_cache = {"at": 0.0, "items": []}

    def get_devices():
        if time.monotonic() - dev_cache["at"] > 10:
            try:
                dev_cache["items"] = list_input_devices()
            except Exception as exc:  # 音频子系统不可用时保留旧缓存
                logging.getLogger("tray").warning("枚举音频设备失败: %s", exc)
            dev_cache["at"] = time.monotonic()
        return dev_cache["items"]

    def current_device() -> str:
        return state.snapshot()["device_name"]

    def build_menu() -> pystray.Menu:
        snap = state.snapshot()

        status_item = pystray.MenuItem(
            f"状态：{snap['status_text']}", None, enabled=False)
        ip_item = pystray.MenuItem(
            f"本机 IP：{snap['local_ip']}", None, enabled=False)
        client_item = pystray.MenuItem(
            f"手机：{snap['client_addr'] or '未连接'}", None, enabled=False)
        stat_item = pystray.MenuItem(
            f"已发送：{snap['frames_sent']} 帧 / {_human_size(snap['bytes_sent'])}",
            None, enabled=False)

        # 采集设备子菜单（用闭包工厂捕获设备名；pystray 回调只接受 0/1/2 个无默认形参）
        dev_items = []
        cur = snap["device_name"]

        def _on_select(n: str):
            def _cb(icon, item):
                _select_device(n)
            return _cb

        def _is_current(n: str):
            def _cb(item):
                return n == cur or cur in n or n in cur
            return _cb

        dev_items.append(pystray.MenuItem(
            "默认设备",
            _on_select(""),
            checked=lambda item: cur == "默认设备",
            radio=True,
        ))
        for _idx, name in get_devices():
            dev_items.append(pystray.MenuItem(
                name,
                _on_select(name),
                checked=_is_current(name),
                radio=True,
            ))
        device_menu = pystray.MenuItem("采集设备", pystray.Menu(*dev_items))

        open_log = pystray.MenuItem("打开日志文件", _open_log)
        quit_item = pystray.MenuItem("退出", _on_quit)

        return pystray.Menu(
            status_item, ip_item, client_item, stat_item,
            pystray.Menu.SEPARATOR, device_menu,
            open_log, pystray.Menu.SEPARATOR, quit_item,
        )

    def _select_device(name: str) -> None:
        cfg["input_device"] = name
        save_config(cfg)
        state.request_device(name)
        logging.getLogger("tray").info("采集设备切换为: %s", name or "默认设备")

    def _open_log(icon, item) -> None:
        try:
            os.startfile(LOG_PATH)  # type: ignore[attr-defined]
        except OSError as exc:
            logging.getLogger("tray").warning("打开日志失败: %s", exc)

    def _on_quit(icon, item) -> None:
        stop_event.set()
        worker.join(timeout=3.0)
        icon.stop()

    icon = pystray.Icon(
        "PhoneAudioSink",
        _make_icon(state.snapshot()["status"]),
        "PC → 手机音频",
        build_menu(),
    )

    # 后台刷新托盘文案 / 图标 / 菜单
    def refresher() -> None:
        last_status = None
        while not stop_event.is_set():
            snap = state.snapshot()
            icon.title = (
                f"PC → 手机音频\n"
                f"状态：{snap['status_text']}\n"
                f"本机 IP：{snap['local_ip']}\n"
                f"手机：{snap['client_addr'] or '未连接'}"
            )
            if snap["status"] != last_status:
                icon.icon = _make_icon(snap["status"])
                last_status = snap["status"]
            icon.menu = build_menu()
            icon.update_menu()
            time.sleep(1.0)

    threading.Thread(target=refresher, daemon=True).start()

    # 阻塞在托盘消息循环（主线程）
    icon.run()


if __name__ == "__main__":
    main()
