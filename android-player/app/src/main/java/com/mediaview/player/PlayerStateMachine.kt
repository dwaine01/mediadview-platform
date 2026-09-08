package com.mediaview.player

/**
 * Sprint 1 — máquina de estados del reproductor.
 *
 * Es la ÚNICA fuente de verdad del estado que se reporta al backend. Nada de
 * cadenas de UI improvisadas: si el panel dice SYNCING es porque el player lo dijo.
 */
enum class PlayerState {
    BOOTING,
    INITIALIZING,
    UNPAIRED,
    PAIRING,
    PAIRED,
    WAITING_FOR_ASSIGNMENT,
    SYNCING,
    DOWNLOADING,
    VALIDATING,
    READY,
    PLAYING,
    OFFLINE_PLAYING_CACHE,
    DEGRADED,
    ERROR,
    RECOVERING,
    UPDATING,
    RESTARTING,
}

/** Progreso REAL de descarga (bytes y archivos verdaderos, nunca simulado). */
data class SyncProgress(
    val filesDone: Int,
    val filesTotal: Int,
    val bytesDone: Long,
    val bytesTotal: Long,
    val currentFile: String? = null,
    val manifestVersion: String? = null,
) {
    val percent: Double
        get() = when {
            bytesTotal > 0 -> bytesDone * 100.0 / bytesTotal
            filesTotal > 0 -> filesDone * 100.0 / filesTotal
            else -> 0.0
        }
}

/**
 * Estado observable del player. Thread-safe y sin dependencias: lo escribe el
 * hilo de sync/playback y lo lee el heartbeat.
 */
object PlayerStateMachine {

    @Volatile
    private var state: PlayerState = PlayerState.BOOTING

    @Volatile
    private var stateSince: Long = System.currentTimeMillis()

    @Volatile
    private var progress: SyncProgress? = null

    /** Estados en los que un progreso de descarga tiene sentido. */
    private val SYNC_STATES = setOf(PlayerState.SYNCING, PlayerState.DOWNLOADING, PlayerState.VALIDATING)

    @Synchronized
    fun transitionTo(next: PlayerState) {
        if (state == next) return
        // Combinaciones imposibles: si ya no estamos sincronizando, no hay progreso.
        if (next !in SYNC_STATES) progress = null
        state = next
        stateSince = System.currentTimeMillis()
        PlayerDiagnostics.note("state=${next.name}")
    }

    fun current(): PlayerState = state

    fun secondsInState(): Long = (System.currentTimeMillis() - stateSince) / 1000

    @Synchronized
    fun reportProgress(update: SyncProgress?) {
        if (update != null && state !in SYNC_STATES) {
            state = PlayerState.DOWNLOADING
            stateSince = System.currentTimeMillis()
        }
        progress = update
    }

    fun currentProgress(): SyncProgress? = if (state in SYNC_STATES) progress else null

    fun clearProgress() = reportProgress(null)
}
