# -*- coding: utf-8 -*-
"""
PC 端主程序（Windows UI 3 风格）：无边框大圆角窗口 + 汉堡侧边栏 + 系统托盘。

- 侧边栏：连接面板（手动输入手机 IP / 等手机连入）、音量、采集设备、日志、设置
- 托盘：显示窗口、音量、连接/断开、退出
- 关闭窗口默认隐藏到托盘，不退出进程
"""

import logging
import math
import os
import re
import sys
import threading
import time

from PyQt5.QtCore import (
    QByteArray, QEasingCurve, QObject, QPoint, QPropertyAnimation, QRectF, Qt, QTimer,
    QSize, QVariantAnimation,
)
from PyQt5.QtGui import (
    QColor, QFont, QGuiApplication, QIcon, QPainter, QPainterPath, QPixmap,
)
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (
    QAction, QApplication, QCheckBox, QComboBox, QFrame, QGraphicsOpacityEffect,
    QHBoxLayout, QLabel, QLineEdit, QMenu, QPlainTextEdit, QProgressBar, QPushButton,
    QSizeGrip, QSlider, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
    QWidgetAction,
)

from app_core import (
    AppState, Worker, app_dir, list_input_devices, load_config, save_config,
)

# ---------------- 配色 ----------------
BG = "#101317"
SURFACE = "#181C23"
SURFACE2 = "#1F242E"
SURFACE3 = "#272D39"
ACCENT = "#4C8DFF"
TEXT = "#E9EEF7"
TEXT_DIM = "#98A3B5"
DIVIDER = "#2A3140"
OK = "#35C27A"
WARN = "#E8A33D"
ERR = "#E5544B"

LOG_PATH = os.path.join(app_dir(), "phone_audio.log")

IPV4 = re.compile(
    r"^((25[0-5]|2[0-4]\d|1\d\d|\d\d|\d)\.){3}(25[0-5]|2[0-4]\d|1\d\d|\d\d|\d)$"
)

# ---------------- SVG 图标 ----------------
SVG_HAMBURGER = (
    '<svg viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" '
    'stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>'
)
SVG_LINK = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M9 3v4M15 3v4M6 7h12v4a6 6 0 0 1-6 6 6 6 0 0 1-6-6V7zM12 17v4"/></svg>'
)
SVG_VOLUME = (
    '<svg viewBox="0 0 24 24" fill="currentColor">'
    '<path d="M4 9h3.4L12 5v14l-4.6-4H4z"/>'
    '<path d="M15.2 8.4a5 5 0 0 1 0 7.2" fill="none" stroke="currentColor" '
    'stroke-width="1.7" stroke-linecap="round"/></svg>'
)
SVG_MIC = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
    'stroke-linecap="round"><path d="M12 3.4a2.8 2.8 0 0 0-2.8 2.8v5a2.8 2.8 0 0 0 5.6 0V6.2'
    'A2.8 2.8 0 0 0 12 3.4z"/><path d="M5.5 11.2a6.5 6.5 0 0 0 13 0M12 17.7v3"/></svg>'
)
SVG_LOG = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
    'stroke-linecap="round"><path d="M5 5.5h14M5 12h14M5 18.5h9"/></svg>'
)
SVG_GEAR = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
    'stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/>'
    '<circle cx="9" cy="7" r="2" fill="currentColor" stroke="none"/>'
    '<circle cx="15" cy="12" r="2" fill="currentColor" stroke="none"/>'
    '<circle cx="8" cy="17" r="2" fill="currentColor" stroke="none"/></svg>'
)
SVG_CLOSE = (
    '<svg viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.9" '
    'stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>'
)
SVG_MIN = (
    '<svg viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.9" '
    'stroke-linecap="round"><path d="M5 12h14"/></svg>'
)
SVG_APP = (
    '<svg viewBox="0 0 64 64"><circle cx="32" cy="32" r="30" fill="#35C27A"/>'
    '<path d="M18 27h9l10-8v26l-10-8h-9z" fill="#FFFFFF"/>'
    '<path d="M42 24a10 10 0 0 1 0 16" fill="none" stroke="#FFFFFF" stroke-width="3" '
    'stroke-linecap="round"/></svg>'
)

# 全局动效开关：由 MainWindow 根据设置同步，供按钮子类读取
MOTION_ON = True


def motion_enabled() -> bool:
    return MOTION_ON


logger = logging.getLogger("ui.anim")


