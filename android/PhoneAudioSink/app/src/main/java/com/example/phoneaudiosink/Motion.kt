package com.example.phoneaudiosink

import android.animation.ObjectAnimator
import android.content.Context
import android.provider.Settings
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.animation.DecelerateInterpolator
import android.view.animation.OvershootInterpolator

/**
 * 统一的动效参数与工具：
 * - 点按反馈 130ms（快）
 * - 小控件 240ms
 * - 入场 280ms、逐项延迟 60ms
 * - 全场尊重「减弱动态效果」：App 内开关或系统 Animator 时长缩放为 0 时直接静止
 */
object Motion {

    const val FEEDBACK_MS = 130L
    const val SMALL_MS = 240L
    const val ENTER_MS = 280L
    const val STAGGER_MS = 60L

    fun reduce(context: Context): Boolean {
        if (AppSettings.reduceMotion) return true
        return try {
            Settings.Global.getFloat(
                context.contentResolver,
                Settings.Global.ANIMATOR_DURATION_SCALE,
                1f,
            ) == 0f
        } catch (_: Exception) {
            false
        }
    }

    fun dp(context: Context, value: Int): Int =
        (context.resources.displayMetrics.density * value).toInt()

    /** 按压反馈：按下轻微收缩，抬起带一点回弹。 */
    fun pressable(vararg views: View) {
        views.forEach { view ->
            if (reduce(view.context)) return@forEach
            view.setOnTouchListener { v, event ->
                when (event.actionMasked) {
                    MotionEvent.ACTION_DOWN ->
                        v.animate().scaleX(0.96f).scaleY(0.96f)
                            .setDuration(FEEDBACK_MS)
                            .setInterpolator(DecelerateInterpolator())
                            .start()

                    MotionEvent.ACTION_UP,
                    MotionEvent.ACTION_CANCEL,
                    -> v.animate().scaleX(1f).scaleY(1f)
                        .setDuration(FEEDBACK_MS)
                        .setInterpolator(OvershootInterpolator(1.1f))
                        .start()
                }
                false
            }
        }
    }

    /** 逐项错峰淡入上移，而不是整屏一起出现。 */
    fun enter(views: List<View>, staggerMs: Long = STAGGER_MS) {
        if (views.isEmpty()) return
        val context = views.first().context
        if (reduce(context)) {
            views.forEach {
                it.alpha = 1f
                it.translationY = 0f
            }
            return
        }
        val offset = dp(context, 18).toFloat()
        views.forEachIndexed { index, view ->
            view.alpha = 0f
            view.translationY = offset
            view.animate().alpha(1f).translationY(0f)
                .setStartDelay(index * staggerMs)
                .setDuration(ENTER_MS)
                .setInterpolator(DecelerateInterpolator())
                .start()
        }
    }

    /** 对整个页面（ScrollView 内第一层容器）逐项入场。 */
    fun enterChildren(root: View, staggerMs: Long = STAGGER_MS) {
        val container = (root as? ViewGroup)?.getChildAt(0) as? ViewGroup ?: return
        val children = ArrayList<View>(container.childCount)
        for (i in 0 until container.childCount) children.add(container.getChildAt(i))
        enter(children, staggerMs)
    }

    /** 输入错误时的左右抖动，幅度 10dp、320ms。 */
    fun shake(view: View) {
        if (reduce(view.context)) return
        val d = dp(view.context, 8).toFloat()
        ObjectAnimator.ofFloat(
            view, "translationX", 0f, -d, d * 0.8f, -d * 0.55f, d * 0.35f, 0f,
        ).setDuration(320).start()
    }

    /** 轻量出现：用于加载条、骨架屏这类临时元素。 */
    fun fadeIn(view: View) {
        if (reduce(view.context)) {
            view.alpha = 1f
            return
        }
        view.alpha = 0f
        view.animate().alpha(1f).setDuration(SMALL_MS).start()
    }
}
