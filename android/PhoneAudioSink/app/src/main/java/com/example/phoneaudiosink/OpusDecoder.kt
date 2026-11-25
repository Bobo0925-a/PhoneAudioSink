package com.example.phoneaudiosink

import android.util.Log
import ashipo.jopus.Opus
import ashipo.jopus.OPUS_OK

/**
 * Opus 解码封装（JOpus / libopus）。输出 16bit 交错 PCM 字节。
 */
class OpusDecoder(
    private val sampleRate: Int,
    private val channels: Int,
    private val frameSize: Int,
) {
    private val opus = Opus()
    private val outBuf = ByteArray(frameSize * channels * 2)

    init {
        val result = opus.initDecoder(sampleRate, channels)
        if (result != OPUS_OK) {
            throw IllegalStateException("Opus 解码器初始化失败: ${opus.getErrorString(result)}")
        }
        Log.i(TAG, "Opus 解码器: ${sampleRate}Hz / ${channels}声道 / 帧长 $frameSize")
    }

    /** 解码一个 Opus 包，返回 16bit PCM 字节；失败返回 null。 */
    fun decode(pkt: ByteArray): ByteArray? {
        val frames = opus.decode(pkt, pkt.size, outBuf, frameSize, 0)
        if (frames < 0) {
            Log.w(TAG, "decode 错误 $frames: ${opus.getErrorString(frames)}")
            return null
        }
        return outBuf.copyOf(frames * channels * 2)
    }

    fun release() {
        try {
            opus.releaseDecoder()
        } catch (e: Exception) {
            Log.w(TAG, "释放解码器异常: $e")
        }
    }

    companion object {
        private const val TAG = "OpusDecoder"
    }
}
