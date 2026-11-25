package com.example.phoneaudiosink

import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import android.util.Log
import com.example.phoneaudiosink.Protocol.HelloInfo
import java.util.concurrent.ConcurrentLinkedQueue

/**
 * 音频播放端：解码线程处理音效后入队，独立播放线程按节奏写入 AudioTrack。
 * 队列有界（按设置缓冲档位，120/250/400 ms）；超限丢弃最旧数据追平实时。
 */
class AudioSinkPlayer {

    private var track: AudioTrack? = null
    private var currentInfo: HelloInfo? = null

    private val queue = ConcurrentLinkedQueue<ByteArray>()
    private val lock = Object()
    private var playerThread: Thread? = null
    @Volatile private var running = false

    private var blockMs = 20
    @Volatile private var maxBlocks = 13

    private val effects = AudioEffects(EffectSettings)

    /** 队列内块数（统计用）。 */
    @Volatile var bufferedBlocks = 0
        private set

    /** 因过载被丢弃的块数。 */
    @Volatile var droppedBlocks = 0
        private set

    private companion object {
        const val TAG = "AudioSinkPlayer"
    }

    @Synchronized
    fun configure(info: HelloInfo) {
        releaseInternal()

        val channelMask = if (info.channels == 1) {
            AudioFormat.CHANNEL_OUT_MONO
        } else {
            AudioFormat.CHANNEL_OUT_STEREO
        }
        val encoding = AudioFormat.ENCODING_PCM_16BIT

        val minBuf = AudioTrack.getMinBufferSize(info.sampleRate, channelMask, encoding)
        val bufferSize = if (minBuf > 0) minBuf else info.sampleRate * 2

        @Suppress("DEPRECATION")
        val newTrack = AudioTrack(
            AudioManager.STREAM_MUSIC,
            info.sampleRate,
            channelMask,
            encoding,
            bufferSize,
            AudioTrack.MODE_STREAM,
        )
        try {
            val lowLatency = 1 // PERFORMANCE_MODE_LOW_LATENCY
            AudioTrack::class.java
                .getMethod("setPerformanceMode", Int::class.javaPrimitiveType)
                .invoke(newTrack, lowLatency)
        } catch (e: Exception) {
            Log.w(TAG, "低延迟模式不可用: $e")
        }

        track = newTrack
        currentInfo = info

        blockMs = if (info.sampleRate > 0) info.frameSize * 1000 / info.sampleRate else 20
        recalcBlocks()

        effects.setFormat(info.sampleRate, info.channels)

        droppedBlocks = 0
        bufferedBlocks = 0
        queue.clear()

        running = true
        playerThread = Thread({ playbackLoop() }, "audio-playback").also { it.start() }
        newTrack.play()

        Log.i(TAG, "AudioTrack ${info.sampleRate}Hz ${info.channels}ch 缓冲 ${bufferSize}B " +
                "队列 ${maxBlocks} 块 (${blockMs}ms)")
    }

    private fun recalcBlocks() {
        maxBlocks = (AppSettings.bufferMs / blockMs).coerceAtLeast(3)
    }

    /** 缓冲档位变更后调用，立即生效。 */
    fun applyBufferSetting() {
        recalcBlocks()
    }

    /** 解码后的 PCM 块：先过音效，再入队；超限丢最旧块追平。 */
    fun enqueue(pcm: ByteArray) {
        val processed = effects.process(pcm)
        synchronized(lock) {
            while (queue.size >= maxBlocks) {
                queue.poll()
                droppedBlocks++
                bufferedBlocks--
            }
            queue.offer(processed)
            bufferedBlocks++
            lock.notifyAll()
        }
    }

    fun bufferedMs(): Int = bufferedBlocks * blockMs

    private fun playbackLoop() {
        while (running) {
            val pcm: ByteArray?
            synchronized(lock) {
                while (queue.isEmpty() && running) {
                    try {
                        lock.wait(200)
                    } catch (_: InterruptedException) {
                        break
                    }
                }
                pcm = queue.poll()
                if (pcm != null) bufferedBlocks--
            }
            if (pcm != null) {
                track?.write(pcm, 0, pcm.size)
            }
        }
    }

    @Synchronized
    fun release() {
        releaseInternal()
        currentInfo = null
    }

    private fun releaseInternal() {
        running = false
        synchronized(lock) { lock.notifyAll() }
        playerThread?.let {
            try { it.join(200) } catch (_: Exception) {}
        }
        playerThread = null
        queue.clear()
        bufferedBlocks = 0
        effects.resetState()
        releaseTrack()
    }

    private fun releaseTrack() {
        track?.let {
            try {
                it.stop()
                it.release()
            } catch (e: Exception) {
                Log.w(TAG, "释放 AudioTrack 异常: $e")
            }
        }
        track = null
    }
}
