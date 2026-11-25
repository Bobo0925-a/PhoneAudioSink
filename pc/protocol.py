# -*- coding: utf-8 -*-
"""
WiFi 版二进制帧协议（PC 端 / Android 端必须保持一致）。

二进制帧（大端 / Big-Endian）::

    Offset  Size  Field
    0       2     magic   = 0xAA 0x55
    2       1     version = 2
    3       1     type    消息类型
    4       2     length  payload 字节数 (uint16 BE)
    6       N     payload

消息类型
--------
HELLO  (0x01)  建链后由 PC 发送一次，协商音频/编码格式。
AUDIO  (0x02)  音频数据帧（Opus 包或 PCM）。
PING   (0x03)  保活，无 payload。
PONG   (0x04)  保活应答，无 payload。
BYE    (0x05)  主动断开，无 payload。

codec 取值
----------
0 = PCM 16-bit signed little-endian（预留）
1 = Opus（本版默认）
"""

import struct
from collections import deque

MAGIC = b"\xAA\x55"
VERSION = 2
HEADER_SIZE = 6

HELLO = 0x01
AUDIO = 0x02
PING = 0x03
PONG = 0x04
BYE = 0x05

CODEC_PCM16 = 0
CODEC_OPUS = 1

# UDP 局域网自动发现（文本协议，不走上面的二进制帧）
DISCOVER_REQUEST = "PHONE_AUDIO_DISCOVER"
DISCOVER_REPLY_PREFIX = "PHONE_AUDIO_SERVER"

_HELLO = struct.Struct(">HBBHI")  # sample_rate u16, channels u8, codec u8, frame_size u16, bitrate u32


def pack_hello(sample_rate: int, channels: int, codec: int,
               frame_size: int, bitrate: int) -> bytes:
    payload = _HELLO.pack(sample_rate, channels, codec, frame_size, bitrate)
    return pack_frame(HELLO, payload)


def pack_audio(payload: bytes) -> bytes:
    return pack_frame(AUDIO, payload)


def pack_ping() -> bytes:
    return pack_frame(PING, b"")


def pack_bye() -> bytes:
    return pack_frame(BYE, b"")


def pack_frame(msg_type: int, payload: bytes) -> bytes:
    if len(payload) > 0xFFFF:
        raise ValueError("payload 超过单帧最大长度 65535")
    head = MAGIC + struct.pack(">BBH", VERSION, msg_type, len(payload))
    return head + payload


class FrameReader:
    """流式解帧：处理半包 / 粘包。"""

    def __init__(self) -> None:
        self._buf = deque()
        self._buflen = 0

    def feed(self, data: bytes) -> None:
        if data:
            self._buf.append(data)
            self._buflen += len(data)

    def _peek(self, n: int) -> bytes:
        out = bytearray()
        need = n
        for chunk in self._buf:
            if need >= len(chunk):
                out += chunk
                need -= len(chunk)
            else:
                out += chunk[:need]
                break
        return bytes(out)

    def _consume(self, n: int) -> bytes:
        out = bytearray()
        need = n
        while need > 0 and self._buf:
            chunk = self._buf[0]
            if len(chunk) <= need:
                out += chunk
                self._buf.popleft()
                need -= len(chunk)
            else:
                out += chunk[:need]
                self._buf[0] = chunk[need:]
                need = 0
        self._buflen -= n
        return bytes(out)

    def read_frame(self):
        while True:
            if self._buflen < HEADER_SIZE:
                return None
            head = self._peek(HEADER_SIZE)
            if head[0:2] != MAGIC:
                self._consume(1)
                continue
            _version, msg_type, length = struct.unpack(">BBH", head[2:6])
            if self._buflen < HEADER_SIZE + length:
                return None
            self._consume(HEADER_SIZE)
            payload = self._consume(length)
            return msg_type, payload
