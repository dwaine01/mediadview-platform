package com.mediaview.player

import android.annotation.SuppressLint
import android.app.Activity
import android.app.ActivityManager
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.util.Log
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.WindowManager
import android.webkit.ConsoleMessage
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView

/**
 * MediAd View Player v2.0 - Main Activity
 *
 * Production-grade digital signage player optimized for:
 * - Colorlight A40 LED Media Player
 * - Android TV / Google TV
 * - Fire TV / Fire TV Stick
 *
 * Features:
 * - Full screen immersive kiosk mode
 * - Screen always on (FLAG_KEEP_SCREEN_ON + WakeLock)
 * - Network monitoring & auto-reconnect with exponential backoff
 * - Crash recovery (auto-restart on unhandled exceptions)
 * - Nightly auto-restart for memory management
 * - Device activation via 6-digit code
 * - Remote control / D-pad friendly navigation
 * - Hidden settings menu (press Menu key 5x or hold DPAD_CENTER 5s)
 * - Configurable server URL and orientation
 * - Offline content caching
 * - Proof of Play logging
 */
class MainActivity : Activity() {

    private lateinit var webView: WebView
    private lateinit var statusView: TextView
    private val handler = Handler(Looper.getMainLooper())
    private var serverUrl = ""
    private var screenId = ""
    private var isConnected = false
    private var reconnectAttempts = 0
    private var wakeLock: android.os.PowerManager.WakeLock? = null
    private val MAX_RECONNECT_DELAY = 60000L

    // Hidden settings menu tracking
    private var menuKeyCount = 0
    private var lastMenuKeyTime = 0L
    private val MENU_KEY_TIMEOUT = 3000L // 3 seconds to press 5 times
    private val MENU_KEY_COUNT_REQUIRED = 5

    // Long press tracking for DPAD_CENTER
    private var dpadCenterDownTime = 0L
    private val LONG_PRESS_DURATION = 5000L // 5 seconds

