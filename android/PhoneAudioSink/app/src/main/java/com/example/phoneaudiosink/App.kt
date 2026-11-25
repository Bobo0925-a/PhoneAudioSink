package com.example.phoneaudiosink

import android.app.Application
import androidx.appcompat.app.AppCompatDelegate

/** 应用入口：初始化设置与共享音频中心，并在启动时套用主题。 */
class App : Application() {

    override fun onCreate() {
        super.onCreate()
        initSettings(this)
        AppCompatDelegate.setDefaultNightMode(
            if (AppSettings.lightMode) AppCompatDelegate.MODE_NIGHT_NO
            else AppCompatDelegate.MODE_NIGHT_YES,
        )
        AudioHub.init(this)
    }
}
