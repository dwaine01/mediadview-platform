package com.mediaview.player

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.util.Log
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

/**
 * Second boot receiver (like OptiSigns' RescheduleReceiver).
 * Listens to CONNECTIVITY_CHANGE + BOOT_COMPLETED + TIME_SET.
 * Double chance to launch the app.
 */
class NetworkBootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        Log.i("MediAdView", "NetworkBootReceiver: ${intent.action}")

        if (intent.action == Intent.ACTION_BOOT_COMPLETED ||
            intent.action == "android.net.conn.CONNECTIVITY_CHANGE" ||
            intent.action == Intent.ACTION_TIME_CHANGED ||
            intent.action == Intent.ACTION_TIMEZONE_CHANGED) {

            // Launch via WorkManager
            try {
                val work = OneTimeWorkRequestBuilder<BootWorker>()
                    .setInitialDelay(10, TimeUnit.SECONDS)
                    .build()
                WorkManager.getInstance(context).enqueue(work)
                Log.i("MediAdView", "NetworkBootReceiver: WorkManager job scheduled")
            } catch (e: Exception) {
                Log.e("MediAdView", "NetworkBootReceiver WorkManager failed: ${e.message}")
            }

            // Also direct launch as backup
            Handler(Looper.getMainLooper()).postDelayed({
                try {
                    context.startActivity(Intent(context, MainActivity::class.java).apply {
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                    })
                } catch (e: Exception) {
                    Log.e("MediAdView", "NetworkBootReceiver direct launch failed")
                }
            }, 12000)
        }
    }
}
