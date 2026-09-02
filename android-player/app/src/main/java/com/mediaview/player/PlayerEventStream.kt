package com.mediaview.player

import android.content.Context
import java.net.HttpURLConnection
import java.net.URLEncoder
import java.net.URL

/** Lightweight SSE client. The existing 15-second polling loop remains the fallback. */
class PlayerEventStream(
    private val context: Context,
    private val screenId: String,
) {
    @Volatile private var closed = false
    @Volatile private var connection: HttpURLConnection? = null

    fun listen(onEvent: (String) -> Unit) {
        closed = false
        val encodedId = URLEncoder.encode(screenId, "UTF-8")
        val url = "${PlayerApi.baseUrl(context)}/api/events/screen/$encodedId"
        val active = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 15_000
            readTimeout = 45_000
            setRequestProperty("Accept", "text/event-stream")
            setRequestProperty("Cache-Control", "no-cache")
            setRequestProperty("User-Agent", "MediAdViewPlayer/${BuildConfig.VERSION_NAME}")
        }
        connection = active
        try {
            val code = active.responseCode
            PlayerDiagnostics.http(url, code)
            if (code !in 200..299) {
                throw PlayerApi.HttpStatusException(code, url, active.errorStream?.bufferedReader()?.use { it.readText() } ?: "")
            }
            var event = "message"
            active.inputStream.bufferedReader().useLines { lines ->
                lines.forEach { line ->
                    if (closed) return@forEach
                    when {
                        line.startsWith("event:") -> event = line.substringAfter(':').trim()
                        line.isBlank() -> {
                            onEvent(event)
                            event = "message"
                        }
                    }
                }
            }
        } finally {
            connection = null
            active.disconnect()
        }
    }

    fun close() {
        closed = true
        connection?.disconnect()
        connection = null
    }
}