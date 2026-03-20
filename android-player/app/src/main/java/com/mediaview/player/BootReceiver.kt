package com.mediaview.player

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log

/**
 * Boot Receiver: Launches MediAd View after device boot.
 * Uses multiple retry attempts with increasing delays for cold boot reliability.
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action
        Log.i(PlayerApp.TAG, "BootReceiver triggered: $action")

        if (action == Intent.ACTION_BOOT_COMPLETED ||
            action == "android.intent.action.QUICKBOOT_POWERON" ||
            action == "android.intent.action.REBOOT") {

            Log.i(PlayerApp.TAG, "Device booted - scheduling MediAd View launch")

            // Start overlay service
            val serviceIntent = Intent(context, OverlayService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(serviceIntent)
            } else {
                context.startService(serviceIntent)
            }

            // Launch app with multiple retries at different delays
            val handler = Handler(Looper.getMainLooper())
            val delays = longArrayOf(3000, 8000, 15000, 30000, 60000) // 3s, 8s, 15s, 30s, 60s

            for (delay in delays) {
                handler.postDelayed({
                    try {
                        val launchIntent = Intent(context, MainActivity::class.java).apply {
                            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                            addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
                        }
                        context.startActivity(launchIntent)
                        Log.i(PlayerApp.TAG, "App launched at delay ${delay}ms")
                    } catch (e: Exception) {
                        Log.e(PlayerApp.TAG, "Launch failed at ${delay}ms: ${e.message}")
                    }
                }, delay)
            }

            // Also set an AlarmManager as backup (survives process death)
            try {
                val alarmIntent = Intent(context, MainActivity::class.java).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                val pendingIntent = PendingIntent.getActivity(
                    context, 0, alarmIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                )
                val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
                alarmManager.setExactAndAllowWhileIdle(
                    AlarmManager.ELAPSED_REALTIME_WAKEUP,
                    SystemClock.elapsedRealtime() + 10000, // 10 seconds
                    pendingIntent
                )
                Log.i(PlayerApp.TAG, "AlarmManager backup set for 10s")
            } catch (e: Exception) {
                Log.e(PlayerApp.TAG, "AlarmManager failed: ${e.message}")
            }
        }
    }
}
