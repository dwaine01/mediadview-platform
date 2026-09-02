package com.mediaview.player

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object PlayerDiagnostics {
    data class Snapshot(
        val url: String = "-",
        val screenId: String = "-",
        val pairing: String = "not paired",
        val httpStatus: String = "-",
        val webViewError: String = "none",
        val playerError: String = "none",
        val connectivity: String = "unknown",
        val realtime: String = "disconnected",
        val lastSync: String = "never",
    )

    @Volatile private var state = Snapshot()
    @Volatile var listener: ((Snapshot) -> Unit)? = null

    fun current(): Snapshot = state
    fun identity(screenId: String?, paired: Boolean) = update {
        it.copy(screenId = screenId?.ifBlank { "-" } ?: "-", pairing = if (paired) "paired" else "pending")
    }
    fun http(url: String, status: Int) = update { it.copy(url = url, httpStatus = status.toString()) }
    fun webError(message: String?) = update { it.copy(webViewError = message?.take(240) ?: "none") }
    fun playerError(message: String?) = update { it.copy(playerError = message?.take(240) ?: "none") }
    fun connectivity(online: Boolean) = update { it.copy(connectivity = if (online) "online" else "offline") }
    fun realtime(connected: Boolean) = update { it.copy(realtime = if (connected) "connected" else "polling fallback") }
    fun synced(epochMs: Long = System.currentTimeMillis()) = update {
        it.copy(lastSync = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date(epochMs)))
    }

    @Synchronized private fun update(change: (Snapshot) -> Snapshot) {
        state = change(state)
        listener?.invoke(state)
    }

    fun text(snapshot: Snapshot = state): String = """
        MEDIAD VIEW DIAGNOSTICS
        URL: ${snapshot.url}
        screen_id: ${snapshot.screenId}
        pairing: ${snapshot.pairing}
        HTTP: ${snapshot.httpStatus}
        WebView: ${snapshot.webViewError}
        Player: ${snapshot.playerError}
        Network: ${snapshot.connectivity}
        Realtime: ${snapshot.realtime}
        Last sync: ${snapshot.lastSync}
    """.trimIndent()
}