    companion object {
        // Default server URL - uses BuildConfig value set in build.gradle.kts
        // For production, change the URL in build.gradle.kts
        val DEFAULT_SERVER = BuildConfig.SERVER_URL

        const val PREF_NAME = "mediaview_player"
        const val PREF_SERVER_URL = "server_url"
        const val PREF_SCREEN_ID = "screen_id"
        const val PREF_ORIENTATION = "orientation" // "landscape", "portrait", "auto"
        const val PREF_DEVICE_NAME = "device_name"
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Log.i(PlayerApp.TAG, "MainActivity onCreate - MediAd View Player v${BuildConfig.VERSION_NAME}")

        // ===== PAIRING CHECK =====
        // If this device hasn't finished pairing (no screen_id saved yet),
        // hand off to the native OptiSigns-style pairing screen instead of
        // building the WebView player UI.
        if (!DeviceIdentity.isRegistered(this) ||
            getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
                .getString(PREF_SCREEN_ID, "").isNullOrBlank()
        ) {
            startActivity(android.content.Intent(this, PairingActivity::class.java).apply {
                flags = android.content.Intent.FLAG_ACTIVITY_NEW_TASK or android.content.Intent.FLAG_ACTIVITY_CLEAR_TASK
            })
            finish()
            return
        }

        // ===== FULL SCREEN + ALWAYS ON =====
        window.addFlags(
            WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON or
            WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
            WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON or
            WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD
        )

        // ===== PREVENT SCREEN SLEEP =====
        preventScreenSleep()
        hideSystemUI()

        // ===== LOAD CONFIG =====
        val prefs = getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
        serverUrl = prefs.getString(PREF_SERVER_URL, DEFAULT_SERVER) ?: DEFAULT_SERVER
        screenId = prefs.getString(PREF_SCREEN_ID, "") ?: ""

        // Check intent extras (for initial setup via ADB)
        intent?.getStringExtra("server_url")?.let {
            serverUrl = it
            prefs.edit().putString(PREF_SERVER_URL, it).apply()
        }
        intent?.getStringExtra("screen_id")?.let {
            screenId = it
            prefs.edit().putString(PREF_SCREEN_ID, it).apply()
        }

        // ===== BUILD UI =====
        val root = FrameLayout(this).apply {
            setBackgroundColor(Color.BLACK)
        }

        // Status overlay (shown during loading/errors)
        statusView = TextView(this).apply {
            setTextColor(Color.parseColor("#64748B"))
            textSize = 14f
            text = "MediAd View Player v${BuildConfig.VERSION_NAME} - Initializing..."
            setPadding(32, 32, 32, 32)
            visibility = View.GONE
        }

        // WebView
        webView = WebView(this).apply {
            setBackgroundColor(Color.BLACK)

            settings.apply {
                javaScriptEnabled = true
                domStorageEnabled = true
                databaseEnabled = true
                mediaPlaybackRequiresUserGesture = false
                allowFileAccess = true
                cacheMode = WebSettings.LOAD_DEFAULT
                mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
                useWideViewPort = true
                loadWithOverviewMode = true
                setSupportZoom(false)

                // Performance optimizations for 24/7 operation
                @Suppress("DEPRECATION")
                setRenderPriority(WebSettings.RenderPriority.HIGH)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    safeBrowsingEnabled = false
                }

                // Ensure hardware acceleration for smooth video playback
                setLayerType(View.LAYER_TYPE_HARDWARE, null)
            }

            // Handle page events
            webViewClient = object : WebViewClient() {
                override fun onPageFinished(view: WebView?, url: String?) {
                    super.onPageFinished(view, url)
                    Log.i(PlayerApp.TAG, "Page loaded: $url")
                    statusView.visibility = View.GONE
                    isConnected = true
                    reconnectAttempts = 0
                }

                override fun onReceivedError(
                    view: WebView?, errorCode: Int, description: String?, failingUrl: String?
                ) {
                    Log.e(PlayerApp.TAG, "WebView error: $description ($errorCode) url=$failingUrl")
                    isConnected = false
                    scheduleReconnect()
                }

                override fun onReceivedHttpError(
                    view: WebView?,
                    request: android.webkit.WebResourceRequest?,
                    errorResponse: android.webkit.WebResourceResponse?
                ) {
                    super.onReceivedHttpError(view, request, errorResponse)
                    val status = errorResponse?.statusCode ?: 0
                    val url = request?.url?.toString() ?: ""
                    // If we are trying to load THIS screen's main player page
                    // and it returns 404, the screen was deleted server-side.
                    // Kick back to PairingActivity so the user can re-pair with
                    // a fresh activation code instead of black-screening forever.
                    val isMainDoc = request?.isForMainFrame == true &&
                        url.contains("/api/player/") && url.endsWith("/web")
                    if (isMainDoc && status == 404) {
                        Log.w(PlayerApp.TAG, "Player URL returned 404 — screen deleted, returning to pairing")
                        returnToPairing("Screen no longer exists")
                    }
                }
            }

            // Console logging + disable default video poster
            webChromeClient = object : WebChromeClient() {
                override fun onConsoleMessage(message: ConsoleMessage?): Boolean {
                    message?.let {
                        Log.d(PlayerApp.TAG, "[WebView] ${it.message()} (${it.lineNumber()})")
                    }
                    return true
                }

                // Remove the play button icon that Android WebView shows before videos
                override fun getDefaultVideoPoster(): android.graphics.Bitmap {
                    return android.graphics.Bitmap.createBitmap(1, 1, android.graphics.Bitmap.Config.ARGB_8888)
                }
            }
        }

