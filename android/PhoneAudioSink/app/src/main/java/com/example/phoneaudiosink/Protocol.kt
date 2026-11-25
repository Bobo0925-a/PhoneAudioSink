package com.example.phoneaudiosink

import java.io.ByteArrayOutputStream

/**
 * 与 PC 端 pc/protocol.py 保持一致的二进制帧协议（大端）。
 *
 * 帧头: magic(0xAA 0x55) | version(u8) | type(u8) | length(u16 BE) | payload
 */
object Protocol {
    const val MAGIC_0: Byte = 0xAA.toByte()
    const val MAGIC_1: Byte = 0x55.toByte()
    const val VERSION = 2
    const val HEADER_SIZE = 6

    const val HELLO = 0x01
    const val AUDIO = 0x02
    const val PING = 0x03
    const val PONG = 0x04
    const val BYE = 0x05

    const val CODEC_PCM16 = 0
    const val CODEC_OPUS = 1

    // UDP 自动发现（文本协议）
    const val DISCOVER_REQUEST = "PHONE_AUDIO_DISCOVER"
    const val DISCOVER_REPLY_PREFIX = "PHONE_AUDIO_SERVER"

    data class Frame(val type: Int, val payload: ByteArray)

    data class HelloInfo(
        val sampleRate: Int,
        val channels: Int,
        val codec: Int,
        val frameSize: Int,
        val bitrate: Int,
    )

    /** 流式解帧：处理半包 / 粘包。 */
    class FrameReader {
        private var buffer = ByteArray(0)

        fun feed(data: ByteArray, offset: Int, length: Int) {
            if (length <= 0) return
            val out = ByteArrayOutputStream(buffer.size + length)
            out.write(buffer)
            out.write(data, offset, length)
            buffer = out.toByteArray()
        }

        fun nextFrame(): Frame? {
            while (buffer.size >= HEADER_SIZE) {
                if (buffer[0] != MAGIC_0 || buffer[1] != MAGIC_1) {
                    buffer = buffer.copyOfRange(1, buffer.size)
                    continue
                }
                val type = buffer[3].toInt() and 0xFF
                val length = ((buffer[4].toInt() and 0xFF) shl 8) or
                        (buffer[5].toInt() and 0xFF)
                if (buffer.size < HEADER_SIZE + length) return null

                val payload = buffer.copyOfRange(HEADER_SIZE, HEADER_SIZE + length)
                buffer = buffer.copyOfRange(HEADER_SIZE + length, buffer.size)
                return Frame(type, payload)
            }
            return null
        }
    }

    fun parseHello(payload: ByteArray): HelloInfo {
        require(payload.size >= 10) { "HELLO 载荷长度不足: ${payload.size}" }
        val sampleRate = ((payload[0].toInt() and 0xFF) shl 8) or
                (payload[1].toInt() and 0xFF)
        val channels = payload[2].toInt() and 0xFF
        val codec = payload[3].toInt() and 0xFF
        val frameSize = ((payload[4].toInt() and 0xFF) shl 8) or
                (payload[5].toInt() and 0xFF)
        val bitrate = ((payload[6].toInt() and 0xFF) shl 24) or
                ((payload[7].toInt() and 0xFF) shl 16) or
                ((payload[8].toInt() and 0xFF) shl 8) or
                (payload[9].toInt() and 0xFF)
        return HelloInfo(sampleRate, channels, codec, frameSize, bitrate)
    }
}
