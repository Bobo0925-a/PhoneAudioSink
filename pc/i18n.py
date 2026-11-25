# -*- coding: utf-8 -*-
"""PC 端界面文案表与当前语言。

只依赖标准库，core 层和界面层都能安全导入。
语言代码存进 config.json 的 "language" 字段（zh / en）。
"""

import os

SUPPORTED = ("zh", "en")
LANGUAGE_NAMES = {"zh": "简体中文", "en": "English"}

_current = "zh"

STRINGS: dict[str, dict[str, str]] = {
    # ---- 通用 / 侧栏 ----
    "nav.connect": {"zh": "连接", "en": "Connect"},
    "nav.volume": {"zh": "音量", "en": "Volume"},
    "nav.capture": {"zh": "采集设备", "en": "Source"},
    "nav.log": {"zh": "日志", "en": "Log"},
    "nav.settings": {"zh": "设置", "en": "Settings"},
    "sidebar.volume": {"zh": "音量", "en": "Volume"},
    "mode.listen": {"zh": "模式：等待手机连入", "en": "Mode: waiting for phone"},
    "mode.connect": {"zh": "模式：直连手机", "en": "Mode: connecting to phone"},

    # ---- 运行状态 ----
    "status.idle": {"zh": "等待连接", "en": "Waiting"},
    "status.connected": {"zh": "正在推流", "en": "Streaming"},
    "status.error": {"zh": "连接异常", "en": "Connection error"},
    "status.stopping": {"zh": "正在停止", "en": "Stopping"},
    "status.stopped": {"zh": "已停止", "en": "Stopped"},

    # ---- 连接页 ----
    "detail.not_started": {"zh": "尚未开始推送", "en": "Not streaming yet"},
    "detail.click_start": {"zh": "点击开始重新推流", "en": "Press Start to stream again"},
    "detail.listening": {"zh": "正在监听，等待手机连入", "en": "Listening, waiting for the phone"},
    "detail.connecting": {"zh": "正在连接 {host}", "en": "Connecting to {host}"},
    "detail.peer": {"zh": "对端　{peer}", "en": "Peer  {peer}"},
    "detail.ip": {"zh": "本机 IP　{ip}", "en": "Local IP  {ip}"},
    "detail.ip_device": {
        "zh": "本机 IP　{ip}　·　采集 {device}",
        "en": "Local IP  {ip}  ·  Source {device}",
    },
    "detail.stats": {
        "zh": "已发送 {frames} 帧 · {size} · 采集丢块 {dropped}",
        "en": "Sent {frames} frames · {size} · Dropped {dropped}",
    },
    "peer.none": {"zh": "未连接", "en": "Not connected"},
    "connect.title": {"zh": "手动连接手机", "en": "Connect to the phone"},
    "btn.listen": {"zh": "等待手机连入", "en": "Wait for the phone"},
    "btn.connect": {"zh": "直连手机", "en": "Connect directly"},
    "placeholder.ip": {"zh": "手机 IP，如 192.168.1.15", "en": "Phone IP, e.g. 192.168.1.15"},
    "btn.start": {"zh": "开始", "en": "Start"},
    "btn.stop": {"zh": "停止", "en": "Stop"},
    "btn.stopping": {"zh": "停止中", "en": "Stopping"},
    "hint.listen": {
        "zh": "手机端需处于监听接收状态，并保证同一局域网",
        "en": "The phone must be listening on the same Wi-Fi network",
    },
    "err.ip_required": {"zh": "请输入手机 IP 后再开始", "en": "Enter the phone IP first"},
    "err.ip_invalid": {
        "zh": "IP 格式不正确，示例 192.168.1.50",
        "en": "Invalid IP format, e.g. 192.168.1.50",
    },

    # ---- 音量页 ----
    "volume.title": {"zh": "推送音量", "en": "Push volume"},
    "volume.desc": {
        "zh": "作用于推送音频增益，0 为静音；超过 100% 会被软限幅保护",
        "en": "Gain applied to the streamed audio; 0 mutes it, above 100% is soft-clipped",
    },

    # ---- 采集页 ----
    "capture.title": {"zh": "采集来源", "en": "Capture source"},
    "btn.refresh": {"zh": "刷新设备", "en": "Refresh devices"},
    "capture.tip1": {
        "zh": "推荐选择虚拟声卡的录制端（如 Virtual Audio Cable、VoiceMeeter），"
              "并把 Windows 播放输出指向该虚拟声卡",
        "en": "Pick the recording end of a virtual sound card (Virtual Audio Cable, VoiceMeeter, …), "
              "and point the Windows playback output at it",
    },
    "capture.tip2": {
        "zh": "格式　48000 Hz / 立体声 / Opus 20ms 帧 / 64 kbps",
        "en": "Format  48000 Hz / stereo / Opus 20 ms frames / 64 kbps",
    },
    "device.default": {"zh": "默认设备", "en": "Default device"},

    # ---- 日志页 ----
    "log.title": {"zh": "运行日志", "en": "Runtime log"},

    # ---- 设置页 ----
    "settings.startup": {"zh": "启动与托盘", "en": "Startup & tray"},
    "chk.show": {"zh": "启动时显示主窗口", "en": "Show the main window on start"},
    "chk.tray_desc": {
        "zh": "关闭窗口时隐藏到托盘，程序继续推送；从托盘菜单可退出",
        "en": "Closing the window hides it to the tray and keeps streaming; quit from the tray menu",
    },
    "chk.motion": {"zh": "减弱动态效果", "en": "Reduce motion"},
    "settings.motion_desc": {
        "zh": "关闭页面淡入与入场动画，仅保留即时按压反馈；"
              "系统级「减少动画」开关同样生效",
        "en": "Turn off page fades and entrance animations, keeping only instant press feedback; "
              "the system-level reduce-animation setting also applies",
    },
    "settings.language": {"zh": "界面语言", "en": "Language"},
    "lang.zh": {"zh": "简体中文", "en": "简体中文"},
    "lang.en": {"zh": "English", "en": "English"},
    "lang.hint": {"zh": "切换后界面立即生效", "en": "Applies immediately"},
    "ports.title": {"zh": "端口", "en": "Ports"},
    "ports.tcp": {"zh": "TCP 音频　{port}", "en": "TCP audio  {port}"},
    "ports.udp": {"zh": "UDP 发现　{port}", "en": "UDP discovery  {port}"},
    "ports.tip": {
        "zh": "首次运行需在防火墙弹窗中允许专用网络",
        "en": "Allow the private network in the firewall prompt on first run",
    },

    # ---- 托盘 ----
    "tray.show": {"zh": "显示主窗口", "en": "Show window"},
    "tray.volume": {"zh": "推送音量", "en": "Push volume"},
    "tray.start": {"zh": "开始连接", "en": "Start streaming"},
    "tray.stop": {"zh": "停止连接", "en": "Stop streaming"},
    "tray.exit": {"zh": "退出", "en": "Quit"},
    "tray.tip": {"zh": "PhoneAudioSink　{status}", "en": "PhoneAudioSink  {status}"},
    "tray.hidden_title": {"zh": "PhoneAudioSink", "en": "PhoneAudioSink"},
    "tray.hidden": {
        "zh": "已隐藏到托盘，程序继续推送音频",
        "en": "Minimized to the tray, audio keeps streaming",
    },

    # ---- 精简托盘入口（tray_app.py） ----
    "tray2.title": {"zh": "PC → 手机音频", "en": "PC → phone audio"},
    "tray2.status": {"zh": "状态：{status}", "en": "Status: {status}"},
    "tray2.ip": {"zh": "本机 IP：{ip}", "en": "Local IP: {ip}"},
    "tray2.phone": {"zh": "手机：{phone}", "en": "Phone: {phone}"},
    "tray2.sent": {"zh": "已发送：{frames} 帧 / {size}", "en": "Sent: {frames} frames / {size}"},
    "tray2.devices": {"zh": "采集设备", "en": "Source device"},
    "tray2.open_log": {"zh": "打开日志文件", "en": "Open log file"},
    "tray2.quit": {"zh": "退出", "en": "Quit"},
}


def normalize(code) -> str:
    """把任意写法收敛到受支持的语言代码，默认中文。"""
    if not code:
        return "zh"
    code = str(code).strip().lower().replace("_", "-")
    if code.startswith("zh"):
        return "zh"
    if code.startswith("en"):
        return "en"
    return "zh"


def system_language() -> str:
    """按系统区域猜一次语言（仅用于首次启动的默认值）。"""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            return normalize(value)
    try:
        import locale

        name = locale.getdefaultlocale()[0] or ""
        return normalize(name)
    except Exception:
        return "zh"


def set_language(code: str) -> str:
    global _current
    _current = normalize(code)
    return _current


def current_language() -> str:
    return _current


def t(key: str, **kwargs) -> str:
    """取当前语言文案；缺键时回退中文，再回退键名本身。"""
    entry = STRINGS.get(key)
    if not entry:
        return key
    text = entry.get(_current) or entry.get("zh") or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text