# ---------------- 帧时钟（跟随显示器刷新率） ----------------
# Qt 默认动画定时器约 16ms（≈60fps），在 120/144Hz 屏上点按动效会"跳帧"。
# 这里用 QTimer(PreciseTimer) 按刷新率出帧，所有时长仍按毫秒计算，帧率只影响采样密度。

_FRAME_MS: int | None = None


def display_refresh_hz() -> float:
    screen = QGuiApplication.primaryScreen()
    hz = float(screen.refreshRate()) if screen is not None else 60.0
    if not (30.0 <= hz <= 500.0):
        hz = 60.0
    return hz


def frame_interval_ms() -> int:
    """一帧的毫秒数：120Hz → 8ms，144Hz → 7ms，60Hz → 16ms。"""
    global _FRAME_MS
    if _FRAME_MS is None:
        _FRAME_MS = max(4, int(round(1000.0 / display_refresh_hz())))
    return _FRAME_MS


class _FrameTicker(QObject):
    """单一定时器驱动所有点按动效，避免每个按钮各起一个定时器。"""

    def __init__(self) -> None:
        super().__init__()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(frame_interval_ms())
        self._timer.timeout.connect(self._tick)
        self._jobs: list[dict] = []

    def run(self, duration_ms: int, curve, on_frame, on_done=None):
        # 允许直接传 QEasingCurve.OutCubic 这类枚举值，统一转成曲线对象
        easing = curve if isinstance(curve, QEasingCurve) else QEasingCurve(curve)
        job = {
            "t0": time.perf_counter(),
            "dur": max(1.0, float(duration_ms)),
            "curve": easing,
            "frame": on_frame,
            "done": on_done,
        }
        self._jobs.append(job)
        if not self._timer.isActive():
            self._timer.start()
        return job

    def cancel(self, job) -> None:
        if job in self._jobs:
            self._jobs.remove(job)
        if not self._jobs:
            self._timer.stop()

    def _tick(self) -> None:
        now = time.perf_counter()
        for job in list(self._jobs):
            progress = (now - job["t0"]) * 1000.0 / job["dur"]
            progress = 1.0 if progress >= 1.0 else progress
            try:
                job["frame"](job["curve"].valueForProgress(progress))
            except RuntimeError:  # 控件已被销毁
                self._jobs.remove(job)
                continue
            except Exception:  # 单帧出错不该拖垮整个界面
                logger.exception("帧回调异常")
                self._jobs.remove(job)
                continue
            if progress >= 1.0:
                self._jobs.remove(job)
                if job["done"] is not None:
                    try:
                        job["done"]()
                    except Exception:
                        logger.exception("动效结束回调异常")
        if not self._jobs:
            self._timer.stop()


_TICKER: _FrameTicker | None = None


def ticker() -> _FrameTicker:
    global _TICKER
    if _TICKER is None:
        _TICKER = _FrameTicker()
    return _TICKER


