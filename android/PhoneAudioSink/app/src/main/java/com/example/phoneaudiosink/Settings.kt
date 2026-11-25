package com.example.phoneaudiosink

import android.content.Context
import android.content.SharedPreferences

private const val PREFS_NAME = "phone_audio_prefs"
private lateinit var prefs: SharedPreferences

fun initSettings(context: Context) {
    if (!::prefs.isInitialized) {
        prefs = context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        EffectSettings.load()
        AppSettings.load()
    }
}

/** 音效参数：EQ 7 段、低频增强、虚拟低音、增益。任何改动 version 自增触发重建。 */
object EffectSettings {

    private const val KEY_EQ = "eq_gains"
    private const val KEY_BASS = "bass_db"
    private const val KEY_GAIN = "gain_db"
    private const val KEY_VB = "virtual_bass"
    private const val KEY_PRESET = "preset"

    val BAND_COUNT = 7
    val BAND_LABELS = arrayOf("60", "150", "400", "1k", "2.4k", "6k", "15k")

    private val eq = IntArray(BAND_COUNT)
    @Volatile private var bassDb = 0
    @Volatile private var gainDb = 0
    @Volatile private var virtualBass = false
    @Volatile var presetId = 0

    @Volatile var version = 0
        private set

    /** 第 0 项是「自定义」，界面上只展示 1..n。 */
    private val PRESET_RES = intArrayOf(
        R.string.preset_custom,
        R.string.preset_electronic,
        R.string.preset_vocal,
        R.string.preset_clear,
        R.string.preset_strings,
    )

    /** 预设名称随当前语言从资源取，不要缓存成常量。 */
    fun presetLabels(): Array<String> = PRESET_RES.map { Str.s(it) }.toTypedArray()

    private val PRESET_GAINS = arrayOf(
        intArrayOf(0, 0, 0, 0, 0, 0, 0),
        intArrayOf(4, 3, 1, -1, 1, 3, 3),
        intArrayOf(-3, -1, 1, 3, 4, 2, 0),
        intArrayOf(-1, 1, 2, 2, 1, 2, 4),
        intArrayOf(3, 2, 0, 1, 2, 3, 1),
    )

    fun load() {
        val saved = prefs.getString(KEY_EQ, null)
        if (saved != null) {
            val parts = saved.split(",")
            for (i in 0 until BAND_COUNT) {
                eq[i] = parts.getOrNull(i)?.toIntOrNull() ?: 0
            }
        }
        bassDb = prefs.getInt(KEY_BASS, 0)
        gainDb = prefs.getInt(KEY_GAIN, 0)
        virtualBass = prefs.getBoolean(KEY_VB, false)
        presetId = prefs.getInt(KEY_PRESET, 0)
        version++
    }

    fun save() {
        prefs.edit()
            .putString(KEY_EQ, eq.joinToString(","))
            .putInt(KEY_BASS, bassDb)
            .putInt(KEY_GAIN, gainDb)
            .putBoolean(KEY_VB, virtualBass)
            .putInt(KEY_PRESET, presetId)
            .apply()
    }

    fun eqGains(): IntArray = eq.copyOf()

    fun bandGain(index: Int): Int = eq[index]

    fun setBand(index: Int, db: Int) {
        if (index !in 0 until BAND_COUNT) return
        eq[index] = db.coerceIn(-12, 12)
        presetId = 0
        version++
    }

    fun setEqGains(values: IntArray) {
        for (i in 0 until BAND_COUNT) eq[i] = values.getOrElse(i) { 0 }.coerceIn(-12, 12)
        version++
    }

    fun bassDb(): Int = bassDb

    fun setBassDb(db: Int) {
        bassDb = db.coerceIn(0, 12)
        version++
    }

    fun gainDb(): Int = gainDb

    fun setGainDb(db: Int) {
        gainDb = db.coerceIn(0, 12)
        version++
    }

    fun virtualBass(): Boolean = virtualBass

    fun setVirtualBass(on: Boolean) {
        virtualBass = on
        version++
    }

    fun applyPreset(id: Int) {
        if (id !in PRESET_RES.indices) return
        presetId = id
        setEqGains(PRESET_GAINS[id].copyOf())
        version++
    }

