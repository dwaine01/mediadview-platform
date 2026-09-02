package com.mediaview.player

import android.content.Context
import android.os.Environment
import android.os.StatFs
import android.util.Log
import androidx.work.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.NetworkInterface
import java.util.concurrent.TimeUnit

/**
 * Periodic fallback heartbeat (every 15 minutes, Android's supported minimum)
 * (restart, update, etc.).
 */
class HeartbeatWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        try {
            val ctx = applicationContext
            // Make sure the device is registered first
            if (!DeviceIdentity.isRegistered(ctx)) {
                DeviceRegistrar.registerIfNeeded(ctx)
            }
            val backendId = DeviceIdentity.getBackendDeviceId(ctx) ?: return@withContext Result.retry()
            if (!PlayerApi.hasInternet(ctx)) return@withContext Result.retry()

            val payload = JSONObject().apply {
                put("uptime_seconds",     android.os.SystemClock.elapsedRealtime() / 1000)
                put("free_storage_mb",    freeStorageMb())
                put("cached_media_count", 0)
                put("cpu_usage",          0)
                put("memory_usage",       memUsagePercent())
                put("ip_address",         localIp() ?: "")
                put("app_version",        BuildConfig.VERSION_NAME)
                put("app_version_code",   BuildConfig.VERSION_CODE)
                put("temperature",        0)
            }
            val res = PlayerApi.postJson(ctx, "/api/devices/$backendId/heartbeat", payload)
            Log.i(PlayerApp.TAG, "♥ Heartbeat OK · action=${res.optString("action")} screen=${res.optString("screen_id", "-")}")

            // === Handle server commands ===
            val cmd = res.optString("command", "")
            if (cmd == "restart") {
                Log.w(PlayerApp.TAG, "Server requested restart")
                restartPlayer(ctx)
            }

            // === Handle auto-update ===
            val update = res.optJSONObject("update_available")
            if (update != null) {
                val newName = update.optString("version_name")
                val newCode = update.optInt("version_code", 0)
                Log.i(PlayerApp.TAG, "⬆ Update available: $newName (code=$newCode) — scheduling download")
                AutoUpdater.tryUpdate(ctx, update)
            }

            Result.success()
        } catch (e: Exception) {
            Log.e(PlayerApp.TAG, "Heartbeat error: ${e.message}")
            Result.retry()
        }
    }

    private fun restartPlayer(ctx: Context) {
        try {
            val pm = ctx.packageManager
            val intent = pm.getLaunchIntentForPackage(ctx.packageName)?.apply {
                addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK or android.content.Intent.FLAG_ACTIVITY_CLEAR_TASK)
            }
            if (intent != null) ctx.startActivity(intent)
            android.os.Process.killProcess(android.os.Process.myPid())
        } catch (_: Exception) {}
    }

    private fun freeStorageMb(): Long {
        return try {
            val stat = StatFs(Environment.getDataDirectory().path)
            (stat.availableBytes / 1024 / 1024)
        } catch (_: Exception) { 0L }
    }

    private fun memUsagePercent(): Int {
        return try {
            val rt = Runtime.getRuntime()
            val used = rt.totalMemory() - rt.freeMemory()
            ((used.toDouble() / rt.maxMemory()) * 100).toInt()
        } catch (_: Exception) { 0 }
    }

    private fun localIp(): String? {
        return try {
            NetworkInterface.getNetworkInterfaces().toList().flatMap { it.inetAddresses.toList() }
                .firstOrNull { !it.isLoopbackAddress && it.hostAddress?.contains(":") == false }
                ?.hostAddress
        } catch (_: Exception) { null }
    }

    companion object {
        const val UNIQUE_NAME = "mediaview-heartbeat"
        const val INTERVAL_MIN = 15L

        fun enqueuePeriodic(ctx: Context) {
            val req = PeriodicWorkRequestBuilder<HeartbeatWorker>(INTERVAL_MIN, TimeUnit.MINUTES)
                .setConstraints(Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build())
                .setBackoffCriteria(BackoffPolicy.LINEAR, 30, TimeUnit.SECONDS)
                .addTag("mediaview-bg")
                .build()
            WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(
                UNIQUE_NAME, ExistingPeriodicWorkPolicy.KEEP, req
            )
            // Also run one immediately
            val immediate = OneTimeWorkRequestBuilder<HeartbeatWorker>()
                .setConstraints(Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            WorkManager.getInstance(ctx).enqueueUniqueWork(
                "mediaview-heartbeat-first", ExistingWorkPolicy.KEEP, immediate
            )
        }
    }
}
