package com.mediaview.player

import android.app.Application
import android.util.Log

/**
 * MediaView Player Application class.
 * Handles global crash recovery.
 */
class PlayerApp : Application() {

    companion object {
        const val TAG = "MediaViewPlayer"
    }

    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "MediaView Player v${BuildConfig.VERSION_NAME} starting...")
        setupCrashRecovery()
    }

    /**
     * Global crash handler: restarts the app automatically on unhandled exceptions.
     * Critical for 24/7 digital signage operation.
     */
    private fun setupCrashRecovery() {
        val defaultHandler = Thread.getDefaultUncaughtExceptionHandler()

        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            Log.e(TAG, "CRASH DETECTED: ${throwable.message}", throwable)

            try {
                // Restart the main activity
                val intent = packageManager.getLaunchIntentForPackage(packageName)
                intent?.addFlags(
                    android.content.Intent.FLAG_ACTIVITY_NEW_TASK or
                    android.content.Intent.FLAG_ACTIVITY_CLEAR_TASK
                )
                startActivity(intent)

                // Kill current process
                android.os.Process.killProcess(android.os.Process.myPid())
            } catch (e: Exception) {
                Log.e(TAG, "Failed to restart after crash", e)
                defaultHandler?.uncaughtException(thread, throwable)
            }
        }
    }
}
