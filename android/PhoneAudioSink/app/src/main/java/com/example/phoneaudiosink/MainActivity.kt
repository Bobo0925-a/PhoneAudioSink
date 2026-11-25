package com.example.phoneaudiosink

import android.content.Context
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.fragment.app.Fragment
import com.google.android.material.bottomnavigation.BottomNavigationView

/**
 * 主界面：底部四页 Tab（播放 / 音效 / 设置 / 关于）。
 * 这里覆盖 attachBaseContext 让应用内选定的语言生效（早于资源加载）。
 */
class MainActivity : AppCompatActivity() {

    private lateinit var bottomNav: BottomNavigationView

    private val playFragment = PlayFragment()
    private val effectsFragment = EffectsFragment()
    private val settingsFragment = SettingsFragment()
    private val aboutFragment = AboutFragment()

    override fun attachBaseContext(newBase: Context) {
        super.attachBaseContext(LocaleHelper.wrap(newBase))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        bottomNav = findViewById(R.id.bottomNav)

        bottomNav.setOnItemSelectedListener { item ->
            when (item.itemId) {
                R.id.tab_play -> show(playFragment)
                R.id.tab_effects -> show(effectsFragment)
                R.id.tab_settings -> show(settingsFragment)
                R.id.tab_about -> show(aboutFragment)
            }
            true
        }

        if (savedInstanceState == null) {
            bottomNav.selectedItemId = R.id.tab_play
            show(playFragment)
        }
    }

    private fun show(fragment: Fragment) {
        val tx = supportFragmentManager.beginTransaction()
        if (Motion.reduce(this)) {
            tx.setCustomAnimations(0, 0)
        } else {
            tx.setCustomAnimations(
                R.anim.slide_fade_in, R.anim.slide_fade_out,
                R.anim.slide_fade_in, R.anim.slide_fade_out,
            )
        }
        tx.replace(R.id.fragmentHost, fragment).commitAllowingStateLoss()
    }

    override fun onDestroy() {
        if (isFinishing) {
            AudioHub.disconnect()
        }
        super.onDestroy()
    }
}
