# -*- coding: utf-8 -*-
"""
系统音频采集（Windows WASAPI / PortAudio loopback）。

说明
----
- 推荐采集来源（任选其一，在 config 的 ``input_device`` 里填设备名关键字或索引）：
  1. 声卡自带的 "Stereo Mix / 立体声混音" 输入设备；
  2. 虚拟声卡（如 VB-Cable）的输入端：把系统播放输出设到虚拟声卡，再从它的输入采集；
  3. 若选普通麦克风，则传出的是麦克风声音而非系统声音。

采集格式与手机端 AudioTrack 由 HELLO 帧协商保持一致。
"""

import queue
import logging

import numpy as np
import sounddevice as sd

logger = logging.getLogger("capture")


def list_devices() -> None:
    """打印所有音频设备及默认设备，方便挑选采集来源。"""
    print(sd.query_devices())
    print("\n默认输入设备:", sd.default.device[0], "默认输出设备:", sd.default.device[1])


def _resolve_device(spec):
    if spec is None or spec == "":
        return None
    if isinstance(spec, int):
        return spec
    spec = str(spec).lower()
    for idx, dev in enumerate(sd.query_devices()):
        if spec in dev["name"].lower():
            return idx
    raise ValueError(f"未在音频设备列表中找到包含 '{spec}' 的设备")


class AudioCapture:
    """从指定输入设备持续采集 int16 PCM，块数据推入队列。"""

    def __init__(self, sample_rate: int, channels: int, blocksize: int,
                 device=None, max_queue: int = 3) -> None:
        # 激进档：队列上限 3 块（10ms/块 ≈ 30ms，20ms/块 ≈ 60ms）；积压即丢最旧块，优先保实时。
        self.sample_rate = sample_rate
        self.channels = channels
        self.blocksize = blocksize
        self.device = _resolve_device(device)
        self._queue: "queue.Queue[bytes]" = queue.Queue(maxsize=max_queue)
        self._stream = None
        self._dropped = 0

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status:
            logger.warning("音频状态: %s", status)
        pcm = indata.astype(np.int16).tobytes()
        try:
            self._queue.put_nowait(pcm)
        except queue.Full:
            self._dropped += 1
            # 队列满：丢弃最旧一块再放入，避免持续累积延迟
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(pcm)
            except queue.Empty:
                pass

    def start(self) -> None:
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            blocksize=self.blocksize,
            device=self.device,
            latency="low",  # 让 PortAudio 选择低延迟设备缓冲
            callback=self._callback,
        )
        self._stream.start()
        logger.info("采集启动: %d Hz, %d 声道, 块大小 %d, 流延迟 %.1f ms",
                     self.sample_rate, self.channels, self.blocksize,
                     self._stream.latency * 1000 if self._stream.latency else -1)

    def read(self, timeout: float = 1.0) -> bytes | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        logger.info("采集停止，期间丢弃 %d 块", self._dropped)
