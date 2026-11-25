# -*- coding: utf-8 -*-
"""Opus 编码封装（基于 opuslib-next-bundled，内置 libopus）。"""

import logging

from opuslib_next import Encoder

logger = logging.getLogger("opus-enc")


class OpusEncoder:
    def __init__(self, sample_rate: int, channels: int, bitrate: int, frame_size: int) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_size = frame_size
        self.enc = Encoder(sample_rate, channels, "audio")
        self.enc.bitrate = bitrate
        # 每帧 PCM 字节数 = 帧长 × 声道 × 2 字节(int16)
        self.frame_pcm_bytes = frame_size * channels * 2
        logger.info("Opus 编码器: %dHz / %d 声道 / %d bps / 帧长 %d 样本",
                    sample_rate, channels, bitrate, frame_size)

    def encode(self, pcm: bytes) -> bytes:
        if len(pcm) != self.frame_pcm_bytes:
            raise ValueError(
                f"PCM 长度 {len(pcm)} 与帧大小 {self.frame_pcm_bytes} 不符")
        return self.enc.encode(pcm, self.frame_size)

    def close(self) -> None:
        # opuslib-next Encoder 无显式 destroy 公开方法，靠 GC 回收
        self.enc = None
