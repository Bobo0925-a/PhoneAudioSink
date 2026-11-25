package com.example.phoneaudiosink

import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * 单声道 biquad 滤波器（转置直接 II 型），用于均衡与搁架。
 */
class Biquad(
    private val b0: Float, private val b1: Float, private val b2: Float,
    private val a1: Float, private val a2: Float,
) {
    private var z1 = 0f
    private var z2 = 0f

    fun reset() {
        z1 = 0f
        z2 = 0f
    }

    fun process(x: Float): Float {
        val y = b0 * x + z1
        z1 = b1 * x - a1 * y + z2
        z2 = b2 * x - a2 * y
        return y
    }

    companion object {
        fun identity(): Biquad = Biquad(1f, 0f, 0f, 0f, 0f)

        /** 峰值型（peaking EQ），dB 为增益。 */
        fun peaking(fs: Float, f: Float, q: Float, db: Float): Biquad {
            if (db <= 0.01f && db >= -0.01f) return identity()
            val w0 = 2.0 * Math.PI * f / fs
            val cosW = cos(w0).toFloat()
            val alpha = (sin(w0) / (2.0 * q)).toFloat()
            val a = 10.0.pow(db / 40.0).toFloat()
            val b0 = 1f + alpha * a
            val b1 = -2f * cosW
            val b2 = 1f - alpha * a
            val a0 = 1f + alpha / a
            val a1 = -2f * cosW
            val a2 = 1f - alpha / a
            return Biquad(b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)
        }

        /** 低频搁架（low shelf），用于低频增强。 */
        fun lowShelf(fs: Float, f: Float, db: Float, slope: Float = 1.0f): Biquad {
            if (db <= 0.01f && db >= -0.01f) return identity()
            val w0 = 2.0 * Math.PI * f / fs
            val cosW = cos(w0).toFloat()
            val sinW = sin(w0).toFloat()
            val a = 10.0.pow(db / 40.0).toFloat()
            val alpha = sinW / 2f * sqrt((a + 1f / a) * (1f / slope - 1f) + 2f)
            val sqrtA = sqrt(a) * 2f * alpha
            val b0 = a * ((a + 1f) - (a - 1f) * cosW + sqrtA)
            val b1 = 2f * a * ((a - 1f) - (a + 1f) * cosW)
            val b2 = a * ((a + 1f) - (a - 1f) * cosW - sqrtA)
            val a0 = (a + 1f) + (a - 1f) * cosW + sqrtA
            val a1 = -2f * ((a - 1f) + (a + 1f) * cosW)
            val a2 = (a + 1f) + (a - 1f) * cosW - sqrtA
            return Biquad(b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)
        }
    }
}

/** 一阶低通，用于虚拟低音取低频分量。 */
class OnePoleLowPass(fs: Float, fc: Float) {
    private val a = (1.0 - exp(-2.0 * Math.PI * fc / fs)).toFloat()
    private var y = 0f

    fun reset() {
        y = 0f
    }

    fun process(x: Float): Float {
        y += a * (x - y)
        return y
    }
}

/**
 * App 内音频处理链：7 段图示均衡 → 低频增强 → 虚拟低音 → 增益 + 软限幅。
 * 全部使用短窗 IIR，单块处理延迟可忽略，不引入系统级长缓冲。
 */
class AudioEffects(private val settings: EffectSettings) {

    companion object {
        val BANDS = floatArrayOf(60f, 150f, 400f, 1000f, 2400f, 6000f, 15000f)
        const val BAND_Q = 1.1f
        private const val BASS_SHELF_HZ = 120f
        private const val VB_CUTOFF = 160f
    }

    private var sampleRate = 48000f
    private var channels = 2

    private var eqL = Array(BANDS.size) { Biquad.identity() }
    private var eqR = Array(BANDS.size) { Biquad.identity() }
    private var shelfL = Biquad.identity()
    private var shelfR = Biquad.identity()

    private var vbLowL = OnePoleLowPass(sampleRate, VB_CUTOFF)
    private var vbLowR = OnePoleLowPass(sampleRate, VB_CUTOFF)

    private var builtVersion = -1
    private var gainLin = 1f
    private var softClip = false
    private var vbOn = false
    private var vbDrive = 0.45f

    fun setFormat(sampleRate: Int, channels: Int) {
        this.sampleRate = sampleRate.toFloat()
        this.channels = channels
        vbLowL = OnePoleLowPass(this.sampleRate, VB_CUTOFF)
        vbLowR = OnePoleLowPass(this.sampleRate, VB_CUTOFF)
        builtVersion = -1
        resetState()
    }

    fun resetState() {
        eqL.forEach { it.reset() }
        eqR.forEach { it.reset() }
        shelfL.reset()
        shelfR.reset()
        vbLowL.reset()
        vbLowR.reset()
    }

    private fun rebuild() {
        val gains = settings.eqGains()
        for (i in BANDS.indices) {
            val db = gains[i].toFloat()
            eqL[i] = Biquad.peaking(sampleRate, BANDS[i], BAND_Q, db)
            eqR[i] = Biquad.peaking(sampleRate, BANDS[i], BAND_Q, db)
        }
        shelfL = Biquad.lowShelf(sampleRate, BASS_SHELF_HZ, settings.bassDb().toFloat())
        shelfR = Biquad.lowShelf(sampleRate, BASS_SHELF_HZ, settings.bassDb().toFloat())

        gainLin = 10.0.pow(settings.gainDb() / 20.0).toFloat()
        softClip = settings.gainDb() > 0.5f
        vbOn = settings.virtualBass()
        vbDrive = 0.35f + settings.bassDb() / 40f

        builtVersion = settings.version
    }

    private fun softLimit(x: Float): Float {
        // 有理式 tanh 近似，峰值压缩不产生硬削波
        val t = x.coerceIn(-3f, 3f)
        return t * (27f + t * t) / (27f + 9f * t * t)
    }

    /** 就地处理 16bit 交错 PCM，返回同一缓冲。 */
    fun process(pcm: ByteArray): ByteArray {
        if (settings.version != builtVersion) rebuild()
        if (!settings.anyEffectActive()) return pcm

        val n = pcm.size / 2
        var i = 0
        var ch = 0
        while (i < n) {
            val raw = (pcm[i * 2].toInt() and 0xFF) or (pcm[i * 2 + 1].toInt() shl 8)
            var x = raw.toFloat() / 32768f

            if (ch == 0) {
                for (f in eqL) x = f.process(x)
                x = shelfL.process(x)
                if (vbOn) x += virtualBass(x, true)
            } else {
                for (f in eqR) x = f.process(x)
                x = shelfR.process(x)
                if (vbOn) x += virtualBass(x, false)
            }

            x *= gainLin
            if (softClip) x = softLimit(x)

            var v = (x * 32767f).toInt()
            if (v > 32767) v = 32767
            if (v < -32768) v = -32768
            pcm[i * 2] = (v and 0xFF).toByte()
            pcm[i * 2 + 1] = ((v shr 8) and 0xFF).toByte()

            i++
            ch = if (channels >= 2) 1 - ch else 0
        }
        return pcm
    }

    /** 谐波合成虚拟低音：取低频分量做非线性生成谐波，弥补手机小喇叭低频不足。 */
    private fun virtualBass(x: Float, left: Boolean): Float {
        val low = if (left) vbLowL.process(x) else vbLowR.process(x)
        if (abs(low) < 0.0005f) return 0f
        val h = low * abs(low) * vbDrive * 3f
        return h * 0.6f
    }
}
