package com.mediaview.player

import android.content.Context
import android.content.Intent
import android.util.Log
import androidx.work.Worker
import androidx.work.WorkerParameters

/**
 * WorkManager Worker that launches the app.
 * WorkManager survives Android's boot restrictions - this is how OptiSigns does it.
 */
class BootWorker(context: Context, params: WorkerParameters) : Worker(context, params) {
    override fun doWork(): Result {
        return try {
            val intent = Intent(applicationContext, MainActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            }
            applicationContext.startActivity(intent)
            Log.i("MediAdView", "BootWorker launched app successfully")
            Result.success()
        } catch (e: Exception) {
            Log.e("MediAdView", "BootWorker failed: ${e.message}")
            Result.retry()
        }
    }
}
