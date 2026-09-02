package com.mediaview.player

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        Log.i("MediAdView", "BootReceiver: ${intent.action}")
        if (!StartupPolicy.shouldAttemptLaunch(intent.action)) return

        // Best effort for AOSP/managed devices. Stock Android may block background
        // activity starts; the HOME intent filter remains the reliable kiosk path.
        runCatching {
            context.startActivity(Intent(context, MainActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            })
        }.onFailure { Log.w(PlayerApp.TAG, "Boot direct launch blocked: ${it.message}") }

        try {
            val work = OneTimeWorkRequestBuilder<BootWorker>()
                .setInitialDelay(5, TimeUnit.SECONDS)
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork(
                "mediaview-boot-recovery",
                ExistingWorkPolicy.REPLACE,
                work,
            )
            Log.i("MediAdView", "WorkManager jobs scheduled")
        } catch (e: Exception) {
            Log.e("MediAdView", "WorkManager failed: ${e.message}")
        }
    }
}
