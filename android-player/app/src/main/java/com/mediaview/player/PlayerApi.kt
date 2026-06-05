package com.mediaview.player

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import android.util.Log
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.io.File
import java.io.FileOutputStream
import java.io.InputStream

/**
 * Lightweight HTTP client for the MediAd View backend.
 * No third-party deps so the APK stays small.
 */
object PlayerApi {

    /** Resolve the backend base URL, preferring runtime override (intent extra) over BuildConfig. */
    fun baseUrl(ctx: Context): String {
        val prefs = ctx.getSharedPreferences("mediaview_identity", Context.MODE_PRIVATE)
        val override = prefs.getString("server_url", null)
        if (!override.isNullOrBlank()) return override.trimEnd('/')
        // Default: server URL embedded at build time in PlayerApp.kt
        return PlayerApp.DEFAULT_SERVER_URL.trimEnd('/')
    }

    fun setBaseUrl(ctx: Context, url: String) {
        ctx.getSharedPreferences("mediaview_identity", Context.MODE_PRIVATE)
            .edit().putString("server_url", url).apply()
    }

    private fun openConn(url: String, method: String = "GET", timeout: Int = 15000): HttpURLConnection {
        val c = URL(url).openConnection() as HttpURLConnection
        c.requestMethod = method
        c.connectTimeout = timeout
        c.readTimeout = timeout
        c.setRequestProperty("User-Agent", "MediAdViewPlayer/${BuildConfig.VERSION_NAME}")
        c.setRequestProperty("Accept", "application/json")
        return c
    }

    private fun readAll(s: InputStream?): String =
        s?.bufferedReader()?.use { it.readText() } ?: ""

    fun postJson(ctx: Context, path: String, body: JSONObject): JSONObject {
        val url = baseUrl(ctx) + path
        val c = openConn(url, "POST")
        c.doOutput = true
        c.setRequestProperty("Content-Type", "application/json; charset=utf-8")
        OutputStreamWriter(c.outputStream, Charsets.UTF_8).use { it.write(body.toString()) }
        val code = c.responseCode
        val text = if (code in 200..299) readAll(c.inputStream) else readAll(c.errorStream)
        Log.d(PlayerApp.TAG, "POST $url → $code")
        if (code !in 200..299) throw RuntimeException("HTTP $code: $text")
        return JSONObject(text)
    }

    fun getJson(ctx: Context, path: String): JSONObject {
        val url = baseUrl(ctx) + path
        val c = openConn(url, "GET")
        val code = c.responseCode
        val text = if (code in 200..299) readAll(c.inputStream) else readAll(c.errorStream)
        Log.d(PlayerApp.TAG, "GET $url → $code")
        if (code !in 200..299) throw RuntimeException("HTTP $code: $text")
        return JSONObject(text)
    }

    /** Download a file with progress callback. Returns the SHA-256 hex of the downloaded bytes. */
    fun downloadFile(url: String, dest: File, onProgress: ((Int) -> Unit)? = null): String {
        val c = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 30000
            readTimeout = 60000
        }
        val total = c.contentLengthLong
        val md = MessageDigest.getInstance("SHA-256")
        c.inputStream.use { input ->
            FileOutputStream(dest).use { out ->
                val buf = ByteArray(64 * 1024)
                var read: Int; var done = 0L
                while (input.read(buf).also { read = it } > 0) {
                    out.write(buf, 0, read)
                    md.update(buf, 0, read)
                    done += read
                    if (total > 0 && onProgress != null) {
                        onProgress(((done * 100) / total).toInt())
                    }
                }
            }
        }
        return md.digest().joinToString("") { "%02x".format(it) }
    }

    fun hasInternet(ctx: Context): Boolean {
        val cm = ctx.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager ?: return false
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val n = cm.activeNetwork ?: return false
            val c = cm.getNetworkCapabilities(n) ?: return false
            return c.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
        }
        @Suppress("DEPRECATION")
        return cm.activeNetworkInfo?.isConnected == true
    }
}
