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

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        Log.i("MediAdView", "BootReceiver: ${intent.action}")

        // Method 1: Direct launch with retries
        val handler = Handler(Looper.getMainLooper())
        longArrayOf(3000, 8000, 15000, 30000, 60000).forEach { delay ->
            handler.postDelayed({
                try {
                    context.startActivity(Intent(context, MainActivity::class.java).apply {
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                    })
                } catch (e: Exception) {
                    Log.e("MediAdView", "Launch failed at ${delay}ms")
                }
            }, delay)
        }

        // Method 2: WorkManager (survives everything - like OptiSigns)
        try {
            val work = OneTimeWorkRequestBuilder<BootWorker>()
                .setInitialDelay(5, TimeUnit.SECONDS)
                .build()
            WorkManager.getInstance(context).enqueue(work)

            val work2 = OneTimeWorkRequestBuilder<BootWorker>()
                .setInitialDelay(20, TimeUnit.SECONDS)
                .build()
            WorkManager.getInstance(context).enqueue(work2)

            val work3 = OneTimeWorkRequestBuilder<BootWorker>()
                .setInitialDelay(45, TimeUnit.SECONDS)
                .build()
            WorkManager.getInstance(context).enqueue(work3)

            Log.i("MediAdView", "WorkManager jobs scheduled")
        } catch (e: Exception) {
            Log.e("MediAdView", "WorkManager failed: ${e.message}")
        }
    }
}