class RippleButton(QPushButton):
    """带点击动效的按钮：水波纹扩散 + 130ms 按压内缩回弹，可被"减弱动态效果"关闭。"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._ripple_center = QPoint(0, 0)
        self._ripple_radius = 0.0
        self._ripple_alpha = 0
        self._ripple_job = None
        self._press_job = None

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton and motion_enabled():
            self._start_ripple(event.pos())
            self._press_in()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if motion_enabled():
            self._press_out()

    def _press_amount(self) -> int:
        return 2 if self.height() < 44 else 3

    def _press_in(self) -> None:
        amount = self._press_amount()
        self._animate_press(amount, 110, QEasingCurve.OutCubic)

    def _press_out(self) -> None:
        self._animate_press(0, 170, QEasingCurve.OutBack)

    def _animate_press(self, target: int, duration: int, curve) -> None:
        start = self.contentsMargins().left()
        if self._press_job is not None:
            ticker().cancel(self._press_job)
            self._press_job = None

        def on_frame(eased: float) -> None:
            offset = int(round(start + (target - start) * eased))
            if self.contentsMargins().left() != offset:
                self.setContentsMargins(offset, offset, offset, offset)

        def on_done() -> None:
            self._press_job = None

        self._press_job = ticker().run(duration, curve, on_frame, on_done)

    def _start_ripple(self, pos: QPoint) -> None:
        self._ripple_center = pos
        max_r = max(
            math.hypot(pos.x(), pos.y()),
            math.hypot(self.width() - pos.x(), pos.y()),
            math.hypot(pos.x(), self.height() - pos.y()),
            math.hypot(self.width() - pos.x(), self.height() - pos.y()),
        )
        if self._ripple_job is not None:
            ticker().cancel(self._ripple_job)
            self._ripple_job = None
        self._ripple_alpha = 92
        self._ripple_radius = 0.0

        def on_frame(eased: float) -> None:
            self._ripple_radius = max_r * eased
            self._ripple_alpha = int(92 * (1.0 - eased))
            self.update()

        def on_done() -> None:
            self._ripple_job = None
            self._clear_ripple()

        self._ripple_job = ticker().run(320, QEasingCurve.OutCubic, on_frame, on_done)

    def _clear_ripple(self) -> None:
        self._ripple_radius = 0.0
        self._ripple_alpha = 0
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._ripple_alpha <= 0 or self._ripple_radius <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        clip = QPainterPath()
        radius = 12 if self.height() < 44 else 16
        clip.addRoundedRect(QRectF(self.rect()), radius, radius)
        painter.setClipPath(clip)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, self._ripple_alpha))
        painter.drawEllipse(self._ripple_center, int(self._ripple_radius),
                            int(self._ripple_radius))
        painter.end()


def svg_pixmap(svg: str, size: int, color: str = TEXT) -> QPixmap:
    data = QByteArray(svg.replace("currentColor", color).encode("utf-8"))
    renderer = QSvgRenderer(data)
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    return pix


def svg_icon(svg: str, size: int = 20, color: str = TEXT) -> QIcon:
    return QIcon(svg_pixmap(svg, size, color))


ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
_APP_ICON: QIcon | None = None


def asset_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "assets", name)


def app_icon() -> QIcon:
    """多尺寸应用图标：每个尺寸一张位图，系统按 DPI 选最合适的一档，避免放大发糊。"""
    global _APP_ICON
    if _APP_ICON is not None:
        return _APP_ICON
    icon = QIcon()
    for s in ICON_SIZES:
        path = asset_path(f"icon_{s}.png")
        if os.path.exists(path):
            icon.addFile(path, QSize(s, s))
    if icon.isNull():
        ico = asset_path("app.ico")
        if os.path.exists(ico):
            icon = QIcon(ico)
    if icon.isNull():
        icon = QIcon(svg_pixmap(SVG_APP, 64))
    _APP_ICON = icon
    return icon


# ---------------- 样式 ----------------
QSS = f"""
QWidget {{ color: {TEXT}; font-family: "Microsoft YaHei UI", "Segoe UI"; font-size: 13px; }}
QFrame#card {{ background: {SURFACE}; border-radius: 24px; }}
QFrame#sidebar {{ background: {SURFACE}; border-radius: 24px; }}
QPushButton#navBtn {{
    background: transparent; border: none; border-radius: 16px;
    text-align: left; padding: 10px 14px; color: {TEXT};
}}
QPushButton#navBtn:hover {{ background: {SURFACE2}; }}
QPushButton#navBtn:pressed {{ background: #2C3444; }}
QPushButton#navBtn:checked {{ background: {SURFACE3}; }}
QPushButton#primary {{
    background: {ACCENT}; border: none; border-radius: 16px;
    padding: 11px 18px; color: #FFFFFF; font-weight: 600;
}}
QPushButton#primary:hover {{ background: #5A98FF; }}
QPushButton#primary:pressed {{ background: #3D7BE6; }}
QPushButton#primary:disabled {{ background: #33415C; color: #93A1B8; }}
QPushButton#ghost {{
    background: {SURFACE2}; border: 1px solid {DIVIDER}; border-radius: 16px;
    padding: 11px 18px; color: {TEXT};
}}
QPushButton#ghost:hover {{ background: {SURFACE3}; }}
QPushButton#ghost:pressed {{ background: #333B4A; }}
QPushButton#ghost:checked {{
    background: {SURFACE3}; border: 1px solid {ACCENT}; color: {TEXT};
}}
QPushButton#winBtn {{
    background: transparent; border: none; border-radius: 12px;
}}
QPushButton#winBtn:hover {{ background: {SURFACE2}; }}
QPushButton#winBtn:pressed {{ background: {SURFACE3}; }}
QLineEdit {{
    background: {SURFACE2}; border: 1px solid {DIVIDER}; border-radius: 16px;
    padding: 10px 14px; selection-background-color: {ACCENT};
}}
QComboBox {{
    background: {SURFACE2}; border: 1px solid {DIVIDER}; border-radius: 16px;
    padding: 9px 14px;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE2}; border: 1px solid {DIVIDER}; border-radius: 12px;
    selection-background-color: {SURFACE3}; outline: none;
}}
QSlider::groove:horizontal {{
    height: 6px; background: {SURFACE3}; border-radius: 3px;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}
QSlider::handle:horizontal {{
    width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; background: #FFFFFF;
}}
QPlainTextEdit {{
    background: {SURFACE2}; border: 1px solid {DIVIDER}; border-radius: 16px;
    padding: 10px; font-family: Consolas, "Microsoft YaHei UI"; font-size: 12px;
    color: {TEXT_DIM};
}}
QProgressBar#connectBar {{
    background: {SURFACE3}; border: none; border-radius: 4px;
    max-height: 6px; min-height: 6px;
}}
QProgressBar#connectBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QMenu {{ background: {SURFACE2}; border: 1px solid {DIVIDER}; border-radius: 12px; padding: 6px; }}
QMenu::item {{ padding: 7px 22px; border-radius: 8px; }}
QMenu::item:selected {{ background: {SURFACE3}; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 18px; height: 18px; border-radius: 6px;
    border: 1px solid {DIVIDER}; background: {SURFACE2};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; }}
