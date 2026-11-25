package com.example.phoneaudiosink

import android.content.Context
import android.os.Handler
import android.os.Looper
import java.util.concurrent.CopyOnWriteArrayList

/**
 * App 内共享的音频链路中心：单例持有播放器与网络客户端，负责状态广播与自动重连。
 */
object AudioHub {

    data class HubState(
        val status: NetClient.State = NetClient.State.IDLE,
        val detail: String = "未连接",
        val format: String = "格式 待协商",
        val bufferMs: Int = 0,
        val dropped: Int = 0,
        val frames: Int = 0,
    )

    @Volatile
    var state = HubState()
        private set

    lateinit var player: AudioSinkPlayer
        private set
    lateinit var client: NetClient
        private set

    private var inited = false
    private val listeners = CopyOnWriteArrayList<(HubState) -> Unit>()
    private val main = Handler(Looper.getMainLooper())

    @Volatile private var wantConnected = false
    private var reconnectPending = false

    fun init(context: Context) {
        if (inited) return
        initSettings(context)
        player = AudioSinkPlayer()
        client = NetClient(player, callbacks)
        inited = true
    }

    private val callbacks = object : NetClient.Callbacks {
        override fun onState(state: NetClient.State, detail: String) {
            publish(state = state, detail = detail)
            if (state == NetClient.State.IDLE || state == NetClient.State.ERROR) {
                scheduleReconnect()
            }
        }

        override fun onHello(info: Protocol.HelloInfo) {
            val text = "格式 ${info.sampleRate}Hz · ${info.channels}声道 · " +
                    "Opus · ${info.frameSize} 帧 · ${info.bitrate / 1000}kbps"
            publish(format = text)
        }

        override fun onBuffer(ms: Int, dropped: Int, frames: Int) {
            publish(bufferMs = ms, dropped = dropped, frames = frames)
        }
    }

    private fun publish(
        state: NetClient.State? = null,
        detail: String? = null,
        format: String? = null,
        bufferMs: Int? = null,
        dropped: Int? = null,
        frames: Int? = null,
    ) {
        val current = this.state
        this.state = HubState(
            status = state ?: current.status,
            detail = detail ?: current.detail,
            format = format ?: current.format,
            bufferMs = bufferMs ?: current.bufferMs,
            dropped = dropped ?: current.dropped,
            frames = frames ?: current.frames,
        )
        val snapshot = this.state
        main.post { listeners.forEach { it(snapshot) } }
    }

    fun addListener(listener: (HubState) -> Unit) {
        if (!listeners.contains(listener)) listeners.add(listener)
        listener(state)
    }

    fun removeListener(listener: (HubState) -> Unit) {
        listeners.remove(listener)
    }

    fun connect(host: String, port: Int = 42101) {
        wantConnected = true
        client.connect(host, port)
    }

    fun connectLast(): Boolean {
        val ip = AppSettings.lastIp
        if (ip.isBlank()) return false
        connect(ip)
        return true
    }

    /** 手机作服务端，等待 PC 端"直连手机"接入。 */
    fun listen(port: Int = 42101) {
        wantConnected = false
        client.listen(port)
    }

    fun disconnect() {
        wantConnected = false
        client.disconnect()
        publish(state = NetClient.State.IDLE, detail = "已断开")
    }

    fun scan(timeoutMs: Int = 2500): List<ServerInfo> =
        try {
            client.discover(42100, timeoutMs)
        } catch (e: Exception) {
            emptyList()
        }

    private fun scheduleReconnect() {
        if (!wantConnected || !AppSettings.autoReconnect) return
        if (AppSettings.lastIp.isBlank()) return
        if (reconnectPending) return
        reconnectPending = true
        main.postDelayed({
            reconnectPending = false
            if (wantConnected && client.running.not() && AppSettings.lastIp.isNotBlank()) {
                connect(AppSettings.lastIp)
            }
        }, 2200)
    }
}
