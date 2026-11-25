package com.example.phoneaudiosink

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import androidx.core.content.ContextCompat

/**
 * 7 段图示均衡器视图：上下拖动频柱调节增益，范围 -12 ~ +12 dB。
 */
class EqView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {

    private val bands = AudioEffects.BANDS.size
    private val labels = EffectSettings.BAND_LABELS

    private var gains = IntArray(bands)

    var onGainChanged: ((IntArray) -> Unit)? = null

    private val barPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val trackPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val gridPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textAlign = Paint.Align.CENTER
        textSize = 11f * resources.displayMetrics.scaledDensity
    }
    private val thumbRect = RectF()

    private val accent = ContextCompat.getColor(context, R.color.accent)
    private val surface3 = ContextCompat.getColor(context, R.color.surface3)
    private val divider = ContextCompat.getColor(context, R.color.divider)
    private val textDim = ContextCompat.getColor(context, R.color.text_dim)

    private var activeBand = -1

    init {
        syncFromSettings()
    }

    fun syncFromSettings() {
        gains = EffectSettings.eqGains()
        invalidate()
    }

    private fun bandWidth(): Float = width.toFloat() / bands
    private val topPad: Float get() = 12f * resources.displayMetrics.density
    private val bottomPad: Float get() = 26f * resources.displayMetrics.density

    private fun plotTop(): Float = topPad
    private fun plotHeight(): Float = height - topPad - bottomPad

    private fun yForDb(db: Int): Float =
        plotTop() + plotHeight() * (12 - db) / 24f

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val bw = bandWidth()
        val radius = 6f * resources.displayMetrics.density

        // 背景网格（-12 / 0 / +12）
        gridPaint.color = divider
        gridPaint.strokeWidth = 1f
        for (db in intArrayOf(-12, -6, 0, 6, 12)) {
            canvas.drawLine(0f, yForDb(db), width.toFloat(), yForDb(db), gridPaint)
        }

        for (i in 0 until bands) {
            val cx = bw * (i + 0.5f)
            val barW = bw * 0.52f
            val left = cx - barW / 2f
            val right = cx + barW / 2f

            // 轨道
            trackPaint.color = surface3
            thumbRect.set(left, yForDb(12), right, yForDb(-12))
            canvas.drawRoundRect(thumbRect, radius, radius, trackPaint)

            // 已调部分
            val zeroY = yForDb(0)
            val gainY = yForDb(gains[i])
            barPaint.color = accent
            thumbRect.set(left, minOf(zeroY, gainY), right, maxOf(zeroY, gainY))
            if (thumbRect.height() > 1f) {
                canvas.drawRoundRect(thumbRect, radius, radius, barPaint)
            }

            // 滑块
            val thumbH = 14f * resources.displayMetrics.density
            val thumbLeft = left - 6f * resources.displayMetrics.density
            val thumbRight = right + 6f * resources.displayMetrics.density
            thumbRect.set(thumbLeft, gainY - thumbH / 2f, thumbRight, gainY + thumbH / 2f)
            barPaint.color = if (activeBand == i) accent else Color.WHITE
            canvas.drawRoundRect(thumbRect, radius, radius, barPaint)

            // 频段标签
            textPaint.color = textDim
            canvas.drawText(labels[i], cx, height - 8f * resources.displayMetrics.density, textPaint)
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                // 按下即锁定父容器（ScrollView）的拦截，避免调均衡器时整页跟着滚动
                parent?.requestDisallowInterceptTouchEvent(true)
                applyTouch(event)
                return true
            }
            MotionEvent.ACTION_MOVE -> {
                applyTouch(event)
                return true
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                parent?.requestDisallowInterceptTouchEvent(false)
                activeBand = -1
                EffectSettings.save()
                invalidate()
                return true
            }
        }
        return super.onTouchEvent(event)
    }

    /**
     * 按 x 定位频段、按 y 换算 dB。拖动时手指横向偏出也能继续控制原频段，
     * 不会跳到相邻频段。
     */
    private fun applyTouch(event: MotionEvent) {
        if (activeBand < 0) {
            val bw = bandWidth()
            activeBand = (event.x / bw).toInt().coerceIn(0, bands - 1)
        }
        val index = activeBand
        val db = dbForY(event.y)
        if (gains[index] != db) {
            gains[index] = db
            EffectSettings.setBand(index, db)
            onGainChanged?.invoke(gains.copyOf())
            invalidate()
        }
    }

    private fun dbForY(y: Float): Int {
        val ratio = (y - plotTop()) / plotHeight()
        val db = 12 - ratio * 24
        return db.toInt().coerceIn(-12, 12)
    }
}
