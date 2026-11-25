package com.example.phoneaudiosink

import android.content.res.ColorStateList
import android.graphics.Color
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import com.google.android.material.button.MaterialButton
import kotlin.concurrent.thread

/**
 * 播放页：连接状态、扫描/断开、手动 IP 连接、可用电脑列表。
 * 交互约束：点按即时反馈、异步过程有加载态与骨架屏、错误有抖动与红色边框。
 */
class PlayFragment : Fragment(R.layout.fragment_play) {

    private lateinit var tvStatus: TextView
    private lateinit var tvSub: TextView
    private lateinit var tvFormat: TextView
    private lateinit var tvBuffer: TextView
    private lateinit var tvStats: TextView
    private lateinit var etIp: EditText
    private lateinit var tvLastIp: TextView
    private lateinit var btnScan: MaterialButton
    private lateinit var btnDisconnect: MaterialButton
    private lateinit var btnConnectIp: MaterialButton
    private lateinit var serverList: LinearLayout
    private lateinit var skeletonList: View
    private lateinit var actionLoading: View
    private lateinit var tvActionLoading: TextView
    private lateinit var btnModeClient: MaterialButton
    private lateinit var btnModeServer: MaterialButton
    private lateinit var cardManual: View
    private lateinit var cardStatus: View
    private lateinit var modeRow: View
    private lateinit var actionRow: View
    private lateinit var tvServerTitle: TextView

    private var serverMode = false
    private var scanning = false
    private var listener: ((AudioHub.HubState) -> Unit)? = null

    private val ipPattern = Regex(
        "^((25[0-5]|2[0-4]\\d|1\\d\\d|\\d\\d|\\d)\\.){3}" +
            "(25[0-5]|2[0-4]\\d|1\\d\\d|\\d\\d|\\d)$",
    )

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        tvStatus = view.findViewById(R.id.tvStatus)
        tvSub = view.findViewById(R.id.tvSubStatus)
        tvFormat = view.findViewById(R.id.tvFormat)
        tvBuffer = view.findViewById(R.id.tvBuffer)
        tvStats = view.findViewById(R.id.tvStats)
        etIp = view.findViewById(R.id.etIp)
        tvLastIp = view.findViewById(R.id.tvLastIp)
        btnScan = view.findViewById(R.id.btnScan)
        btnDisconnect = view.findViewById(R.id.btnDisconnect)
        btnConnectIp = view.findViewById(R.id.btnConnectIp)
        serverList = view.findViewById(R.id.serverList)
        skeletonList = view.findViewById(R.id.skeletonList)
        actionLoading = view.findViewById(R.id.actionLoading)
        tvActionLoading = view.findViewById(R.id.tvActionLoading)
        btnModeClient = view.findViewById(R.id.btnModeClient)
        btnModeServer = view.findViewById(R.id.btnModeServer)
        cardManual = view.findViewById(R.id.cardManual)
        cardStatus = view.findViewById(R.id.cardStatus)
        modeRow = view.findViewById(R.id.modeRow)
        actionRow = view.findViewById(R.id.actionRow)
        tvServerTitle = view.findViewById(R.id.tvServerTitle)

        val last = AppSettings.lastIp
        tvLastIp.text = if (last.isBlank()) getString(R.string.play_last_ip_none) else getString(R.string.play_last_ip, last)

        val l: (AudioHub.HubState) -> Unit = { render(it) }
        listener = l
        AudioHub.addListener(l)

        serverMode = AppSettings.serverMode
        updateModeUi()

        Motion.pressable(btnScan, btnDisconnect, btnModeClient, btnModeServer, btnConnectIp)
        Motion.enter(listOf(cardStatus, modeRow, actionRow, cardManual))

        btnModeClient.setOnClickListener { switchMode(false) }
        btnModeServer.setOnClickListener { switchMode(true) }
        btnScan.setOnClickListener {
            if (serverMode) startListening() else startScan()
        }
        btnDisconnect.setOnClickListener { AudioHub.disconnect() }
        btnConnectIp.setOnClickListener { connectByIp() }
        etIp.setText(AppSettings.lastIp)

