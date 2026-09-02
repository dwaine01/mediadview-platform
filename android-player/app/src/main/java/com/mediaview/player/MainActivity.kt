package com.mediaview.player

import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.content.pm.ActivityInfo
import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.StatFs
import android.os.SystemClock
import android.util.Log
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.TextView
import androidx.work.WorkManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File

class MainActivity : Activity(), PlaybackEvents {
    companion object {
        val DEFAULT_SERVER = BuildConfig.SERVER_URL
        const val PREF_NAME = "mediaview_player"
        const val PREF_SERVER_URL = "server_url"
        const val PREF_SCREEN_ID = "screen_id"
        const val PREF_ORIENTATION = "orientation"
        const val PREF_DEVICE_NAME = "device_name"
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var contentHost: FrameLayout
    private lateinit var statusView: TextView
    private lateinit var diagnosticsView: TextView
    private lateinit var renderer: PlaybackController
    private lateinit var repository: PlayerRepository
    private lateinit var networkMonitor: NetworkMonitor
    private var syncJob: Job? = null
    private var heartbeatJob: Job? = null
    private var realtimeJob: Job? = null
    @Volatile private var eventStream: PlayerEventStream? = null
    private var syncing = false
    private var retryAttempt = 0
    private var retryRunnable: Runnable? = null
    private var menuPresses = 0
    private var lastMenuPress = 0L

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        DeviceIdentity.migrateLegacy(this)
        configureWindow()
        buildUi()
        repository = PlayerRepository(this)
        renderer = PlaybackController(this, contentHost, this)
        networkMonitor = NetworkMonitor(this) { online ->
            runOnUiThread {
                refreshDiagnostics()
                if (online) syncNow("network-restored")
                else if (renderer.currentItem == null) showStatus("Sin conexión", "Esperando red; reintento automático")
            }
        }

        val screenId = DeviceIdentity.getScreenId(this)
        PlayerDiagnostics.identity(screenId, DeviceIdentity.isPaired(this))
        showPreviousCrashIfPresent()
        if (!DeviceIdentity.isPaired(this)) {
            showStatus("Dispositivo sin vincular", "Abriendo emparejamiento seguro…")
            launchPairing()
            return
        }
        startRuntime()
    }

    private fun configureWindow() {
        window.addFlags(
            WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON or
                WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON or
                WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD,
        )
        hideSystemUi()
    }

