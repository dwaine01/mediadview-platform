package com.mediaview.player

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.PixelFormat
import android.os.Build
import android.os.IBinder
import android.util.Log
import android.view.Gravity
import android.view.WindowManager

/**
 * Overlay Service - Launches MediAd View on top of everything.
 * Uses SYSTEM_ALERT_WINDOW permission to display over other apps.
 * This is how OptiSigns and other signage apps auto-start on boot.
 */
class OverlayService : Service() {

    companion object {
        const val CHANNEL_ID = "mediadview_overlay"
    }

    override fun onCreate() {
        super.onCreate()
        Log.i(PlayerApp.TAG, "OverlayService started")
        createNotificationChannel()
        startForeground(1, buildNotification())
        launchApp()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        launchApp()
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun launchApp() {
        try {
            val launchIntent = Intent(this, MainActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
                addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
            }
            startActivity(launchIntent)
            Log.i(PlayerApp.TAG, "App launched from OverlayService")
        } catch (e: Exception) {
            Log.e(PlayerApp.TAG, "Failed to launch app: ${e.message}")
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "MediAd View Player",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Digital signage player running"
                setShowBadge(false)
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(): Notification {
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        return builder
            .setContentTitle("MediAd View")
            .setContentText("Digital signage player running")
            .setSmallIcon(android.R.drawable.ic_menu_display)
            .build()
    }
}
