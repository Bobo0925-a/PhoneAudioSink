package com.example.phoneaudiosink

import android.os.Bundle
import android.view.View
import android.widget.TextView
import androidx.fragment.app.Fragment

/** 关于页：版本、链路参数与使用步骤。 */
class AboutFragment : Fragment(R.layout.fragment_about) {

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        val version = try {
            requireContext().packageManager.getPackageInfo(requireContext().packageName, 0).versionName
        } catch (e: Exception) {
            "2.0"
        }
        view.findViewById<TextView>(R.id.tvVersion).text =
            getString(R.string.about_version, version)
        Motion.enterChildren(view)
    }
}
