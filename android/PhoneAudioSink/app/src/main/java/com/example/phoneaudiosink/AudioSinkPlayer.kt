package com.example.phoneaudiosink

import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import android.os.SystemClock
import android.util.Log
import com.example.phoneaudiosink.Protocol.HelloInfo

/**
 * 音频播放端：解码线程处理音效后入队，独立播放线程按节奏写入 AudioTrack。
 *
 * 缓冲策略（2026-11 低延迟改造）
 * ----------------------------
 * 旧实现把 bufferMs 当成队列**硬上限**，生产与消费都是实时速率，队列长期贴着上限跑，
 * 于是「档位多少、延迟就几乎是多少」。现在改为**目标水位**调度：
 *
 *  1. 播放线程每次取块前，若队列低于 targetBlocks，就原地等补到目标再取（预填/回填）。
 *  2. 队列高出 targetBlocks + slack 才丢最旧块，一次追平到目标，不做零碎丢弃。
 *  3. hardCapBlocks 只兜底极端卡顿，防止无限积压。
 *  4. AudioTrack 引擎缓冲压到 2 块（setBufferSizeInFrames），避免写满几十毫秒。
 *  5. 播放线程用 THREAD_PRIORITY_URGENT_AUDIO，减少被抢占造成的抖动。
 *
 * 稳态延迟 ≈ targetBlocks × 帧长 + 引擎缓冲 + 采集与编码，实际由档位决定。
 */
class AudioSinkPlayer {

    private var track: AudioTrack? = null
    private var currentInfo: HelloInfo? = null

    private val queue = ArrayDeque<ByteArray>()
    private val lock = Object()
    private var playerThread: Thread? = null
    @Volatile private var running = false

    /** 单帧时长（ms）：10ms 帧为 10，20ms 帧为 20。 */
    private var blockMs = 20
    /** 单帧字节数 = 帧样本 × 声道 × 2。 */
    private var bytesPerBlock = 0

    /** 目标水位（块）。稳态延迟基本等于它。 */
    private var targetBlocks = 3
    /** 允许的抖动余量，超过目标 + 余量才追平。 */
    private var slackBlocks = 1
    /** 极端积压兜底。 */
    private var hardCapBlocks = 10

    private val effects = AudioEffects(EffectSettings)

    /** 队列内块数（统计用）。 */
    @Volatile var bufferedBlocks = 0
        private set

    /** 因过载被丢弃的块数。 */
    @Volatile var droppedBlocks = 0
        private set

    private companion object {
        const val TAG = "AudioSinkPlayer"
        /** 欠载后最多等多久补货，超时照播，避免永久静音。 */
        const val REFILL_TIMEOUT_MS = 400L
        /** 引擎缓冲保留几块。 */
        const val ENGINE_BLOCKS = 2
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

        blockMs = if (info.sampleRate > 0) {
            (info.frameSize * 1000 / info.sampleRate).coerceAtLeast(1)
        } else 20
        bytesPerBlock = info.frameSize * info.channels * 2
        recalc()

        effects.setFormat(info.sampleRate, info.channels)

        droppedBlocks = 0
        bufferedBlocks = 0
        synchronized(lock) {
            queue.clear()
            lock.notifyAll()
        }

        running = true
        playerThread = Thread({ playbackLoop() }, "audio-playback").also { it.start() }
        newTrack.play()

        // 引擎缓冲压到 2 块：写满即阻塞，让写节奏贴住实时，别囤几十毫秒
        try {
            val desired = info.frameSize * ENGINE_BLOCKS
            val applied = newTrack.setBufferSizeInFrames(desired)
            Log.i(TAG, "引擎缓冲 $desired 帧 -> 实际 $applied 帧")
        } catch (e: Throwable) {
            // 低版本设备没有该方法（NoSuchMethodError 不是 Exception）
            Log.w(TAG, "引擎缓冲调整不可用: $e")
        }

        Log.i(TAG, "AudioTrack ${info.sampleRate}Hz ${info.channels}ch 构造缓冲 ${bufferSize}B " +
                "目标 ${targetBlocks} 块 (${targetBlocks * blockMs}ms) 帧长 ${blockMs}ms")
    }

    /** 依据当前档位重算水位。帧长变化或用户改档时调用，立即生效。 */
    private fun recalc() {
        val tierMs = AppSettings.bufferMs.coerceIn(20, 600)
        targetBlocks = ((tierMs + blockMs - 1) / blockMs).coerceAtLeast(2)
        slackBlocks = (targetBlocks / 3).coerceAtLeast(1)
        hardCapBlocks = targetBlocks + slackBlocks * 3 + 2
    }

    /** 缓冲档位变更后调用，立即生效（并把已经囤起来的旧数据裁到新水位内）。 */
    fun applyBufferSetting() {
        synchronized(lock) {
            recalc()
            while (queue.size > hardCapBlocks) {
                queue.removeFirst()
                droppedBlocks++
            }
            bufferedBlocks = queue.size
        }
    }

    /** 解码后的 PCM 块：先过音效，再入队；明显超水位时一次追平。 */
    fun enqueue(pcm: ByteArray) {
        val processed = effects.process(pcm)
        synchronized(lock) {
            if (queue.size >= hardCapBlocks) {
                queue.removeFirst()
                droppedBlocks++
            }
            queue.addLast(processed)

            // 只在高出「目标 + 抖动余量」时追平，避免零碎丢弃带来的咔哒声
            if (queue.size > targetBlocks + slackBlocks) {
                while (queue.size > targetBlocks) {
                    queue.removeFirst()
                    droppedBlocks++
                }
            }
            bufferedBlocks = queue.size
            lock.notifyAll()
        }
    }

    fun bufferedMs(): Int = bufferedBlocks * blockMs

    private fun playbackLoop() {
        try {
            android.os.Process.setThreadPriority(android.os.Process.THREAD_PRIORITY_URGENT_AUDIO)
        } catch (_: Throwable) {
        }

        while (running) {
            var pcm: ByteArray? = null
            synchronized(lock) {
                // 低于目标水位就等补货：既做开播预填，也做运行中的回填
                if (queue.size < targetBlocks) {
                    val deadline = SystemClock.uptimeMillis() + REFILL_TIMEOUT_MS
                    while (running && queue.size < targetBlocks &&
                        SystemClock.uptimeMillis() < deadline
                    ) {
                        try {
                            lock.wait(20)
                        } catch (_: InterruptedException) {
                            break
                        }
                    }
                }
                pcm = if (queue.isEmpty()) null else queue.removeFirst()
                bufferedBlocks = queue.size
            }

            if (!running) break
            val p = pcm ?: continue

            try {
                track?.write(p, 0, p.size)
            } catch (e: Exception) {
                Log.w(TAG, "写入失败: $e")
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
        synchronized(lock) { queue.clear() }
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
