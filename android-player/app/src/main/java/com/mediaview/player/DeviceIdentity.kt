package com.mediaview.player

import android.content.Context
import android.content.SharedPreferences
import android.os.Build
import android.provider.Settings
import android.util.Log
import java.util.UUID

/**
 * Manages the persistent device_id and other identity data.
 *
 * Stores the device_id in SharedPreferences so it survives reboots.
 * Generates a stable UUID on first boot (preferring ANDROID_ID when available).
 */
object DeviceIdentity {
    private const val PREFS = "mediaview_identity"
    private const val KEY_DEVICE_ID  = "device_id"
    private const val KEY_REGISTERED = "registered"
    private const val KEY_BACKEND_ID = "backend_device_id"   // the id returned by /devices/register
    private const val KEY_ACTIVATION = "activation_code"

    private fun prefs(ctx: Context): SharedPreferences =
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    /** Returns a stable per-device UUID. Persisted on first call. */
    fun getDeviceId(ctx: Context): String {
        val p = prefs(ctx)
        val cur = p.getString(KEY_DEVICE_ID, null)
        if (cur != null) return cur
        // Prefer ANDROID_ID if available (more stable across factory resets only)
        val androidId = try {
            Settings.Secure.getString(ctx.contentResolver, Settings.Secure.ANDROID_ID)
        } catch (e: Exception) { null }
        val generated = if (!androidId.isNullOrBlank() && androidId != "9774d56d682e549c") {
            "mv-$androidId"
        } else {
            "mv-${UUID.randomUUID().toString().replace("-", "").take(16)}"
        }
        p.edit().putString(KEY_DEVICE_ID, generated).apply()
        Log.i(PlayerApp.TAG, "DeviceIdentity: new device_id=$generated")
        return generated
    }

    fun getBackendDeviceId(ctx: Context): String? =
        prefs(ctx).getString(KEY_BACKEND_ID, null)

    fun isRegistered(ctx: Context): Boolean =
        prefs(ctx).getBoolean(KEY_REGISTERED, false)

    fun markRegistered(ctx: Context, backendId: String, activationCode: String?) {
        prefs(ctx).edit()
            .putBoolean(KEY_REGISTERED, true)
            .putString(KEY_BACKEND_ID, backendId)
            .putString(KEY_ACTIVATION, activationCode)
            .apply()
        Log.i(PlayerApp.TAG, "DeviceIdentity: marked as registered (backend_id=$backendId)")
    }

    fun getActivationCode(ctx: Context): String? =
        prefs(ctx).getString(KEY_ACTIVATION, null)

    fun deviceModel(): String = "${Build.MANUFACTURER} ${Build.MODEL}"
    fun osVersion(): String = "Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})"
}
