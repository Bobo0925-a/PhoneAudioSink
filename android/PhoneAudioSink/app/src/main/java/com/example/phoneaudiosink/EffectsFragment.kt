package com.example.phoneaudiosink

import android.content.res.ColorStateList
import android.os.Bundle
import android.view.View
import android.widget.LinearLayout
import android.widget.SeekBar
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import com.google.android.material.button.MaterialButton
import androidx.appcompat.widget.SwitchCompat

/** 音效页：场景预设、7 段图示均衡、虚拟低音、低频增强、输出增益。 */
class EffectsFragment : Fragment(R.layout.fragment_effects) {

    private lateinit var presetRow: LinearLayout
    private lateinit var eqView: EqView
    private lateinit var swBass: SwitchCompat
    private lateinit var swVirtual: SwitchCompat
    private lateinit var sbBass: SeekBar
    private lateinit var sbGain: SeekBar
    private lateinit var tvBassValue: TextView
    private lateinit var tvGainValue: TextView

    private val presetButtons = mutableListOf<MaterialButton>()

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        presetRow = view.findViewById(R.id.presetRow)
        eqView = view.findViewById(R.id.eqView)
        swVirtual = view.findViewById(R.id.swVirtualBass)
        sbBass = view.findViewById(R.id.sbBass)
        sbGain = view.findViewById(R.id.sbGain)
        tvBassValue = view.findViewById(R.id.tvBassValue)
        tvGainValue = view.findViewById(R.id.tvGainValue)

        buildPresets()
        bindSliders()
        Motion.enterChildren(view)

        swVirtual.isChecked = EffectSettings.virtualBass()
        swVirtual.setOnCheckedChangeListener { _, checked ->
            EffectSettings.setVirtualBass(checked)
            EffectSettings.save()
        }

        view.findViewById<MaterialButton>(R.id.btnResetEq).setOnClickListener {
            EffectSettings.reset()
            EffectSettings.save()
            refreshAll()
        }
        view.findViewById<MaterialButton>(R.id.btnSavePreset).setOnClickListener {
            EffectSettings.save()
            val hint = view.findViewById<TextView>(R.id.tvEqHint)
            hint.text = getString(R.string.effects_eq_saved)
            hint.postDelayed({ hint.text = getString(R.string.effects_eq_hint) }, 1600)
        }
        Motion.pressable(
            view.findViewById(R.id.btnResetEq),
            view.findViewById(R.id.btnSavePreset),
        )

        eqView.onGainChanged = { highlightPreset(EffectSettings.presetId) }
        refreshAll()
    }

    private fun buildPresets() {
        presetRow.removeAllViews()
        presetButtons.clear()
        val dp = resources.displayMetrics.density
        val labels = EffectSettings.presetLabels()
        for (id in 1 until labels.size) {
            val btn = MaterialButton(requireContext()).apply {
                text = labels[id]
                isAllCaps = false
                textSize = 13f
                cornerRadius = (16 * dp).toInt()
                minWidth = 0
                minimumWidth = 0
                insetTop = 0
                insetBottom = 0
                setPadding((12 * dp).toInt(), 0, (12 * dp).toInt(), 0)
                layoutParams = LinearLayout.LayoutParams(0, (42 * dp).toInt(), 1f).apply {
                    if (id > 1) marginStart = (8 * dp).toInt()
                }
                setOnClickListener {
                    EffectSettings.applyPreset(id)
                    EffectSettings.save()
                    refreshAll()
                }
            }
            presetButtons.add(btn)
            Motion.pressable(btn)
            presetRow.addView(btn)
        }
        highlightPreset(EffectSettings.presetId)
    }

    private fun highlightPreset(presetId: Int) {
        val accent = ContextCompat.getColor(requireContext(), R.color.accent)
        val surface = ContextCompat.getColor(requireContext(), R.color.surface3)
        presetButtons.forEachIndexed { index, btn ->
            val selected = (index + 1) == presetId
            btn.backgroundTintList = ColorStateList.valueOf(if (selected) accent else surface)
        }
    }

    private fun bindSliders() {
        sbBass.progress = EffectSettings.bassDb()
        sbGain.progress = EffectSettings.gainDb()
        updateBassLabel()
        updateGainLabel()

        sbBass.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(bar: SeekBar?, progress: Int, fromUser: Boolean) {
                EffectSettings.setBassDb(progress.coerceAtMost(12))
                updateBassLabel()
            }

            override fun onStartTrackingTouch(bar: SeekBar?) = Unit

            override fun onStopTrackingTouch(bar: SeekBar?) {
                EffectSettings.save()
            }
        })

        sbGain.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(bar: SeekBar?, progress: Int, fromUser: Boolean) {
                EffectSettings.setGainDb(progress.coerceAtMost(12))
                updateGainLabel()
            }

            override fun onStartTrackingTouch(bar: SeekBar?) = Unit

            override fun onStopTrackingTouch(bar: SeekBar?) {
                EffectSettings.save()
            }
        })
    }

    private fun updateBassLabel() {
        tvBassValue.text = "+${EffectSettings.bassDb()} dB"
    }

    private fun updateGainLabel() {
        tvGainValue.text = "+${EffectSettings.gainDb()} dB"
    }

    private fun refreshAll() {
        eqView.syncFromSettings()
        swVirtual.isChecked = EffectSettings.virtualBass()
        sbBass.progress = EffectSettings.bassDb()
        sbGain.progress = EffectSettings.gainDb()
        updateBassLabel()
        updateGainLabel()
        highlightPreset(EffectSettings.presetId)
    }
}
