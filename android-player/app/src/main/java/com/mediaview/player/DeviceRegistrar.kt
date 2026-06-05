package com.mediaview.player

import android.content.Context
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject

/**
 * Registers the device with the backend on first boot.
 * Idempotent: skips if already registered.
 */
object DeviceRegistrar {

    suspend fun registerIfNeeded(ctx: Context): JSONObject? = withContext(Dispatchers.IO) {
        if (DeviceIdentity.isRegistered(ctx)) {
            Log.i(PlayerApp.TAG, "Device already registered (backend_id=${DeviceIdentity.getBackendDeviceId(ctx)})")
            return@withContext null
        }
        if (!PlayerApi.hasInternet(ctx)) {
            Log.w(PlayerApp.TAG, "No internet, skipping registration for now")
            return@withContext null
        }
        val payload = JSONObject().apply {
            put("device_model", DeviceIdentity.deviceModel())
            put("device_name", "MediAd View A40 — ${android.os.Build.MODEL}")
            put("os_version",  DeviceIdentity.osVersion())
            put("app_version", BuildConfig.VERSION_NAME)
            put("resolution",  "")
            put("client_uuid", DeviceIdentity.getDeviceId(ctx))
        }
        try {
            val res = PlayerApi.postJson(ctx, "/api/devices/register", payload)
            val backendId = res.optString("device_id")
            val code = res.optString("activation_code", null)
            if (backendId.isNotBlank()) {
                DeviceIdentity.markRegistered(ctx, backendId, code)
                Log.i(PlayerApp.TAG, "✓ Device registered: backend_id=$backendId activation_code=$code")
                return@withContext res
            }
        } catch (e: Exception) {
            Log.e(PlayerApp.TAG, "Registration failed: ${e.message}")
        }
        null
    }
}
