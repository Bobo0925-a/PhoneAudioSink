package com.example.phoneaudiosink

import android.content.res.ColorStateList
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatDelegate
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import com.google.android.material.button.MaterialButton
import androidx.appcompat.widget.SwitchCompat

/** 设置页：缓冲档位、主题、自动重连、链路心跳、恢复默认。 */
class SettingsFragment : Fragment(R.layout.fragment_settings) {

    private lateinit var tierRow: LinearLayout
    private lateinit var hint: TextView
    private val tierButtons = mutableListOf<MaterialButton>()

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        tierRow = view.findViewById(R.id.bufferTierRow)
        hint = view.findViewById(R.id.tvBufferTierHint)

        buildTiers()

        val swLight = view.findViewById<SwitchCompat>(R.id.swLight)
        val swAuto = view.findViewById<SwitchCompat>(R.id.swAutoReconnect)
        val swHeartbeat = view.findViewById<SwitchCompat>(R.id.swHeartbeat)

        swLight.isChecked = AppSettings.lightMode
        swAuto.isChecked = AppSettings.autoReconnect
        swHeartbeat.isChecked = AppSettings.heartbeat

        val swReduce = view.findViewById<SwitchCompat>(R.id.swReduceMotion)
        swReduce.isChecked = AppSettings.reduceMotion
        swReduce.setOnCheckedChangeListener { _, checked -> AppSettings.setReduceMotion(checked) }

        Motion.enterChildren(view)

        swLight.setOnCheckedChangeListener { _, checked ->
            AppSettings.setLightMode(checked)
            AppCompatDelegate.setDefaultNightMode(
                if (checked) AppCompatDelegate.MODE_NIGHT_NO else AppCompatDelegate.MODE_NIGHT_YES,
            )
            activity?.recreate()
        }
        swAuto.setOnCheckedChangeListener { _, checked -> AppSettings.setAutoReconnect(checked) }
        swHeartbeat.setOnCheckedChangeListener { _, checked -> AppSettings.setHeartbeat(checked) }

        view.findViewById<MaterialButton>(R.id.btnRestoreDefaults).setOnClickListener {
            AppSettings.resetAll()
            applyTheme()
            activity?.recreate()
        }
        Motion.pressable(view.findViewById(R.id.btnRestoreDefaults))
    }

    private fun applyTheme() {
        AppCompatDelegate.setDefaultNightMode(
            if (AppSettings.lightMode) AppCompatDelegate.MODE_NIGHT_NO
            else AppCompatDelegate.MODE_NIGHT_YES,
        )
    }

    private fun buildTiers() {
        tierRow.removeAllViews()
        tierButtons.clear()
        val dp = resources.displayMetrics.density
        AppSettings.BUFFER_TIERS.forEachIndexed { index, ms ->
            val btn = MaterialButton(requireContext()).apply {
                text = AppSettings.BUFFER_LABELS[index]
                isAllCaps = false
                textSize = 12f
                gravity = Gravity.CENTER
                cornerRadius = (16 * dp).toInt()
                minWidth = 0
                minimumWidth = 0
                insetTop = 0
                insetBottom = 0
                setPadding(0, 0, 0, 0)
                layoutParams = LinearLayout.LayoutParams(0, (48 * dp).toInt(), 1f).apply {
                    if (index > 0) marginStart = (8 * dp).toInt()
                }
                setOnClickListener {
                    AppSettings.setBufferMs(ms)
                    AudioHub.player.applyBufferSetting()
                    refreshTiers()
                }
            }
            Motion.pressable(btn)
            tierButtons.add(btn)
            tierRow.addView(btn)
        }
        refreshTiers()
    }

    private fun refreshTiers() {
        val accent = ContextCompat.getColor(requireContext(), R.color.accent)
        val surface = ContextCompat.getColor(requireContext(), R.color.surface3)
        AppSettings.BUFFER_TIERS.forEachIndexed { index, ms ->
            val selected = ms == AppSettings.bufferMs
            tierButtons.getOrNull(index)?.backgroundTintList =
                ColorStateList.valueOf(if (selected) accent else surface)
        }
        hint.text = when (AppSettings.bufferMs) {
            120 -> "当前 120 ms（低延迟，弱网易爆音）"
            400 -> "当前 400 ms（抗抖动，延迟略高）"
            else -> "当前 250 ms（平衡）"
        }
    }
}
