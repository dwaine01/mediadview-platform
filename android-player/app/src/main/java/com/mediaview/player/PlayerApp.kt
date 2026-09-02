package com.mediaview.player

import android.app.AlarmManager
import android.app.Application
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.SystemClock
import android.util.Log

class PlayerApp : Application() {
    companion object {
        const val TAG = "MediAdView"
        const val DEFAULT_SERVER_URL = "https://mediadview.com"
    }

    override fun onCreate() {
        super.onCreate()
        DeviceIdentity.migrateLegacy(this)
        Log.i(TAG, "Player ${BuildConfig.VERSION_NAME}; device=${DeviceIdentity.getDeviceId(this)}")
        installCrashRecovery()
        if (!DeviceIdentity.getBackendDeviceId(this).isNullOrBlank()) {
            runCatching { HeartbeatWorker.enqueuePeriodic(this) }
                .onFailure { Log.e(TAG, "Heartbeat schedule failed", it) }
        }
    }

    private fun installCrashRecovery() {
        val systemHandler = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            Log.e(TAG, "Uncaught player crash", throwable)
            runCatching {
                getSharedPreferences("player_crash", Context.MODE_PRIVATE).edit()
                    .putString("last_crash", "${throwable.javaClass.simpleName}: ${throwable.message}")
                    .putLong("last_crash_at", System.currentTimeMillis())
                    .commit()
                val launchIntent = packageManager.getLaunchIntentForPackage(packageName)?.apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                }
                if (launchIntent != null) {
                    val pendingIntent = PendingIntent.getActivity(
                        this,
                        9301,
                        launchIntent,
                        PendingIntent.FLAG_CANCEL_CURRENT or PendingIntent.FLAG_IMMUTABLE,
                    )
                    val alarm = getSystemService(Context.ALARM_SERVICE) as AlarmManager
                    alarm.set(
                        AlarmManager.ELAPSED_REALTIME,
                        SystemClock.elapsedRealtime() + 3_000,
                        pendingIntent,
                    )
                }
            }
            systemHandler?.uncaughtException(thread, throwable)
                ?: android.os.Process.killProcess(android.os.Process.myPid())
        }
    }
}