    private fun buildUi() {
        val root = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }
        contentHost = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }
        statusView = TextView(this).apply {
            setBackgroundColor(Color.rgb(8, 15, 30))
            setTextColor(Color.WHITE)
            textSize = 28f
            gravity = Gravity.CENTER
            setPadding(64, 64, 64, 64)
        }
        diagnosticsView = TextView(this).apply {
            setBackgroundColor(Color.argb(220, 2, 6, 23))
            setTextColor(Color.rgb(165, 243, 252))
            textSize = 13f
            gravity = Gravity.START
            setPadding(24, 18, 24, 18)
            visibility = if (BuildConfig.DIAGNOSTICS_ENABLED) View.VISIBLE else View.GONE
        }
        root.addView(contentHost, fillParams())
        root.addView(statusView, fillParams())
        root.addView(diagnosticsView, FrameLayout.LayoutParams(
            resources.displayMetrics.widthPixels.coerceAtLeast(640) / 2,
            FrameLayout.LayoutParams.WRAP_CONTENT,
            Gravity.TOP or Gravity.START,
        ))
        setContentView(root)
        PlayerDiagnostics.listener = { runOnUiThread { refreshDiagnostics() } }
        refreshDiagnostics()
    }

    private fun startRuntime() {
        networkMonitor.start()
        HeartbeatWorker.enqueuePeriodic(this)
        scope.launch {
            val cached = repository.loadCached()
            if (!cached?.items.isNullOrEmpty()) {
                applyOrientation(cached!!.resolution)
                renderer.setPlaylist(cached.items)
                showStatus("Contenido local", "Sincronizando cambios…")
            } else {
                showStatus("Preparando contenido", "Validando playlist y archivos…")
            }
            syncNow("startup")
        }
        syncJob = scope.launch {
            while (isActive) {
                delay(15_000)
                syncNow("poll")
            }
        }
        heartbeatJob = scope.launch {
            while (isActive) {
                sendHeartbeat()
                delay(30_000)
            }
        }
        startRealtimeEvents()
        handler.post(watchdog)
    }

    private fun startRealtimeEvents() {
        val screenId = DeviceIdentity.getScreenId(this) ?: return
        realtimeJob?.cancel()
        realtimeJob = scope.launch(Dispatchers.IO) {
            var attempt = 0
            while (isActive) {
                val stream = PlayerEventStream(this@MainActivity, screenId)
                eventStream = stream
                try {
                    stream.listen { event ->
                        if (event == "connected") {
                            attempt = 0
                            PlayerDiagnostics.realtime(true)
                        }
                        if (RealtimeEventPolicy.shouldSync(event)) {
                            runOnUiThread { syncNow("realtime-$event") }
                        }
                    }
                } catch (error: Exception) {
                    if (isActive) Log.w(PlayerApp.TAG, "Realtime stream unavailable: ${error.message}")
                } finally {
                    stream.close()
                    eventStream = null
                    PlayerDiagnostics.realtime(false)
                }
                if (isActive) delay(RetryPolicy.delayMs(attempt++).coerceAtMost(60_000L))
            }
        }
    }

    private fun syncNow(reason: String) {
        if (syncing || !DeviceIdentity.isPaired(this)) return
        if (!PlayerApi.hasInternet(this)) {
            PlayerDiagnostics.connectivity(false)
            scheduleRetry()
            return
        }
        val deviceId = DeviceIdentity.getBackendDeviceId(this) ?: return
        syncing = true
        scope.launch {
            try {
                val result = repository.sync(deviceId)
                retryAttempt = 0
                retryRunnable?.let(handler::removeCallbacks)
                retryRunnable = null
                applyOrientation(result.snapshot.resolution)
                if (result.snapshot.items.isEmpty()) {
                    renderer.setPlaylist(emptyList())
                    showStatus("Sin contenido programado", "El player seguirá sincronizando automáticamente")
                } else {
                    renderer.setPlaylist(result.snapshot.items)
                }
                if (result.rejectedItems > 0) {
                    PlayerDiagnostics.playerError("${result.rejectedItems} archivo(s) rechazado(s)")
                }
            } catch (_: DeviceUnpairedException) {
                DeviceIdentity.clearPairing(this@MainActivity)
                launchPairing()
            } catch (error: PlayerApi.HttpStatusException) {
                if (error.statusCode == 404) {
                    DeviceIdentity.clearPairing(this@MainActivity)
                    launchPairing()
                } else handleSyncFailure(reason, error)
            } catch (error: Exception) {
                handleSyncFailure(reason, error)
            } finally {
                syncing = false
                refreshDiagnostics()
            }
        }
    }

    private fun handleSyncFailure(reason: String, error: Exception) {
        PlayerDiagnostics.playerError("sync/$reason: ${error.message}")
        if (renderer.currentItem == null) showStatus("Servicio no disponible", "Usando caché local o reintentando…")
        scheduleRetry()
    }

    private fun scheduleRetry() {
        val delayMs = RetryPolicy.delayMs(retryAttempt++)
        retryRunnable?.let(handler::removeCallbacks)
        retryRunnable = Runnable { syncNow("retry") }.also { handler.postDelayed(it, delayMs) }
    }

    private suspend fun sendHeartbeat() = withContext(Dispatchers.IO) {
        val deviceId = DeviceIdentity.getBackendDeviceId(this@MainActivity) ?: return@withContext
        if (!PlayerApi.hasInternet(this@MainActivity)) return@withContext
        try {
            val payload = JSONObject().apply {
                put("status", "online")
                put("current_media_id", renderer.currentItem?.mediaId)
                put("uptime_seconds", SystemClock.elapsedRealtime() / 1000)
                put("free_storage_mb", StatFs(filesDir.path).availableBytes / 1024 / 1024)
                put("cached_media_count", File(filesDir, "media-cache").listFiles()?.size ?: 0)
                put("app_version", BuildConfig.VERSION_NAME)
                put("last_error", PlayerDiagnostics.current().playerError.takeUnless { it == "none" })
            }
            val response = PlayerApi.postJson(this@MainActivity, "/api/devices/$deviceId/heartbeat", payload)
            response.optJSONObject("update_available")?.let { AutoUpdater.tryUpdate(this@MainActivity, it) }
            when (response.optString("command")) {
                "reload" -> runOnUiThread { syncNow("remote-command") }
                "clear_cache" -> {
                    repository.clearCache()
                    runOnUiThread {
                        renderer.setPlaylist(emptyList())
                        showStatus("Caché limpiada", "Descargando contenido validado…")
                        syncNow("clear-cache")
                    }
                }
                "restart" -> runOnUiThread { restartApp() }
            }
            if (response.optString("action") == "wait") {
                DeviceIdentity.clearPairing(this@MainActivity)
                runOnUiThread { launchPairing() }
            }
        } catch (error: Exception) {
            PlayerDiagnostics.playerError("heartbeat: ${error.message}")
        }
    }

    override fun onPreparing(item: PlaylistItemModel) {
        showStatus("Cargando contenido", item.filename)
    }

    override fun onReady(item: PlaylistItemModel) {
        statusView.visibility = View.GONE
        PlayerDiagnostics.playerError(null)
        if (item.kind != MediaKind.HTML) PlayerDiagnostics.webError(null)
    }

    override fun onError(item: PlaylistItemModel, message: String) {
        showStatus("Contenido no reproducible", "$message\nSaltando y recuperando automáticamente…")
        scope.launch { repository.invalidate(item) }
    }

    private fun showStatus(title: String, detail: String) {
        statusView.text = "$title\n\n$detail"
        statusView.visibility = View.VISIBLE
    }

    private fun applyOrientation(resolution: String) {
        val parts = resolution.lowercase().split("x")
        val width = parts.getOrNull(0)?.toIntOrNull() ?: return
        val height = parts.getOrNull(1)?.toIntOrNull() ?: return
        requestedOrientation = if (height > width) ActivityInfo.SCREEN_ORIENTATION_SENSOR_PORTRAIT
        else ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
    }

    private fun launchPairing() {
        startActivity(Intent(this, PairingActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        })
        finish()
    }

    private fun restartApp() {
        val launch = packageManager.getLaunchIntentForPackage(packageName) ?: return
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
        startActivity(launch)
        finishAffinity()
    }

    private fun showPreviousCrashIfPresent() {
        val crash = getSharedPreferences("player_crash", Context.MODE_PRIVATE).getString("last_crash", null)
        if (!crash.isNullOrBlank()) PlayerDiagnostics.playerError("previous crash: $crash")
    }

    private fun refreshDiagnostics() {
        diagnosticsView.text = PlayerDiagnostics.text()
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_I && BuildConfig.DIAGNOSTICS_ENABLED) {
            diagnosticsView.visibility = if (diagnosticsView.visibility == View.VISIBLE) View.GONE else View.VISIBLE
            return true
        }
        if (keyCode == KeyEvent.KEYCODE_MENU || keyCode == KeyEvent.KEYCODE_F1) {
            val now = System.currentTimeMillis()
            if (now - lastMenuPress > 3_000) menuPresses = 0
            lastMenuPress = now
            if (++menuPresses >= 5) {
                menuPresses = 0
                showInstallerMenu()
            }
            return true
        }
        return keyCode == KeyEvent.KEYCODE_BACK || super.onKeyDown(keyCode, event)
    }

    private fun showInstallerMenu() {
        runCatching { stopLockTask() }
        AlertDialog.Builder(this)
            .setTitle("MediAd View ${BuildConfig.VERSION_NAME}")
            .setMessage(PlayerDiagnostics.text())
            .setPositiveButton("Cerrar", null)
            .setNegativeButton("Desvincular") { _, _ ->
                DeviceIdentity.clearPairing(this)
                WorkManager.getInstance(this).cancelAllWorkByTag("mediaview-bg")
                launchPairing()
            }
            .show()
    }

    private val watchdog = object : Runnable {
        override fun run() {
            renderer.watchdogTick()
            hideSystemUi()
            handler.postDelayed(this, 10_000)
        }
    }

    @Suppress("DEPRECATION")
    private fun hideSystemUi() {
        window.decorView.systemUiVisibility =
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or View.SYSTEM_UI_FLAG_FULLSCREEN or
                View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_LAYOUT_STABLE or
                View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
    }

    override fun onResume() { super.onResume(); if (::renderer.isInitialized) renderer.resume(); hideSystemUi() }
    override fun onPause() { if (::renderer.isInitialized) renderer.pause(); super.onPause() }
    override fun onDestroy() {
        PlayerDiagnostics.listener = null
        if (::networkMonitor.isInitialized) networkMonitor.stop()
        if (::renderer.isInitialized) renderer.release()
        eventStream?.close()
        syncJob?.cancel(); heartbeatJob?.cancel(); realtimeJob?.cancel(); scope.coroutineContext[Job]?.cancel()
        handler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }

    private fun fillParams() = FrameLayout.LayoutParams(
        FrameLayout.LayoutParams.MATCH_PARENT,
        FrameLayout.LayoutParams.MATCH_PARENT,
    )
}