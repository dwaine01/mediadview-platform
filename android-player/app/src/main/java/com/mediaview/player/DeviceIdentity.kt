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
    private const val KEY_SCREEN_ID = "screen_id"
    private const val KEY_SCREEN_NAME = "screen_name"
    private const val KEY_SERVER_URL = "server_url"

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

    fun markPaired(ctx: Context, backendId: String, activationCode: String?, screenId: String, screenName: String?) {
        prefs(ctx).edit()
            .putBoolean(KEY_REGISTERED, true)
            .putString(KEY_BACKEND_ID, backendId)
            .putString(KEY_ACTIVATION, activationCode)
            .putString(KEY_SCREEN_ID, screenId)
            .putString(KEY_SCREEN_NAME, screenName)
            .apply()
    }

    fun getScreenId(ctx: Context): String? = prefs(ctx).getString(KEY_SCREEN_ID, null)

    fun getScreenName(ctx: Context): String? = prefs(ctx).getString(KEY_SCREEN_NAME, null)

    fun isPaired(ctx: Context): Boolean = !getBackendDeviceId(ctx).isNullOrBlank() && !getScreenId(ctx).isNullOrBlank()

    fun setServerUrl(ctx: Context, url: String) {
        prefs(ctx).edit().putString(KEY_SERVER_URL, url.trimEnd('/')).apply()
    }

    fun getServerUrl(ctx: Context): String? = prefs(ctx).getString(KEY_SERVER_URL, null)

    fun clearPairing(ctx: Context) {
        prefs(ctx).edit()
            .remove(KEY_BACKEND_ID)
            .remove(KEY_ACTIVATION)
            .remove(KEY_SCREEN_ID)
            .remove(KEY_SCREEN_NAME)
            .putBoolean(KEY_REGISTERED, false)
            .apply()
    }

    /** One-time compatibility bridge from the pre-3.0 native preference file. */
    fun migrateLegacy(ctx: Context) {
        if (!getScreenId(ctx).isNullOrBlank()) return
        val legacy = ctx.getSharedPreferences(MainActivity.PREF_NAME, Context.MODE_PRIVATE)
        val screenId = legacy.getString(MainActivity.PREF_SCREEN_ID, null)
        val serverUrl = legacy.getString(MainActivity.PREF_SERVER_URL, null)
        if (!serverUrl.isNullOrBlank()) setServerUrl(ctx, serverUrl)
        if (!screenId.isNullOrBlank()) {
            prefs(ctx).edit().putString(KEY_SCREEN_ID, screenId).apply()
        }
    }

    fun getActivationCode(ctx: Context): String? =
        prefs(ctx).getString(KEY_ACTIVATION, null)

    fun deviceModel(): String = "${Build.MANUFACTURER} ${Build.MODEL}"
    fun osVersion(): String = "Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})"
}
