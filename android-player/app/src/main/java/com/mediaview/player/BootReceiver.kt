package com.mediaview.player

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Boot Receiver: Automatically starts MediaView Player when the device boots.
 * Works on Android TV, Fire TV, and standard Android devices.
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action
        Log.i(PlayerApp.TAG, "BootReceiver triggered: $action")

        if (action == Intent.ACTION_BOOT_COMPLETED ||
            action == "android.intent.action.QUICKBOOT_POWERON" ||
            action == "android.intent.action.REBOOT") {

            Log.i(PlayerApp.TAG, "Device booted - launching MediaView Player")

            val launchIntent = Intent(context, MainActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
            }

            // Small delay to ensure system is ready
            android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
                context.startActivity(launchIntent)
            }, 3000) // 3 second delay after boot
        }
    }
}