        root.addView(webView, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        ))
        root.addView(statusView)
        setContentView(root)

        // ===== START =====
        checkOverlayPermission()
        if (screenId.isNotEmpty()) {
            // Verify with backend that the screen is still valid BEFORE
            // loading the WebView, so we don't black-screen on deleted screens.
            verifyPairingThenLoad()
        } else {
            showSetupMode()
        }

        // Start overlay service for auto-boot
        startOverlayService()

        // Schedule nightly restart for stability
        scheduleNightlyRestart()

        // ===== KIOSK MODE =====
        try {
            startLockTask()
        } catch (e: Exception) {
            Log.w(PlayerApp.TAG, "Lock task not available: ${e.message}")
        }
    }

    /**
     * Check and request "Display over other apps" permission.
     */
    private fun checkOverlayPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            if (!android.provider.Settings.canDrawOverlays(this)) {
                try {
                    val intent = Intent(
                        android.provider.Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:$packageName")
                    )
                    startActivity(intent)
                } catch (e: Exception) {
                    Log.w(PlayerApp.TAG, "Cannot request overlay permission: ${e.message}")
                }
            }
        }
    }

    /**
     * Start the overlay service for auto-boot capability
     */
    private fun startOverlayService() {
        try {
            val serviceIntent = Intent(this, OverlayService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(serviceIntent)
            } else {
                startService(serviceIntent)
            }
        } catch (e: Exception) {
            Log.e(PlayerApp.TAG, "Failed to start overlay service: ${e.message}")
        }
    }

    /**
     * Load the Web Player for the configured screen
     */
    private fun loadPlayer() {
        val playerUrl = "$serverUrl/api/player/$screenId/web"
        Log.i(PlayerApp.TAG, "Loading player: $playerUrl")
        statusView.text = "Loading MediAd View Player..."
        statusView.visibility = View.VISIBLE

        if (isNetworkAvailable()) {
            webView.loadUrl(playerUrl)
        } else {
            Log.w(PlayerApp.TAG, "No network - will retry")
            statusView.text = "Sin conexion de red. Reintentando..."
            statusView.visibility = View.VISIBLE
            scheduleReconnect()
        }
    }

    /**
     * Verify the pairing status with the backend before loading the WebView.
     * If the backend reports the device is no longer active (e.g. the screen
     * was deleted from the admin panel), route back to the PairingActivity
     * so the user sees a fresh activation code instead of a black screen.
     */
    private fun verifyPairingThenLoad() {
        statusView.text = "Verifying pairing..."
        statusView.visibility = View.VISIBLE
        val pairPrefs = getSharedPreferences(PairingActivity.PAIR_PREFS, Context.MODE_PRIVATE)
        val srvId = pairPrefs.getString(PairingActivity.KEY_SERVER_DEVICE_ID, "") ?: ""
        val clientUuid = DeviceIdentity.getDeviceId(this)
        val pollId = if (srvId.isNotBlank()) srvId else clientUuid

        Thread {
            try {
                val res = PlayerApi.getJson(this@MainActivity, "/api/devices/$pollId/check")
                val status = res.optString("status", "")
                val serverScreenId = res.optString("screen_id", "")
                runOnUiThread {
                    if (status == "active" && serverScreenId.isNotBlank()) {
                        // Sync screen_id in case admin re-assigned it to a new screen
                        if (serverScreenId != screenId) {
                            screenId = serverScreenId
                            getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE).edit()
                                .putString(PREF_SCREEN_ID, serverScreenId).apply()
                        }
                        loadPlayer()
                    } else {
                        Log.w(PlayerApp.TAG, "Backend reports device not active (status=$status). Returning to pairing.")
                        returnToPairing("Not paired anymore")
                    }
                }
            } catch (e: Exception) {
                // Network error — best effort: try loading the player anyway
                // so an offline TV doesn't get stuck in a verification loop.
                Log.w(PlayerApp.TAG, "Pairing verify failed: ${e.message}. Falling back to loadPlayer().")
                runOnUiThread { loadPlayer() }
            }
        }.start()
    }

    /**
     * Clear the current pairing (screen_id) and jump back to PairingActivity.
     * Called when the backend says our screen no longer exists or the device
     * is no longer active.
     */
    private fun returnToPairing(reason: String) {
        Log.i(PlayerApp.TAG, "Returning to pairing screen: $reason")
        try {
            getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE).edit()
                .remove(PREF_SCREEN_ID)
                .remove(PREF_DEVICE_NAME)
                .apply()
            // Also drop the cached activation_code so PairingActivity fetches
            // the fresh one from the backend.
            getSharedPreferences(PairingActivity.PAIR_PREFS, Context.MODE_PRIVATE).edit()
                .remove(PairingActivity.KEY_ACTIVATION_CODE)
                .apply()
        } catch (e: Exception) {
            Log.w(PlayerApp.TAG, "Failed to clear prefs: ${e.message}")
        }
        try { stopLockTask() } catch (e: Exception) { }
        startActivity(Intent(this, PairingActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        })
        finish()
    }

    /**
     * Show setup/activation page when no screen is configured
     */
    private fun showSetupMode() {
        val activateUrl = "$serverUrl/api/player-activate"
        Log.i(PlayerApp.TAG, "Loading activation page: $activateUrl")

        if (isNetworkAvailable()) {
            webView.loadUrl(activateUrl)
        } else {
            // Show offline message with server URL info
            statusView.text = "Sin conexion de red.\nServidor: $serverUrl\nReintentando..."
            statusView.visibility = View.VISIBLE
            scheduleReconnect()
        }
    }

    /**
     * Schedule reconnection with exponential backoff
     */
    private fun scheduleReconnect() {
        reconnectAttempts++
        val delay = minOf(
            (5000L * reconnectAttempts),
            MAX_RECONNECT_DELAY
        )
        Log.i(PlayerApp.TAG, "Reconnecting in ${delay/1000}s (attempt #$reconnectAttempts)")
        statusView.text = "Reconectando en ${delay/1000}s... (intento #$reconnectAttempts)"
        statusView.visibility = View.VISIBLE

        handler.postDelayed({
            if (screenId.isNotEmpty()) {
                loadPlayer()
            } else {
                showSetupMode()
            }
        }, delay)
    }

    /**
     * Check network availability
     */
    private fun isNetworkAvailable(): Boolean {
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val cap = cm.getNetworkCapabilities(cm.activeNetwork) ?: return false
            return cap.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
        }
        @Suppress("DEPRECATION")
        return cm.activeNetworkInfo?.isConnected == true
    }

    /**
     * Immersive full-screen mode
     */
    @Suppress("DEPRECATION")
    private fun hideSystemUI() {
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or
            View.SYSTEM_UI_FLAG_FULLSCREEN or
            View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
            View.SYSTEM_UI_FLAG_LAYOUT_STABLE or
            View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION or
            View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
        )
    }

    /**
     * Handle key events:
     * - 'i' key: diagnostics HUD in web player
     * - Menu key x5: hidden settings menu
     * - Back: blocked in kiosk mode
     * - DPAD_CENTER long press (5s): hidden settings menu
     */
    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        // Diagnostics HUD
        if (keyCode == KeyEvent.KEYCODE_I) {
            webView.evaluateJavascript("document.dispatchEvent(new KeyboardEvent('keydown',{key:'i'}))", null)
            return true
        }

        // Hidden settings menu via MENU key x5
        if (keyCode == KeyEvent.KEYCODE_MENU || keyCode == KeyEvent.KEYCODE_F1) {
            val now = System.currentTimeMillis()
            if (now - lastMenuKeyTime > MENU_KEY_TIMEOUT) {
                menuKeyCount = 0
            }
            menuKeyCount++
            lastMenuKeyTime = now
            if (menuKeyCount >= MENU_KEY_COUNT_REQUIRED) {
                menuKeyCount = 0
                showSettingsDialog()
            }
            return true
        }

        // DPAD_CENTER long press tracking
        if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER) {
            if (event?.repeatCount == 0) {
                dpadCenterDownTime = System.currentTimeMillis()
            }
            // Check if held for 5 seconds
            if (System.currentTimeMillis() - dpadCenterDownTime >= LONG_PRESS_DURATION) {
                dpadCenterDownTime = Long.MAX_VALUE // Prevent re-trigger
                showSettingsDialog()
                return true
            }
        }

        // Block back button in kiosk mode
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            return true
        }

        return super.onKeyDown(keyCode, event)
    }

    override fun onKeyUp(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER) {
            dpadCenterDownTime = 0L
        }
        return super.onKeyUp(keyCode, event)
    }

    /**
     * Hidden settings dialog - accessible via Menu x5 or DPAD_CENTER long press
     * Allows configuring server URL, screen ID, and resetting the device
     */
    private fun showSettingsDialog() {
        try {
            // Temporarily stop lock task for dialog
            try { stopLockTask() } catch (e: Exception) { }

            val prefs = getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)

            val layout = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(48, 32, 48, 16)
            }

            // Title
            val title = TextView(this).apply {
                text = "MediAd View Player v${BuildConfig.VERSION_NAME}"
                textSize = 18f
                setTextColor(Color.WHITE)
                gravity = Gravity.CENTER
                setPadding(0, 0, 0, 24)
            }
            layout.addView(title)

            // Device info
            val infoText = TextView(this).apply {
                text = "Modelo: ${Build.MODEL}\n" +
                       "Android: ${Build.VERSION.RELEASE}\n" +
                       "Pantalla: ${resources.displayMetrics.widthPixels}x${resources.displayMetrics.heightPixels}\n" +
                       "Screen ID: ${screenId.ifEmpty { "(no configurado)" }}"
                textSize = 13f
                setTextColor(Color.parseColor("#94A3B8"))
                setPadding(0, 0, 0, 24)
            }
            layout.addView(infoText)

            // Server URL input
            val serverLabel = TextView(this).apply {
                text = "URL del Servidor:"
                textSize = 14f
                setTextColor(Color.parseColor("#E2E8F0"))
            }
            layout.addView(serverLabel)

            val serverInput = EditText(this).apply {
                setText(serverUrl)
                inputType = InputType.TYPE_TEXT_VARIATION_URI
                textSize = 14f
                setTextColor(Color.WHITE)
                setBackgroundColor(Color.parseColor("#1E293B"))
                setPadding(16, 12, 16, 12)
                isFocusable = true
                isFocusableInTouchMode = true
            }
            layout.addView(serverInput)

            // Screen ID input
            val screenLabel = TextView(this).apply {
                text = "\nScreen ID (dejar vacio para activacion):"
                textSize = 14f
                setTextColor(Color.parseColor("#E2E8F0"))
            }
            layout.addView(screenLabel)

            val screenInput = EditText(this).apply {
                setText(screenId)
                textSize = 14f
                setTextColor(Color.WHITE)
                setBackgroundColor(Color.parseColor("#1E293B"))
                setPadding(16, 12, 16, 12)
                isFocusable = true
                isFocusableInTouchMode = true
            }
            layout.addView(screenInput)

            val dialog = AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
                .setView(layout)
                .setPositiveButton("Guardar") { _, _ ->
                    val newServer = serverInput.text.toString().trim()
                    val newScreen = screenInput.text.toString().trim()

                    if (newServer.isNotEmpty()) {
                        serverUrl = newServer
                        prefs.edit().putString(PREF_SERVER_URL, newServer).apply()
                    }

                    screenId = newScreen
                    prefs.edit().putString(PREF_SCREEN_ID, newScreen).apply()

                    // Reload
                    if (screenId.isNotEmpty()) {
                        loadPlayer()
                    } else {
                        showSetupMode()
                    }

                    try { startLockTask() } catch (e: Exception) { }
                }
                .setNegativeButton("Cancelar") { _, _ ->
                    try { startLockTask() } catch (e: Exception) { }
                }
                .setNeutralButton("Reset") { _, _ ->
                    // Clear all settings and restart activation
                    prefs.edit().clear().apply()
                    serverUrl = DEFAULT_SERVER
                    screenId = ""
                    webView.clearCache(true)
                    webView.clearHistory()

                    // Clear WebView local storage
                    webView.evaluateJavascript(
                        "localStorage.clear(); sessionStorage.clear();", null
                    )

                    showSetupMode()
                    try { startLockTask() } catch (e: Exception) { }
                }
                .setCancelable(false)
                .create()

            dialog.window?.setBackgroundDrawableResource(android.R.color.background_dark)
            dialog.show()

        } catch (e: Exception) {
            Log.e(PlayerApp.TAG, "Settings dialog error: ${e.message}")
            try { startLockTask() } catch (e2: Exception) { }
        }
    }

    override fun onResume() {
        super.onResume()
        hideSystemUI()
        webView.onResume()
    }

    override fun onPause() {
        super.onPause()
        webView.onPause()
    }

    override fun onDestroy() {
        webView.destroy()
        releaseWakeLock()
        super.onDestroy()
    }

    /**
     * Prevent screen from sleeping - uses ALL methods that pro signage apps use:
     * 1. WakeLock (keeps CPU + screen on)
     * 2. Disable system screen timeout
     * 3. Disable screensaver
     * 4. Stay on while plugged in
     * 5. Watchdog timer that re-acquires wake lock periodically
     */
    @SuppressLint("WakelockTimeout")
    private fun preventScreenSleep() {
        try {
            // 1. Acquire WakeLock
            val pm = getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
            wakeLock = pm.newWakeLock(
                android.os.PowerManager.SCREEN_BRIGHT_WAKE_LOCK or android.os.PowerManager.ACQUIRE_CAUSES_WAKEUP,
                "MediAdView::ScreenOn"
            )
            wakeLock?.acquire()
            Log.i(PlayerApp.TAG, "WakeLock acquired")

            // 2. Disable screen timeout
            try {
                android.provider.Settings.System.putInt(
                    contentResolver,
                    android.provider.Settings.System.SCREEN_OFF_TIMEOUT,
                    Int.MAX_VALUE
                )
                Log.i(PlayerApp.TAG, "Screen timeout disabled")
            } catch (e: Exception) {
                Log.w(PlayerApp.TAG, "Cannot set screen timeout: ${e.message}")
            }

            // 3. Disable screensaver
            try {
                android.provider.Settings.Secure.putInt(
                    contentResolver,
                    "screensaver_enabled",
                    0
                )
                Log.i(PlayerApp.TAG, "Screensaver disabled")
            } catch (e: Exception) {
                Log.w(PlayerApp.TAG, "Cannot disable screensaver: ${e.message}")
            }

            // 4. Stay on while plugged in (USB + AC)
            try {
                android.provider.Settings.Global.putInt(
                    contentResolver,
                    android.provider.Settings.Global.STAY_ON_WHILE_PLUGGED_IN,
                    android.os.BatteryManager.BATTERY_PLUGGED_AC or
                    android.os.BatteryManager.BATTERY_PLUGGED_USB
                )
                Log.i(PlayerApp.TAG, "Stay on while plugged in enabled")
            } catch (e: Exception) {
                Log.w(PlayerApp.TAG, "Cannot set stay on: ${e.message}")
            }

            // 5. Watchdog - re-acquire wake lock every 5 minutes
            handler.postDelayed(object : Runnable {
                override fun run() {
                    try {
                        if (wakeLock?.isHeld == false) {
                            wakeLock?.acquire()
                            Log.i(PlayerApp.TAG, "WakeLock re-acquired by watchdog")
                        }
                        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                        hideSystemUI()
                    } catch (e: Exception) {
                        Log.w(PlayerApp.TAG, "Watchdog error: ${e.message}")
                    }
                    handler.postDelayed(this, 300000) // Every 5 minutes
                }
            }, 300000)

        } catch (e: Exception) {
            Log.e(PlayerApp.TAG, "preventScreenSleep error: ${e.message}")
        }
    }

    private fun releaseWakeLock() {
        try {
            wakeLock?.let {
                if (it.isHeld) {
                    it.release()
                    Log.i(PlayerApp.TAG, "WakeLock released")
                }
            }
        } catch (e: Exception) {
            Log.w(PlayerApp.TAG, "WakeLock release error: ${e.message}")
        }
    }

    /**
     * Schedule nightly app restart for stability.
     * Reloads the WebView at 3 AM to clear memory leaks and refresh content.
     */
    private fun scheduleNightlyRestart() {
        handler.postDelayed(object : Runnable {
            override fun run() {
                val cal = java.util.Calendar.getInstance()
                val hour = cal.get(java.util.Calendar.HOUR_OF_DAY)
                val minute = cal.get(java.util.Calendar.MINUTE)

                // Reboot at 3:00 AM
                if (hour == 3 && minute == 0) {
                    Log.i(PlayerApp.TAG, "Nightly restart triggered")
                    webView.clearCache(true)
                    webView.clearHistory()
                    if (screenId.isNotEmpty()) {
                        loadPlayer()
                    } else {
                        showSetupMode()
                    }
                }
                handler.postDelayed(this, 60000) // Check every minute
            }
        }, 60000)
    }
}