        if (serverMode) startListening()
    }

    private fun switchMode(toServer: Boolean) {
        if (toServer == serverMode) return
        AudioHub.disconnect()
        serverMode = toServer
        AppSettings.setServerMode(toServer)
        updateModeUi()
        if (toServer) startListening()
    }

    private fun updateModeUi() {
        val ctx = requireContext()
        val accent = ContextCompat.getColor(ctx, R.color.accent)
        val dim = ContextCompat.getColor(ctx, R.color.surface3)
        btnModeClient.backgroundTintList =
            ColorStateList.valueOf(if (serverMode) dim else accent)
        btnModeServer.backgroundTintList =
            ColorStateList.valueOf(if (serverMode) accent else dim)
        btnModeClient.setTextColor(
            ContextCompat.getColor(ctx, if (serverMode) R.color.text_dim else R.color.text)
        )
        btnModeServer.setTextColor(
            ContextCompat.getColor(ctx, if (serverMode) R.color.text else R.color.text_dim)
        )
        btnScan.text = if (serverMode) getString(R.string.play_btn_wait_start) else getString(R.string.play_btn_scan)
        cardManual.visibility = if (serverMode) View.GONE else View.VISIBLE
        tvServerTitle.visibility = if (serverMode) View.GONE else View.VISIBLE
        skeletonList.visibility = View.GONE
        serverList.visibility = if (serverMode) View.GONE else View.VISIBLE
        if (serverMode) {
            tvSub.text = getString(R.string.play_server_mode_tip)
        }
    }

    private fun startListening() {
        AudioHub.listen(42101)
        showLoading(true, getString(R.string.play_waiting))
        tvSub.text = getString(R.string.play_waiting)
        btnScan.isEnabled = false
        btnScan.text = getString(R.string.play_btn_waiting)
    }

    /** 手动 IP 连接：先做格式校验，再进入加载态。 */
    private fun connectByIp() {
        val ip = etIp.text.toString().trim()
        if (ip.isBlank()) {
            showFieldError(getString(R.string.play_ip_required))
            return
        }
        if (!ipPattern.matches(ip)) {
            showFieldError(getString(R.string.play_ip_invalid))
            return
        }
        etIp.setBackgroundResource(R.drawable.field_bg_ok)
        tvSub.setTextColor(ContextCompat.getColor(requireContext(), R.color.text_dim))
        showLoading(true, getString(R.string.play_connecting, ip))
        btnConnectIp.isEnabled = false
        btnConnectIp.text = getString(R.string.play_btn_connecting)
        AudioHub.connect(ip)
        etIp.postDelayed({
            if (isAdded) etIp.setBackgroundResource(R.drawable.field_bg)
        }, 1500)
    }

    private fun showFieldError(message: String) {
        etIp.setBackgroundResource(R.drawable.field_bg_error)
        Motion.shake(etIp)
        tvSub.text = message
        tvSub.setTextColor(ContextCompat.getColor(requireContext(), R.color.error))
        etIp.requestFocus()
        etIp.postDelayed({
            if (isAdded) {
                etIp.setBackgroundResource(R.drawable.field_bg)
                tvSub.setTextColor(ContextCompat.getColor(requireContext(), R.color.text_dim))
            }
        }, 1800)
    }

    private fun showLoading(show: Boolean, text: String = "") {
        actionLoading.visibility = if (show) View.VISIBLE else View.GONE
        if (show) {
            tvActionLoading.text = text
            Motion.fadeIn(actionLoading)
        }
    }

    override fun onDestroyView() {
        listener?.let { AudioHub.removeListener(it) }
        listener = null
        super.onDestroyView()
    }

    private fun render(state: AudioHub.HubState) {
        tvStatus.text = when (state.status) {
            NetClient.State.CONNECTED -> getString(R.string.play_state_connected)
            NetClient.State.SCANNING -> if (serverMode) getString(R.string.play_state_waiting) else getString(R.string.play_state_scanning)
            NetClient.State.ERROR -> getString(R.string.play_state_error)
            NetClient.State.IDLE -> getString(R.string.play_state_idle)
        }
        tvStatus.setTextColor(
            ContextCompat.getColor(
                requireContext(),
                when (state.status) {
                    NetClient.State.CONNECTED -> R.color.ok
                    NetClient.State.ERROR -> R.color.error
                    else -> R.color.text
                },
            ),
        )
        tvSub.text = state.detail
        tvSub.setTextColor(
            ContextCompat.getColor(
                requireContext(),
                if (state.status == NetClient.State.ERROR) R.color.error else R.color.text_dim,
            ),
        )
        tvFormat.text = state.format
        tvBuffer.text = if (state.bufferMs > 0) getString(R.string.play_buffer_ms, state.bufferMs) else getString(R.string.play_buffer_none)
        tvStats.text = buildString {
            append(getString(R.string.play_frames_received, state.frames))
            if (state.dropped > 0) append(getString(R.string.play_dropped, state.dropped))
        }

        // 按钮三态：空闲 / 加载中 / 结果
        when (state.status) {
            NetClient.State.CONNECTED -> {
                btnConnectIp.isEnabled = true
                btnConnectIp.text = getString(R.string.play_btn_connect)
                btnScan.isEnabled = serverMode.not()
                btnScan.text = if (serverMode) getString(R.string.play_btn_waiting) else getString(R.string.play_btn_scan)
                showLoading(false)
            }

            NetClient.State.SCANNING -> {
                btnScan.isEnabled = false
                btnScan.text = if (serverMode) getString(R.string.play_btn_waiting) else getString(R.string.play_btn_scanning)
                if (serverMode) {
                    showLoading(true, getString(R.string.play_waiting))
                }
            }

            NetClient.State.ERROR -> {
                btnConnectIp.isEnabled = true
                btnConnectIp.text = getString(R.string.play_btn_connect)
                btnScan.isEnabled = serverMode.not() && !scanning
                btnScan.text = if (serverMode) getString(R.string.play_btn_wait_start) else getString(R.string.play_btn_scan)
                showLoading(false)
            }

            NetClient.State.IDLE -> {
                btnConnectIp.isEnabled = true
                btnConnectIp.text = getString(R.string.play_btn_connect)
                if (!scanning) {
                    btnScan.isEnabled = true
                    btnScan.text = if (serverMode) getString(R.string.play_btn_wait_start) else getString(R.string.play_btn_scan)
                    showLoading(false)
                }
            }
        }

        if (state.status == NetClient.State.CONNECTED) {
            val last = AppSettings.lastIp
            if (last.isNotBlank()) tvLastIp.text = getString(R.string.play_last_ip, last)
        }
    }

    private fun startScan() {
        scanning = true
        btnScan.isEnabled = false
        btnScan.text = getString(R.string.play_btn_scanning)
        showLoading(true, getString(R.string.play_loading_scan))
        // 骨架屏先占位，避免列表区域空着像卡死
        skeletonList.visibility = View.VISIBLE
        Motion.fadeIn(skeletonList)
        serverList.visibility = View.GONE

        thread {
            val servers = AudioHub.scan()
            activity?.runOnUiThread {
                if (!isAdded) return@runOnUiThread
                scanning = false
                skeletonList.visibility = View.GONE
                serverList.visibility = View.VISIBLE
                btnScan.isEnabled = true
                btnScan.text = if (serverMode) getString(R.string.play_btn_wait_start) else getString(R.string.play_btn_scan)
                showLoading(false)
                renderServers(servers)
                if (servers.isEmpty()) {
                    tvSub.text = getString(R.string.play_no_servers)
                } else {
                    tvSub.text = getString(R.string.play_servers_found, servers.size)
                }
                tvSub.setTextColor(ContextCompat.getColor(requireContext(), R.color.text_dim))
            }
        }
    }

    private fun renderServers(servers: List<ServerInfo>) {
        serverList.removeAllViews()
        val dp = resources.displayMetrics.density
        servers.forEach { info ->
            val btn = MaterialButton(requireContext()).apply {
                text = "${info.name}　${info.host}"
                isAllCaps = false
                textSize = 15f
                gravity = Gravity.START or Gravity.CENTER_VERTICAL
                cornerRadius = (16 * dp).toInt()
                setTextColor(Color.WHITE)
                setBackgroundColor(ContextCompat.getColor(requireContext(), R.color.surface3))
                setPadding((18 * dp).toInt(), 0, (18 * dp).toInt(), 0)
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    (52 * dp).toInt(),
                ).apply { topMargin = (10 * dp).toInt() }
                setOnClickListener {
                    AudioHub.connect(info.host, info.port)
                    showLoading(true, getString(R.string.play_connecting, info.host))
                }
            }
            serverList.addView(btn)
            Motion.pressable(btn)
            if (Motion.reduce(requireContext())) return@forEach
            btn.alpha = 0f
            btn.translationY = 12 * dp
            btn.animate().alpha(1f).translationY(0f)
                .setStartDelay(serverList.childCount.toLong() * Motion.STAGGER_MS)
                .setDuration(Motion.ENTER_MS).start()
        }
    }
}
