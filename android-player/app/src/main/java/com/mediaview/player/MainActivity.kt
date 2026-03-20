package com.mediaview.player

import android.annotation.SuppressLint
import android.app.Activity
import android.app.ActivityManager
import android.content.Context
import android.graphics.Color
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.KeyEvent
import android.view.View
import android.view.WindowManager
import android.webkit.ConsoleMessage
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.TextView

/**
 * MediaView Player - Main Activity
 *
 * Production-grade digital signage player for Android TV / Fire TV.
 * Loads the Web Player Engine in a WebView with:
 * - Full screen immersive mode
 * - Screen always on (FLAG_KEEP_SCREEN_ON)
 * - Kiosk mode (Lock Task)
 * - Network monitoring & auto-reconnect
 * - Crash recovery
 */
class MainActivity : Activity() {

    private lateinit var webView: WebView
    private lateinit var statusView: TextView
    private val handler = Handler(Looper.getMainLooper())
    private var serverUrl = ""
    private var screenId = ""
    private var isConnected = false
    private var reconnectAttempts = 0
    private val MAX_RECONNECT_DELAY = 60000L // 60 seconds max

    // =================================================================
    // CONFIGURATION - Change these for your deployment
    // =================================================================
    companion object {
        // Your MediaView server URL
        // For production, change this to your actual server
        const val DEFAULT_SERVER = "https://screensync-ads.preview.emergentagent.com"

        // Screen ID - can be configured via:
        // 1. SharedPreferences (set via activation flow)
        // 2. Hardcoded for dedicated devices
        // 3. Intent extra when launched
        const val PREF_NAME = "mediaview_player"
        const val PREF_SERVER_URL = "server_url"
        const val PREF_SCREEN_ID = "screen_id"
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Log.i(PlayerApp.TAG, "MainActivity onCreate")

        // ===== FULL SCREEN + ALWAYS ON =====
        window.addFlags(
            WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON or
            WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
            WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
        )
        hideSystemUI()

        // ===== LOAD CONFIG =====
        val prefs = getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
        serverUrl = prefs.getString(PREF_SERVER_URL, DEFAULT_SERVER) ?: DEFAULT_SERVER
        screenId = prefs.getString(PREF_SCREEN_ID, "") ?: ""

        // Check intent extras (for initial setup)
        intent?.getStringExtra("server_url")?.let { serverUrl = it }
        intent?.getStringExtra("screen_id")?.let { screenId = it }

        // ===== BUILD UI =====
        val root = FrameLayout(this).apply {
            setBackgroundColor(Color.BLACK)
        }

        // Status overlay (shown during loading/errors)
        statusView = TextView(this).apply {
            setTextColor(Color.parseColor("#64748B"))
            textSize = 14f
            text = "MediaView Player - Initializing..."
            setPadding(32, 32, 32, 32)
            visibility = View.GONE
        }

        // WebView
        webView = WebView(this).apply {
            setBackgroundColor(Color.BLACK)

            settings.apply {
                javaScriptEnabled = true
                domStorageEnabled = true                    // localStorage for offline cache
                databaseEnabled = true
                mediaPlaybackRequiresUserGesture = false    // Auto-play video
                allowFileAccess = true
                cacheMode = WebSettings.LOAD_DEFAULT
                mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
                useWideViewPort = true
                loadWithOverviewMode = true
                setSupportZoom(false)

                // Performance optimizations for 24/7
                setRenderPriority(WebSettings.RenderPriority.HIGH)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    safeBrowsingEnabled = false
                }
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
                    Log.e(PlayerApp.TAG, "WebView error: $description ($errorCode)")
                    isConnected = false
                    scheduleReconnect()
                }
            }

            // Console logging
            webChromeClient = object : WebChromeClient() {
                override fun onConsoleMessage(message: ConsoleMessage?): Boolean {
                    message?.let {
                        Log.d(PlayerApp.TAG, "[WebView] ${it.message()} (${it.lineNumber()})")
                    }
                    return true
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
            loadPlayer()
        } else {
            showSetupMode()
        }

        // Start overlay service for auto-boot
        startOverlayService()

        // ===== KIOSK MODE =====
        startLockTask()
    }

    /**
     * Check and request "Display over other apps" permission.
     * This is what allows the app to auto-start on boot (like OptiSigns).
     */
    private fun checkOverlayPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            if (!android.provider.Settings.canDrawOverlays(this)) {
                val intent = Intent(
                    android.provider.Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    android.net.Uri.parse("package:$packageName")
                )
                startActivity(intent)
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
        statusView.text = "Loading MediaView Player..."
        statusView.visibility = View.VISIBLE

        if (isNetworkAvailable()) {
            webView.loadUrl(playerUrl)
        } else {
            Log.w(PlayerApp.TAG, "No network - will retry")
            statusView.text = "No network connection. Retrying..."
            statusView.visibility = View.VISIBLE
            scheduleReconnect()
        }
    }

    /**
     * Show setup instructions when no screen is configured
     */
    private fun showSetupMode() {
        // Load the web-based activation page - no ADB required
        val activateUrl = "$serverUrl/api/player-activate"
        Log.i(PlayerApp.TAG, "Loading activation page: $activateUrl")
        webView.loadUrl(activateUrl)
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
        statusView.text = "Reconnecting in ${delay/1000}s... (attempt #$reconnectAttempts)"
        statusView.visibility = View.VISIBLE

        handler.postDelayed({
            if (screenId.isNotEmpty()) {
                loadPlayer()
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
     * Handle key events - pass 'i' to WebView for diagnostics HUD
     */
    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        // Allow 'i' key for diagnostics
        if (keyCode == KeyEvent.KEYCODE_I) {
            webView.evaluateJavascript("document.dispatchEvent(new KeyboardEvent('keydown',{key:'i'}))", null)
            return true
        }
        // Block back button in kiosk mode
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            return true
        }
        return super.onKeyDown(keyCode, event)
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
        super.onDestroy()
    }
}
