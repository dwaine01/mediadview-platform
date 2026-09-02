package com.mediaview.player

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.util.Log
import androidx.core.content.FileProvider
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File

/**
 * Downloads the new APK, verifies SHA-256 (if provided), and triggers system install.
 * Requires the user's device to allow "Install from unknown sources" — A40 firmware
 * typically allows this. After install, the launcher (MainActivity) auto-starts again.
 */
object AutoUpdater {

    @Volatile private var updating = false
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    fun tryUpdate(ctx: Context, info: JSONObject) {
        if (updating) {
            Log.i(PlayerApp.TAG, "AutoUpdater: already updating, skip")
            return
        }
        val url = info.optString("apk_url", null) ?: return
        val version = info.optString("version_name", "?")
        val versionCode = info.optInt("version_code", 0)
        if (versionCode > 0 && versionCode <= BuildConfig.VERSION_CODE) {
            Log.i(PlayerApp.TAG, "AutoUpdater: server version $versionCode <= current ${BuildConfig.VERSION_CODE}, skip")
            return
        }
        val expectedSha = info.optString("sha256", null)
        updating = true

        scope.launch {
            try {
                val cacheDir = File(ctx.cacheDir, "updates").also { it.mkdirs() }
                val out = File(cacheDir, "mediaview-player-$version.apk")
                val temp = File(cacheDir, out.name + ".tmp")
                temp.delete()
                Log.i(PlayerApp.TAG, "⬇ Downloading APK from $url → ${out.absolutePath}")
                val absoluteUrl = if (url.startsWith("http")) url else PlayerApi.baseUrl(ctx) + url
                val download = PlayerApi.downloadFile(absoluteUrl, temp) { pct ->
                    if (pct % 10 == 0) Log.d(PlayerApp.TAG, "  download: $pct%")
                }
                Log.i(PlayerApp.TAG, "  downloaded ${download.bytes} bytes — sha256=${download.sha256}")
                if (!expectedSha.isNullOrBlank() && !download.sha256.equals(expectedSha, ignoreCase = true)) {
                    Log.e(PlayerApp.TAG, "  SHA mismatch (expected=$expectedSha) — abort install")
                    temp.delete()
                    return@launch
                }
                FileIntegrity.commit(temp, out)
                withContext(Dispatchers.Main) { installApk(ctx, out) }
            } catch (e: Exception) {
                Log.e(PlayerApp.TAG, "AutoUpdater error: ${e.message}")
            } finally {
                updating = false
            }
        }
    }

    private fun installApk(ctx: Context, apk: File) {
        try {
            val uri: Uri = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                FileProvider.getUriForFile(
                    ctx,
                    ctx.packageName + ".fileprovider",
                    apk
                )
            } else {
                Uri.fromFile(apk)
            }
            val intent = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(uri, "application/vnd.android.package-archive")
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
            // Check if we can install (Oreo+)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                if (!ctx.packageManager.canRequestPackageInstalls()) {
                    Log.w(PlayerApp.TAG, "App lacks REQUEST_INSTALL_PACKAGES grant — opening system page")
                    val settings = Intent(android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                        Uri.parse("package:${ctx.packageName}"))
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    ctx.startActivity(settings)
                    return
                }
            }
            Log.i(PlayerApp.TAG, "⚙ Launching APK install")
            ctx.startActivity(intent)
        } catch (e: Exception) {
            Log.e(PlayerApp.TAG, "installApk failed: ${e.message}")
        }
    }
}