"""


class TitleBar(QWidget):
    """自绘标题栏，支持拖动移动窗口。"""

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self._win = window
        self._drag_pos: QPoint | None = None
        self.setFixedHeight(52)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 0, 10, 0)
        row.setSpacing(8)

        self.btn_menu = RippleButton()
        self.btn_menu.setObjectName("winBtn")
        self.btn_menu.setIcon(svg_icon(SVG_HAMBURGER, 20))
        self.btn_menu.setFixedSize(34, 34)
        self.btn_menu.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.btn_menu)

        title = QLabel("PhoneAudioSink")
        title.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT};")
        row.addWidget(title)
        row.addStretch(1)

        self.btn_min = RippleButton()
        self.btn_min.setObjectName("winBtn")
        self.btn_min.setIcon(svg_icon(SVG_MIN, 18, TEXT_DIM))
        self.btn_min.setFixedSize(32, 32)
        self.btn_min.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.btn_min)

        self.btn_close = RippleButton()
        self.btn_close.setObjectName("winBtn")
        self.btn_close.setIcon(svg_icon(SVG_CLOSE, 18, TEXT_DIM))
        self.btn_close.setFixedSize(32, 32)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.btn_close)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self._win.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self._win.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.cfg = load_config()
        self._sync_motion_flag()
        self.state = AppState(self.cfg)
        self.stop_event: threading.Event | None = None
        self.worker: Worker | None = None
        self._anims: list[QPropertyAnimation] = []
        self._hint = ""

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(880, 600)
        self.resize(940, 640)
        self.setWindowTitle("PhoneAudioSink")
        self.setWindowIcon(app_icon())

        self._build_ui()
        self._build_tray()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(500)

        self._auto_start()

    # ---------------- 界面 ----------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.title_bar = TitleBar(self)
        outer.addWidget(self.title_bar)

        body = QHBoxLayout()
        body.setContentsMargins(14, 0, 14, 14)
        body.setSpacing(12)
        outer.addLayout(body, 1)

        # ---- 侧边栏 ----
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(212)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(12, 14, 12, 14)
        side.setSpacing(6)

        self.nav_buttons: list[QPushButton] = []
        for idx, (icon, label) in enumerate(
            [(SVG_LINK, "连接"), (SVG_VOLUME, "音量"), (SVG_MIC, "采集设备"),
             (SVG_LOG, "日志"), (SVG_GEAR, "设置")]
        ):
            btn = RippleButton(label)
            btn.setObjectName("navBtn")
            btn.setIcon(svg_icon(icon, 18))
            btn.setIconSize(QSize(18, 18))
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(42)
            btn.clicked.connect(lambda _=False, i=idx: self._switch_page(i))
            side.addWidget(btn)
            self.nav_buttons.append(btn)

        side.addSpacing(14)

        vol_title = QLabel("音量")
        vol_title.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px; padding-left: 4px;")
        side.addWidget(vol_title)

        vol_row = QHBoxLayout()
        vol_row.setContentsMargins(4, 0, 4, 0)
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 150)
        self.vol_slider.setValue(int(float(self.cfg.get("volume", 1.0)) * 100))
        self.vol_slider.valueChanged.connect(self._on_volume)
        vol_row.addWidget(self.vol_slider)
        self.vol_label = QLabel(f"{self.vol_slider.value()}%")
        self.vol_label.setFixedWidth(44)
        self.vol_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        vol_row.addWidget(self.vol_label)
        side.addLayout(vol_row)

        side.addStretch(1)

        self.mode_hint = QLabel("模式：等待手机连入")
        self.mode_hint.setWordWrap(True)
        self.mode_hint.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px; padding: 6px 4px;")
        side.addWidget(self.mode_hint)

        body.addWidget(self.sidebar)

        # ---- 内容区 ----
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        self.stack.addWidget(self._page_connect())
        self.stack.addWidget(self._page_volume())
        self.stack.addWidget(self._page_capture())
        self.stack.addWidget(self._page_log())
        self.stack.addWidget(self._page_settings())

        # 尺寸手柄（无边框窗口也能拉伸）
        grip_layer = QHBoxLayout()
        grip_layer.addStretch(1)
        grip = QSizeGrip(self)
        grip.setFixedSize(18, 18)
        grip_layer.addWidget(grip, 0, Qt.AlignRight | Qt.AlignBottom)
        outer.addLayout(grip_layer)

        self._switch_page(0)
        self.title_bar.btn_menu.clicked.connect(self._toggle_sidebar)
        self.title_bar.btn_close.clicked.connect(self.hide)
        self.title_bar.btn_min.clicked.connect(self.showMinimized)

    @staticmethod
    def _card() -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("card")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(10)
        return frame, lay

    @staticmethod
    def _title(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {TEXT};")
        return label

    @staticmethod
    def _dim(text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        return label

    def _page_connect(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        card, cl = self._card()
        self.lbl_status = QLabel("等待连接")
        self.lbl_status.setStyleSheet(f"font-size: 26px; font-weight: 700; color: {TEXT};")
        cl.addWidget(self.lbl_status)

        self.lbl_detail = self._dim("尚未开始推送")
        cl.addWidget(self.lbl_detail)

        self.lbl_ip = self._dim(f"本机 IP　{self.state.local_ip}")
        cl.addWidget(self.lbl_ip)

        self.lbl_stats = self._dim("已发送 0 帧")
        cl.addWidget(self.lbl_stats)

        self.connect_bar = QProgressBar()
        self.connect_bar.setObjectName("connectBar")
        self.connect_bar.setRange(0, 0)
        self.connect_bar.setTextVisible(False)
        self.connect_bar.setVisible(False)
        cl.addWidget(self.connect_bar)
        lay.addWidget(card)

        card2, cl2 = self._card()
        cl2.addWidget(self._title("手动连接手机"))

        mode_row = QHBoxLayout()
        self.btn_mode_listen = RippleButton("等待手机连入")
        self.btn_mode_listen.setObjectName("ghost")
        self.btn_mode_listen.setCheckable(True)
        self.btn_mode_listen.setChecked(True)
        self.btn_mode_connect = RippleButton("直连手机")
        self.btn_mode_connect.setObjectName("ghost")
        self.btn_mode_connect.setCheckable(True)
        for b in (self.btn_mode_listen, self.btn_mode_connect):
            b.setCursor(Qt.PointingHandCursor)
            mode_row.addWidget(b)
        cl2.addLayout(mode_row)
        self.btn_mode_listen.clicked.connect(lambda: self._choose_mode("listen"))
        self.btn_mode_connect.clicked.connect(lambda: self._choose_mode("connect"))

        ip_row = QHBoxLayout()
        self.edit_ip = QLineEdit()
        self.edit_ip.setPlaceholderText("手机 IP，如 192.168.1.15")
        self.edit_ip.setText(str(self.cfg.get("last_phone_ip", "")))
        ip_row.addWidget(self.edit_ip, 1)
        self.btn_start = RippleButton("开始")
        self.btn_start.setObjectName("primary")
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.clicked.connect(self._toggle_engine)
        ip_row.addWidget(self.btn_start)
        cl2.addLayout(ip_row)

        cl2.addWidget(self._dim("手机端需处于监听接收状态，并保证同一局域网"))
        lay.addWidget(card2)
        lay.addStretch(1)
        return page

    def _page_volume(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)

        card, cl = self._card()
        cl.addWidget(self._title("推送音量"))
        big = QLabel("100%")
        big.setStyleSheet(f"font-size: 44px; font-weight: 700; color: {ACCENT};")
        cl.addWidget(big)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 150)
        slider.setValue(int(float(self.cfg.get("volume", 1.0)) * 100))
        slider.valueChanged.connect(self._on_volume)
        cl.addWidget(slider)
        cl.addWidget(self._dim("作用于推送音频增益，0 为静音；超过 100% 会被软限幅保护"))
        self.big_volume_label = big
        self.page_volume_slider = slider
        lay.addWidget(card)
        lay.addStretch(1)
        return page

    def _page_capture(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)

        card, cl = self._card()
        cl.addWidget(self._title("采集来源"))
        self.combo_device = QComboBox()
        self.combo_device.currentIndexChanged.connect(self._on_device_changed)
        cl.addWidget(self.combo_device)

        row = QHBoxLayout()
        btn_refresh = RippleButton("刷新设备")
        btn_refresh.setObjectName("ghost")
        btn_refresh.setCursor(Qt.PointingHandCursor)
        btn_refresh.clicked.connect(self._reload_devices)
        row.addWidget(btn_refresh)
        row.addStretch(1)
        cl.addLayout(row)

        cl.addWidget(self._dim("推荐选择虚拟声卡的录制端（如 Virtual Audio Cable、VoiceMeeter），"
                               "并把 Windows 播放输出指向该虚拟声卡"))
        cl.addWidget(self._dim("格式　48000 Hz / 立体声 / Opus 20ms 帧 / 64 kbps"))
        lay.addWidget(card)
        lay.addStretch(1)
        self._reload_devices()
        return page

    def _page_log(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)

        card, cl = self._card()
        cl.addWidget(self._title("运行日志"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(420)
        cl.addWidget(self.log_view)
        lay.addWidget(card)
        return page

    def _page_settings(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)

        card, cl = self._card()
        cl.addWidget(self._title("启动与托盘"))
        self.chk_show = QCheckBox("启动时显示主窗口")
        self.chk_show.setChecked(bool(self.cfg.get("show_window_on_start", True)))
        self.chk_show.stateChanged.connect(self._save_settings)
        cl.addWidget(self.chk_show)
        cl.addWidget(self._dim("关闭窗口时隐藏到托盘，程序继续推送；从托盘菜单可退出"))

        self.chk_motion = QCheckBox("减弱动态效果")
        self.chk_motion.setChecked(bool(self.cfg.get("reduce_motion", False)))
        self.chk_motion.stateChanged.connect(self._save_settings)
        cl.addWidget(self.chk_motion)
        cl.addWidget(self._dim("关闭页面淡入与入场动画，仅保留即时按压反馈；"
                               "系统级「减少动画」开关同样生效"))
        lay.addWidget(card)

        card2, cl2 = self._card()
        cl2.addWidget(self._title("端口"))
        cl2.addWidget(self._dim(f"TCP 音频　{self.cfg.get('tcp_port', 42101)}"))
        cl2.addWidget(self._dim(f"UDP 发现　{self.cfg.get('discover_port', 42100)}"))
        cl2.addWidget(self._dim("首次运行需在防火墙弹窗中允许专用网络"))
        lay.addWidget(card2)
        lay.addStretch(1)
        return page

    # ---------------- 托盘 ----------------
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("PhoneAudioSink　等待连接")

        menu = QMenu()
        act_show = QAction("显示主窗口", menu)
        act_show.triggered.connect(self._show_window)
        menu.addAction(act_show)
        menu.addSeparator()

        vol_widget = QWidget()
        vlay = QVBoxLayout(vol_widget)
        vlay.setContentsMargins(16, 8, 16, 8)
        vlay.addWidget(QLabel("推送音量"))
        self.tray_slider = QSlider(Qt.Horizontal)
        self.tray_slider.setRange(0, 150)
        self.tray_slider.setValue(self.vol_slider.value())
        self.tray_slider.setFixedWidth(180)
        self.tray_slider.valueChanged.connect(self._on_volume)
        vlay.addWidget(self.tray_slider)
        vol_action = QWidgetAction(menu)
        vol_action.setDefaultWidget(vol_widget)
        menu.addAction(vol_action)
        menu.addSeparator()

        self.act_connect = QAction("开始连接", menu)
        self.act_connect.triggered.connect(self._toggle_engine)
        menu.addAction(self.act_connect)

        act_exit = QAction("退出", menu)
        act_exit.triggered.connect(self._quit)
        menu.addAction(act_exit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        self.tray_menu = menu

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._show_window()

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ---------------- 逻辑 ----------------
    def _switch_page(self, index: int) -> None:
        page = self.stack.widget(index)
        self.stack.setCurrentWidget(page)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        self._page_enter(page)

    # ---- 动效：页面淡入 + 卡片错峰入场 ----
    def _motion_on(self) -> bool:
        return not bool(self.cfg.get("reduce_motion", False))

    def _fade_in(self, widgets, stagger: int = 55, duration: int = 240) -> None:
        if not self._motion_on():
            return
        for i, widget in enumerate(widgets):
            if widget is None or not widget.isVisible():
                continue
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)
            anim = QPropertyAnimation(effect, b"opacity", self)
            anim.setDuration(duration)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.finished.connect(lambda w=widget: w.setGraphicsEffect(None))
            QTimer.singleShot(i * stagger, anim.start)
            self._anims.append(anim)
        if len(self._anims) > 60:
            self._anims = self._anims[-30:]

    def _page_enter(self, page: QWidget) -> None:
        layout = page.layout()
        if layout is None:
            return
        widgets = []
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item is not None and item.widget() is not None:
                widgets.append(item.widget())
        self._fade_in(widgets)

    def _shake(self, widget: QWidget) -> None:
        if not self._motion_on():
            return
        geo = widget.geometry()
        base = geo.topLeft()
        anim = QPropertyAnimation(widget, b"pos", self)
        anim.setDuration(320)
        for ratio, dx in ((0.0, 0), (0.2, -7), (0.4, 6), (0.6, -4), (0.8, 3), (1.0, 0)):
            anim.setKeyValueAt(ratio, base + QPoint(dx, 0))
        anim.start()
        self._anims.append(anim)

    def _set_ip_state(self, state: str) -> None:
        color = {"error": ERR, "ok": OK}.get(state, DIVIDER)
        self.edit_ip.setStyleSheet(
            "QLineEdit { background: %s; border: 1px solid %s; border-radius: 16px;"
            " padding: 10px 14px; }" % (SURFACE2, color)
        )
        if state != "normal":
            QTimer.singleShot(1600, lambda: self._set_ip_state("normal"))

    def _toggle_sidebar(self) -> None:
        self.sidebar.setVisible(not self.sidebar.isVisible())

    def _choose_mode(self, mode: str) -> None:
        self.btn_mode_listen.setChecked(mode == "listen")
        self.btn_mode_connect.setChecked(mode == "connect")
        self.mode_hint.setText(
            "模式：等待手机连入" if mode == "listen" else "模式：直连手机"
        )
        if mode == "connect":
            self.edit_ip.setFocus()

    def _on_volume(self, value: int) -> None:
        self.state.set_gain(value / 100.0)
        self.vol_slider.blockSignals(True)
        self.vol_slider.setValue(value)
        self.vol_slider.blockSignals(False)
        if hasattr(self, "tray_slider"):
            self.tray_slider.blockSignals(True)
            self.tray_slider.setValue(value)
            self.tray_slider.blockSignals(False)
        self.vol_label.setText(f"{value}%")
        if hasattr(self, "big_volume_label"):
            self.big_volume_label.setText(f"{value}%")
        self.cfg["volume"] = value / 100.0
        save_config(self.cfg)

    def _reload_devices(self) -> None:
        # 重建列表期间屏蔽信号，避免 clear()/addItem() 误触发保存、清掉已选设备
        self.combo_device.blockSignals(True)
        try:
            self.combo_device.clear()
            self.combo_device.addItem("默认设备", "")
            try:
                for _idx, name in list_input_devices():
                    self.combo_device.addItem(name, name)
            except Exception as exc:
                logging.getLogger("ui").warning("枚举音频设备失败: %s", exc)
            current = self.cfg.get("input_device") or ""
            pos = self.combo_device.findData(current)
            self.combo_device.setCurrentIndex(pos if pos >= 0 else 0)
        finally:
            self.combo_device.blockSignals(False)

    def _on_device_changed(self, _index: int) -> None:
        name = self.combo_device.currentData() or ""
        self.cfg["input_device"] = name
        save_config(self.cfg)
        self.state.request_device(name)

    def _toggle_engine(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            self._stop_engine()
        else:
            self._start_engine()

    def _start_engine(self) -> None:
        mode = "listen" if self.btn_mode_listen.isChecked() else "connect"
        host = self.edit_ip.text().strip()
        if mode == "connect":
            if not host:
                self._ip_error("请输入手机 IP 后再开始")
                return
            if not IPV4.match(host):
                self._ip_error("IP 格式不正确，示例 192.168.1.50")
                return
            self._set_ip_state("ok")
            self.cfg["last_phone_ip"] = host
            save_config(self.cfg)

        self.stop_event = threading.Event()
        self.worker = Worker(self.cfg, self.state, self.stop_event, mode=mode, host=host)
        self.worker.start()
        self._hint = ""
        self.btn_start.setEnabled(True)
        self.btn_start.setText("停止")
        self.act_connect.setText("停止连接")
        self.lbl_detail.setText(
            "正在监听，等待手机连入" if mode == "listen" else f"正在连接 {host}"
        )

    def _ip_error(self, message: str) -> None:
        self._set_ip_state("error")
        self._shake(self.edit_ip)
        self._hint = message
        self.lbl_detail.setText(message)
        self.lbl_detail.setStyleSheet(f"color: {ERR}; font-size: 12px;")
        self.edit_ip.setFocus()
        QTimer.singleShot(
            1600, lambda: self.lbl_detail.setStyleSheet(
                f"color: {TEXT_DIM}; font-size: 12px;"
            )
        )

    def _stop_engine(self) -> None:
        if self.stop_event is None and self.worker is None:
            return
        if self.stop_event is not None:
            self.stop_event.set()
        self.btn_start.setEnabled(False)
        self.btn_start.setText("停止中")
        self._poll_stopped()

    def _poll_stopped(self) -> None:
        """非阻塞收尾：等线程真正退出后再恢复按钮，避免界面假死。"""
        if self.worker is not None and self.worker.is_alive():
            QTimer.singleShot(150, self._poll_stopped)
            return
        self.worker = None
        self.stop_event = None
        self.state.set_status("idle", client_addr="", last_error="")
        self.btn_start.setEnabled(True)
        self.btn_start.setText("开始")
        self.act_connect.setText("开始连接")
        self.lbl_status.setText("已停止")
        self.lbl_status.setStyleSheet(
            f"font-size: 26px; font-weight: 700; color: {TEXT_DIM};"
        )
        self.connect_bar.setVisible(False)

    def _auto_start(self) -> None:
        self._start_engine()

    def _refresh(self) -> None:
        snap = self.state.snapshot()
        status = snap["status"]

        # 未运行时固定显示"已停止"，避免状态机残留 STOPPING/旧对端信息
        if self.worker is None or not self.worker.is_alive():
            self.lbl_status.setText("已停止")
            self.lbl_status.setStyleSheet(
                f"font-size: 26px; font-weight: 700; color: {TEXT_DIM};"
            )
            self.lbl_detail.setText(self._hint or "点击开始重新推流")
            self.lbl_detail.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
            self._update_common(snap)
            return

        self.lbl_status.setText(snap["status_text"])
        self.lbl_status.setStyleSheet(
            "font-size: 26px; font-weight: 700; color: "
            f"{ {'connected': OK, 'error': ERR}.get(status, TEXT) };"
        )
        detail = snap["last_error"] if status == "error" and snap["last_error"] else ""
        peer = snap["client_addr"] or ("未连接" if status != "error" else "")
        self.lbl_detail.setText(detail or f"对端　{peer}")
        if detail:
            self.lbl_detail.setStyleSheet(f"color: {ERR}; font-size: 12px;")
        else:
            self.lbl_detail.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        self._update_common(snap)

        self.tray.setToolTip(f"PhoneAudioSink　{snap['status_text']}")

        # 连接中才显示进度条：给"正在拨号"一个可见的等待状态
        busy_connecting = snap["mode"] == "connect" and status != "connected"
        if self.connect_bar.isVisible() != busy_connecting:
            self.connect_bar.setVisible(busy_connecting)

        if self.stack.currentIndex() == 3:
            text = self.state.log_text()
            if text != self.log_view.toPlainText():
                self.log_view.setPlainText(text)
                self.log_view.verticalScrollBar().setValue(
                    self.log_view.verticalScrollBar().maximum()
                )

    def _update_common(self, snap: dict) -> None:
        self.lbl_ip.setText(f"本机 IP　{snap['local_ip']}　·　采集 {snap['device_name']}")
        size = snap["bytes_sent"]
        human = f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / 1048576:.1f} MB"
        self.lbl_stats.setText(
            f"已发送 {snap['frames_sent']} 帧 · {human} · 采集丢块 {snap['dropped_blocks']}"
        )

    def _save_settings(self) -> None:
        self.cfg["show_window_on_start"] = self.chk_show.isChecked()
        self.cfg["reduce_motion"] = self.chk_motion.isChecked()
        save_config(self.cfg)
        self._sync_motion_flag()

    def _sync_motion_flag(self) -> None:
        global MOTION_ON
        MOTION_ON = not bool(self.cfg.get("reduce_motion", False))

    def _quit(self) -> None:
        self._stop_engine()
        self.tray.hide()
        QApplication.quit()

    # ---------------- 绘制 ----------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 24, 24)
        painter.fillPath(path, QColor(BG))
        painter.end()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        if not self.cfg.get("_tray_hint_shown"):
            self.tray.showMessage("PhoneAudioSink", "已隐藏到托盘，程序继续推送音频")
            self.cfg["_tray_hint_shown"] = True
            save_config(self.cfg)


def _setup_logging() -> None:
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    try:
        fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        pass
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)


def main() -> int:
    _setup_logging()
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(QSS)

    window = MainWindow()
    if window.cfg.get("show_window_on_start", True):
        window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