    fun reset() {
        presetId = 0
        setEqGains(PRESET_GAINS[0].copyOf())
        bassDb = 0
        gainDb = 0
        virtualBass = false
        version++
    }

    fun anyEffectActive(): Boolean {
        if (virtualBass || bassDb != 0 || gainDb != 0) return true
        for (g in eq) if (g != 0) return true
        return false
    }
}

/** 连接与界面偏好。 */
object AppSettings {

    private const val KEY_BUFFER_MS = "buffer_ms"
    private const val KEY_LIGHT = "light_mode"
    private const val KEY_AUTO_RECONNECT = "auto_reconnect"
    private const val KEY_HEARTBEAT = "heartbeat"
    private const val KEY_LAST_IP = "last_ip"
    private const val KEY_SERVER_MODE = "server_mode"
    private const val KEY_REDUCE_MOTION = "reduce_motion"
    private const val KEY_LANGUAGE = "language"

    val BUFFER_TIERS = intArrayOf(120, 250, 400)
    private val BUFFER_RES = intArrayOf(
        R.string.buffer_label_120, R.string.buffer_label_250, R.string.buffer_label_400,
    )

    fun bufferLabels(): Array<String> = BUFFER_RES.map { Str.s(it) }.toTypedArray()

    @Volatile var bufferMs = 250
        private set
    @Volatile var lightMode = false
        private set
    @Volatile var autoReconnect = true
        private set
    @Volatile var heartbeat = true
        private set
    @Volatile var lastIp = ""
        private set
    /** true 表示等待 PC 主动连入（手机作服务端）。 */
    @Volatile var serverMode = false
        private set
    /** 减弱动态效果（与系统无障碍设置叠加生效）。 */
    @Volatile var reduceMotion = false
        private set
    /** 界面语言：空 = 跟随系统，否则 "zh" / "en"。 */
    @Volatile var language = ""
        private set

    fun load() {
        bufferMs = prefs.getInt(KEY_BUFFER_MS, 250)
        lightMode = prefs.getBoolean(KEY_LIGHT, false)
        autoReconnect = prefs.getBoolean(KEY_AUTO_RECONNECT, true)
        heartbeat = prefs.getBoolean(KEY_HEARTBEAT, true)
        lastIp = prefs.getString(KEY_LAST_IP, "") ?: ""
        serverMode = prefs.getBoolean(KEY_SERVER_MODE, false)
        reduceMotion = prefs.getBoolean(KEY_REDUCE_MOTION, false)
        language = prefs.getString(KEY_LANGUAGE, "") ?: ""
    }

    fun setLanguage(tag: String) {
        language = tag
        prefs.edit().putString(KEY_LANGUAGE, tag).apply()
    }

    fun setReduceMotion(on: Boolean) {
        reduceMotion = on
        prefs.edit().putBoolean(KEY_REDUCE_MOTION, on).apply()
    }

    fun setServerMode(on: Boolean) {
        serverMode = on
        prefs.edit().putBoolean(KEY_SERVER_MODE, on).apply()
    }

    fun setBufferMs(ms: Int) {
        bufferMs = ms
        prefs.edit().putInt(KEY_BUFFER_MS, ms).apply()
    }

    fun setLightMode(on: Boolean) {
        lightMode = on
        prefs.edit().putBoolean(KEY_LIGHT, on).apply()
    }

    fun setAutoReconnect(on: Boolean) {
        autoReconnect = on
        prefs.edit().putBoolean(KEY_AUTO_RECONNECT, on).apply()
    }

    fun setHeartbeat(on: Boolean) {
        heartbeat = on
        prefs.edit().putBoolean(KEY_HEARTBEAT, on).apply()
    }

    fun setLastIp(ip: String) {
        lastIp = ip
        prefs.edit().putString(KEY_LAST_IP, ip).apply()
    }

    fun resetAll() {
        setBufferMs(250)
        setLightMode(false)
        setAutoReconnect(true)
        setHeartbeat(true)
        setReduceMotion(false)
        EffectSettings.reset()
    }
}
