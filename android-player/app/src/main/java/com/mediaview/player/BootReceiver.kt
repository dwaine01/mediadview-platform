package com.mediaview.player

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.util.Log

/**
 * Boot Receiver: Launches MediAd View after device boot.
 * Uses ONLY startActivity() - no foreground service (which Android 15+ blocks on boot).
 * This is the same approach OptiSigns and Yodeck use.
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED ||
            intent.action == "android.intent.action.QUICKBOOT_POWERON" ||
            intent.action == "android.intent.action.REBOOT") {

            Log.i("MediAdView", "Boot detected - launching app")

            val handler = Handler(Looper.getMainLooper())

            // Launch at 3s, 8s, 15s, 30s, 60s - only startActivity, no service
            longArrayOf(3000, 8000, 15000, 30000, 60000).forEach { delay ->
                handler.postDelayed({
                    try {
                        val launchIntent = Intent(context, MainActivity::class.java).apply {
                            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                        }
                        context.startActivity(launchIntent)
                        Log.i("MediAdView", "App launched at ${delay}ms")
                    } catch (e: Exception) {
                        Log.e("MediAdView", "Launch failed at ${delay}ms: ${e.message}")
                    }
                }, delay)
            }
        }
    }
}
