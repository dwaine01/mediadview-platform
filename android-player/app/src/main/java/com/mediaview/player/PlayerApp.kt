package com.mediaview.player

import android.app.Application
import android.util.Log
import kotlinx.coroutines.launch

/**
 * MediAd View Player Application class.
 * Handles global crash recovery and app initialization.
 * v2.0 - Optimized for Colorlight A40 + Android TV
 */
class PlayerApp : Application() {

    companion object {
        const val TAG = "MediAdView"
        // Default backend URL — can be overridden at runtime via SharedPreferences ("server_url")
        const val DEFAULT_SERVER_URL = "https://mediadview.com"
    }

    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "========================================")
        Log.i(TAG, "MediAd View Player v${BuildConfig.VERSION_NAME} (build ${BuildConfig.VERSION_CODE})")
        Log.i(TAG, "Device: ${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL}")
        Log.i(TAG, "Android: ${android.os.Build.VERSION.RELEASE} (SDK ${android.os.Build.VERSION.SDK_INT})")
        Log.i(TAG, "device_id: ${DeviceIdentity.getDeviceId(this)}")
        Log.i(TAG, "paired: ${DeviceIdentity.isRegistered(this)}")
        Log.i(TAG, "========================================")
        setupCrashRecovery()

        // Schedule heartbeat ONLY if device is paired
        if (DeviceIdentity.isRegistered(this)) {
            try { HeartbeatWorker.enqueuePeriodic(this) }
            catch (e: Exception) { Log.e(TAG, "Failed to enqueue heartbeat: ${e.message}") }
        }
    }

    /**
     * Global crash handler: restarts the app automatically on unhandled exceptions.
     * Critical for 24/7 digital signage operation.
     * Uses multiple recovery strategies:
     * 1. Restart main activity
     * 2. Kill and restart process
     */
    private fun setupCrashRecovery() {
        val defaultHandler = Thread.getDefaultUncaughtExceptionHandler()

        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            Log.e(TAG, "CRASH DETECTED: ${throwable.message}", throwable)

            try {
                // Strategy 1: Restart the main activity
                val intent = packageManager.getLaunchIntentForPackage(packageName)
                intent?.addFlags(
                    android.content.Intent.FLAG_ACTIVITY_NEW_TASK or
                    android.content.Intent.FLAG_ACTIVITY_CLEAR_TASK
                )
                startActivity(intent)

                // Kill current process after a short delay
                Thread.sleep(500)
                android.os.Process.killProcess(android.os.Process.myPid())
            } catch (e: Exception) {
                Log.e(TAG, "Failed to restart after crash", e)
                defaultHandler?.uncaughtException(thread, throwable)
            }
        }
    }
}
