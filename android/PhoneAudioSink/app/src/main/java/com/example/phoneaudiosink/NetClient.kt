package com.example.phoneaudiosink

import android.util.Log
import com.example.phoneaudiosink.Protocol.DISCOVER_REQUEST
import com.example.phoneaudiosink.Protocol.DISCOVER_REPLY_PREFIX
import com.example.phoneaudiosink.Protocol.HELLO
import com.example.phoneaudiosink.Protocol.AUDIO
import com.example.phoneaudiosink.Protocol.PING
import com.example.phoneaudiosink.Protocol.BYE
import com.example.phoneaudiosink.Protocol.FrameReader
import com.example.phoneaudiosink.Protocol.parseHello
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketTimeoutException

/** 一台可连接的 PC 服务器。 */
data class ServerInfo(val name: String, val host: String, val port: Int)

/**
 * 网络客户端：UDP 广播自动发现 PC，TCP 连接接收 Opus 音频流并解码。
 * 支持心跳应答与读超时，避免僵死链接持续堆积音频数据。
 */
class NetClient(
    private val player: AudioSinkPlayer,
    private val callbacks: Callbacks,
) {
    interface Callbacks {
        fun onState(state: State, detail: String)
        fun onHello(info: Protocol.HelloInfo)
        fun onBuffer(ms: Int, dropped: Int, frames: Int) {}
    }

    enum class State { IDLE, SCANNING, CONNECTED, ERROR }

    private var socket: Socket? = null
    private var serverSocket: ServerSocket? = null
    private var ioThread: Thread? = null
    private var decoder: OpusDecoder? = null

    @Volatile
    var running = false
        private set

    /** 当前连接的对端地址。 */
    @Volatile
    var currentHost: String = ""
        private set

    private companion object {
        const val TAG = "NetClient"
        const val READ_TIMEOUT_MS = 6000
        val PONG_FRAME = byteArrayOf(
            0xAA.toByte(), 0x55.toByte(), 0x02, 0x04, 0x00, 0x00,
        )
    }

    /** UDP 广播扫描局域网内的 PC 服务器（阻塞，需在子线程调用）。 */
    fun discover(discoverPort: Int, timeoutMs: Int): List<ServerInfo> {
        val found = LinkedHashMap<String, ServerInfo>()
        val ds = DatagramSocket()
        return try {
            ds.broadcast = true
            ds.soTimeout = timeoutMs
            val req = DISCOVER_REQUEST.toByteArray(Charsets.UTF_8)
            val broadcast = InetAddress.getByName("255.255.255.255")
            ds.send(DatagramPacket(req, req.size, broadcast, discoverPort))

            val buf = ByteArray(1024)
            while (true) {
                val pkt = DatagramPacket(buf, buf.size)
                try {
                    ds.receive(pkt)
                } catch (_: SocketTimeoutException) {
                    break
                }
                val text = String(pkt.data, 0, pkt.length, Charsets.UTF_8).trim()
                if (!text.startsWith(DISCOVER_REPLY_PREFIX)) continue
                val parts = text.split("|")
                if (parts.size >= 3) {
                    val host = pkt.address.hostAddress ?: continue
                    val port = parts[2].toIntOrNull() ?: continue
                    found[host] = ServerInfo(parts[1], host, port)
                }
            }
            found.values.toList()
        } finally {
            ds.close()
        }
    }

    /** 后台连接指定服务器。 */
    fun connect(host: String, port: Int) {
        disconnect()
        ioThread = Thread {
            running = true
            currentHost = host
            try {
                val s = Socket()
                s.connect(java.net.InetSocketAddress(host, port), 3000)
                socket = s
                AppSettings.setLastIp(host)
                callbacks.onState(State.CONNECTED, "已连接 $host:$port")
                ioLoop(s)
            } catch (e: Exception) {
                Log.w(TAG, "连接失败: $e")
                callbacks.onState(State.ERROR, "连接失败: ${e.message ?: "网络不可达"}")
            } finally {
                cleanup()
                if (running) {
                    running = false
                    callbacks.onState(State.IDLE, "连接已断开")
                }
            }
        }.also { it.start() }
    }

    /**
     * 服务端模式：监听端口等待 PC 主动连入（对应 PC 端"直连手机"）。
     * 一次会话结束后自动回到等待状态，直到调用 disconnect()。
     */
    fun listen(port: Int = 42101) {
        disconnect()
        ioThread = Thread {
            running = true
            currentHost = ""
            var server: ServerSocket? = null
            try {
                server = ServerSocket().apply {
                    reuseAddress = true
                    bind(InetSocketAddress(port))
                }
                serverSocket = server
                callbacks.onState(State.SCANNING, "等待电脑连接 · 端口 $port")
                while (running) {
                    val s = try {
                        server.accept()
                    } catch (e: Exception) {
                        if (running) Log.w(TAG, "accept 中断: $e")
                        break
                    }
                    socket = s
                    try {
                        s.tcpNoDelay = true
                    } catch (_: Exception) {
                    }
                    currentHost = s.inetAddress?.hostAddress ?: ""
                    AppSettings.setLastIp(currentHost)
                    callbacks.onState(State.CONNECTED, "电脑已接入 $currentHost")
                    ioLoop(s)
                    try {
                        s.close()
                    } catch (_: Exception) {
                    }
                    socket = null
                    if (running) {
                        callbacks.onState(State.SCANNING, "等待电脑连接 · 端口 $port")
                    }
                }
            } catch (e: Exception) {
                Log.w(TAG, "监听失败: $e")
                callbacks.onState(State.ERROR, "监听失败: ${e.message ?: "端口被占用"}")
            } finally {
                try {
                    server?.close()
                } catch (_: Exception) {
                }
                serverSocket = null
                cleanup()
                if (running) {
                    running = false
                    callbacks.onState(State.IDLE, "监听已停止")
                }
            }
        }.also { it.start() }
    }

    private fun ioLoop(s: Socket) {
        val reader = FrameReader()
        val input = s.getInputStream()
        val output = s.getOutputStream()
        val buf = ByteArray(4096)
        var audioCount = 0

        // 心跳开启时启用读超时，超时即判定链路失效
        s.soTimeout = if (AppSettings.heartbeat) READ_TIMEOUT_MS else 0

        while (running) {
            val n = try {
                input.read(buf)
            } catch (_: SocketTimeoutException) {
                Log.w(TAG, "链路超时，主动断开")
                callbacks.onState(State.ERROR, "链路超时，请重连")
                break
            } catch (e: Exception) {
                Log.w(TAG, "读取异常: $e")
                break
            }

            if (n < 0) break
            reader.feed(buf, 0, n)

            while (true) {
                val frame = reader.nextFrame() ?: break
                when (frame.type) {
                    HELLO -> {
                        val info = parseHello(frame.payload)
                        player.configure(info)
                        decoder?.release()
                        decoder = OpusDecoder(info.sampleRate, info.channels, info.frameSize)
                        callbacks.onHello(info)
                    }
                    AUDIO -> {
                        decoder?.decode(frame.payload)?.let { pcm ->
                            player.enqueue(pcm)
                            audioCount++
                            if (audioCount % 20 == 0) {
                                callbacks.onBuffer(
                                    player.bufferedMs(), player.droppedBlocks, audioCount,
                                )
                            }
                        }
                    }
                    PING -> {
                        if (AppSettings.heartbeat) {
                            try {
                                output.write(PONG_FRAME)
                                output.flush()
                            } catch (_: Exception) {
                            }
                        }
                    }
                    BYE -> {
                        Log.i(TAG, "对端结束会话")
                        return
                    }
                    else -> Log.w(TAG, "未知帧类型 ${frame.type}")
                }
                if (!running) break
            }
        }
    }

    fun disconnect() {
        running = false
        try {
            serverSocket?.close()
        } catch (_: Exception) {
        }
        serverSocket = null
        cleanup()
    }

    private fun cleanup() {
        decoder?.release()
        decoder = null
        socket?.let {
            try { it.close() } catch (_: Exception) {}
        }
        socket = null
        player.applyBufferSetting()
    }
}
