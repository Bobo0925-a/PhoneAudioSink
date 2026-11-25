package com.example.phoneaudiosink

import android.content.Context
import android.content.res.Configuration
import android.os.LocaleList
import java.util.Locale

/**
 * 应用内语言：不依赖系统语言，自己覆盖 Configuration。
 *
 * - AppSettings.language 为空表示跟随系统；
 * - Activity 在 attachBaseContext 里包一层，资源就会按目标语言解析；
 * - 后台线程（网络状态文案）用 [Str] 取字符串，同样走这套覆盖。
 */
object LocaleHelper {

    fun wrap(base: Context): Context {
        val tag = AppSettings.language
        if (tag.isBlank()) return base
        val locale = Locale.forLanguageTag(tag)
        Locale.setDefault(locale)
        val config = Configuration(base.resources.configuration)
        config.setLocales(LocaleList(locale))
        return base.createConfigurationContext(config)
    }

    fun string(base: Context, id: Int, vararg args: Any): String =
        wrap(base).getString(id, *args)
}

/** 供非 UI 层（网络回调、状态默认值）取多语言文本。 */
object Str {

    lateinit var app: Context
        private set

    fun attach(context: Context) {
        app = context.applicationContext
    }

    fun s(id: Int, vararg args: Any): String = LocaleHelper.string(app, id, *args)
}
