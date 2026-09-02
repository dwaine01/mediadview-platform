package com.mediaview.player

import android.animation.ValueAnimator
import android.content.Context
import android.content.Intent
import android.content.pm.ActivityInfo
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.text.InputType
import android.util.Log
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.WindowManager
import android.view.animation.AccelerateDecelerateInterpolator
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

/**
 * PairingActivity — premium OptiSigns-style pairing screen with MediAd View branding.
 *
 * Flow:
 *   1. Register against POST /api/devices/register (idempotent).
 *   2. Show the returned 6-char activation code in oversized letters.
 *   3. Long-poll GET /api/devices/{device_id}/check every 3s until active.
 *   4. Persist screen_id and hand off to MainActivity.
 */
class PairingActivity : AppCompatActivity() {

    // ═══════ Premium palette ═══════
    private val colorBg = Color.parseColor("#050810")           // solid deep black-navy
    private val colorBgTop = Color.parseColor("#0A0F1C")        // slightly lighter top
    private val colorCardBg = Color.parseColor("#0F172A")
    private val colorCardBorder = Color.parseColor("#1E293B")
    private val colorLogoCardBg = Color.parseColor("#FFFFFF")   // white card behind logo (intentional)
    private val colorTextPrimary = Color.WHITE
    private val colorTextSecondary = Color.parseColor("#94A3B8")
    private val colorTextMuted = Color.parseColor("#475569")
    private val colorTextBody = Color.parseColor("#CBD5E1")
    private val colorAccent1 = Color.parseColor("#EC4899")       // brand pink
    private val colorAccent2 = Color.parseColor("#8B5CF6")       // brand purple
    private val colorAccent3 = Color.parseColor("#06B6D4")       // brand cyan
    private val colorSuccess = Color.parseColor("#10B981")
    private val colorError = Color.parseColor("#F87171")
    private val colorCode = Color.parseColor("#A78BFA")
    private val colorFooter = Color.parseColor("#334155")
    private val colorGlow = Color.parseColor("#3730A3")

    private lateinit var codeText: TextView
    private lateinit var statusText: TextView
    private lateinit var subStatusText: TextView
    private lateinit var retryButton: Button
    private lateinit var homeButton: Button
    private lateinit var statusDot: View

    private var job: Job? = null
    private var pulseAnim: ValueAnimator? = null
    private var clientUuid: String = ""     // stable local UUID
    private var serverDeviceId: String = "" // the id returned by /register (used for polling)
    private var checkCount: Int = 0
    private var lastActivationCode: String = ""

    companion object {
        const val PAIR_PREFS = "mediaview_pairing"
        const val KEY_SERVER_DEVICE_ID = "server_device_id"
        const val KEY_ACTIVATION_CODE = "activation_code"
    }

    private var menuKeyCount = 0
    private var lastMenuKeyTime = 0L
    private val MENU_KEY_TIMEOUT = 3000L
    private val MENU_KEY_COUNT_REQUIRED = 5
    private var dpadCenterDownTime = 0L
    private val LONG_PRESS_DURATION = 5000L

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        supportActionBar?.hide()
        // Support both landscape and portrait — Android TV usually lands landscape,
        // but portrait signage (menu boards) needs this too.
        requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        window.decorView.systemUiVisibility = (View.SYSTEM_UI_FLAG_FULLSCREEN
                or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                or View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION)

        clientUuid = DeviceIdentity.getDeviceId(this)
        PlayerDiagnostics.identity(null, false)
        // Restore previous server-issued device_id + code if we already registered.
        val pairPrefs = getSharedPreferences(PAIR_PREFS, Context.MODE_PRIVATE)
        serverDeviceId = pairPrefs.getString(KEY_SERVER_DEVICE_ID, "") ?: ""
        lastActivationCode = pairPrefs.getString(KEY_ACTIVATION_CODE, "") ?: ""
        setContentView(buildUi())
        startPulseAnimation()
        startRegisterAndPoll()
    }

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density).toInt()

    private fun buildUi(): View {
        // ═══════ Root with radial-ish glow effect ═══════
        val root = FrameLayout(this).apply {
            background = GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM,
                intArrayOf(colorBg, Color.parseColor("#020617"), colorBg)
            )
        }

        // ═══════ Content column, centered ═══════
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(80), dp(48), dp(80), dp(48))
        }

        // ═══════ Logo (real MediAd View brand image) ═══════
        val logo = ImageView(this).apply {
            try {
                val resId = resources.getIdentifier("logo_mediaview_dark", "drawable", packageName)
                if (resId != 0) setImageResource(resId)
            } catch (_: Exception) {}
            scaleType = ImageView.ScaleType.FIT_CENTER
            layoutParams = LinearLayout.LayoutParams(dp(360), dp(120)).apply {
                bottomMargin = dp(32)
            }
        }
        content.addView(logo)

        // ═══════ Tagline ═══════
        val tagline = TextView(this).apply {
            text = "DIGITAL SIGNAGE PLATFORM"
            textSize = 12f
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(colorTextSecondary)
            gravity = Gravity.CENTER
            letterSpacing = 0.4f
            setPadding(0, 0, 0, dp(48))
        }
        content.addView(tagline)

        // ═══════ Code card with premium glow border ═══════
        val codeCardWrap = FrameLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                gravity = Gravity.CENTER_HORIZONTAL
            }
        }

        // outer glow layer
        val glowLayer = View(this).apply {
            background = GradientDrawable().apply {
                cornerRadius = dp(28).toFloat()
                colors = intArrayOf(colorAccent1, colorAccent2, colorAccent3)
                orientation = GradientDrawable.Orientation.LEFT_RIGHT
                alpha = 60
            }
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ).apply {
                setMargins(-dp(2), -dp(2), -dp(2), -dp(2))
            }
        }
        codeCardWrap.addView(glowLayer)

        val codeCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(48), dp(36), dp(48), dp(36))
            background = GradientDrawable().apply {
                setColor(colorCardBg)
                setStroke(dp(1), colorCardBorder)
                cornerRadius = dp(24).toFloat()
            }
        }

        codeText = TextView(this).apply {
            text = "\u00b7  \u00b7  \u00b7  \u00b7  \u00b7  \u00b7"
            textSize = 56f
            setTypeface(Typeface.MONOSPACE, Typeface.BOLD)
            setTextColor(colorCode)
            gravity = Gravity.CENTER
            letterSpacing = 0.18f
            maxLines = 1
            includeFontPadding = false
        }
        codeCard.addView(codeText)
        codeCardWrap.addView(codeCard)

        val codeCardParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply { gravity = Gravity.CENTER_HORIZONTAL }
        codeCardWrap.layoutParams = codeCardParams
        content.addView(codeCardWrap)

        // ═══════ Instructions ═══════
        val instructions = TextView(this).apply {
            text = "1.  Open  panel.mediadview.com  on your computer\n" +
                "2.  Go to  Devices  \u2192  Link Device by Code\n" +
                "3.  Enter the code above and select a screen"
            textSize = 16f
            setTextColor(colorTextBody)
            gravity = Gravity.CENTER
            setLineSpacing(dp(6).toFloat(), 1f)
            setPadding(0, dp(48), 0, dp(0))
        }
        content.addView(instructions)

        // ═══════ Status row (dot + text) ═══════
        val statusRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            setPadding(0, dp(32), 0, 0)
        }

        statusDot = View(this).apply {
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(colorCode)
            }
            layoutParams = LinearLayout.LayoutParams(dp(10), dp(10)).apply {
                rightMargin = dp(12)
                gravity = Gravity.CENTER_VERTICAL
            }
        }
        statusRow.addView(statusDot)

        statusText = TextView(this).apply {
            text = "Connecting to server..."
            textSize = 14f
            setTextColor(colorCode)
            gravity = Gravity.CENTER_VERTICAL
            letterSpacing = 0.05f
        }
        statusRow.addView(statusText)
        content.addView(statusRow)

        subStatusText = TextView(this).apply {
            text = ""
            textSize = 11f
            setTextColor(colorTextMuted)
            gravity = Gravity.CENTER
            setPadding(0, dp(8), 0, 0)
            letterSpacing = 0.08f
        }
        content.addView(subStatusText)

        retryButton = Button(this).apply {
            text = "RETRY"
            setAllCaps(true)
            setTextColor(Color.WHITE)
            typeface = Typeface.create(typeface, Typeface.BOLD)
            letterSpacing = 0.15f
            background = GradientDrawable().apply {
                cornerRadius = dp(12).toFloat()
                colors = intArrayOf(colorAccent2, colorAccent1)
                orientation = GradientDrawable.Orientation.LEFT_RIGHT
            }
            setPadding(dp(56), dp(18), dp(56), dp(18))
            visibility = View.GONE
            setOnClickListener {
                visibility = View.GONE
                startRegisterAndPoll()
            }
        }
        val retryParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply {
            topMargin = dp(24)
            gravity = Gravity.CENTER
        }
        retryButton.layoutParams = retryParams
        content.addView(retryButton)

        homeButton = Button(this).apply {
            text = "CONFIGURE AUTO-START"
            setTextColor(colorTextBody)
            setBackgroundColor(colorCardBg)
            visibility = if (KioskSetup.isDefaultHome(this@PairingActivity)) View.GONE else View.VISIBLE
            setOnClickListener { KioskSetup.requestHomeRole(this@PairingActivity) }
        }
        homeButton.layoutParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = dp(16); gravity = Gravity.CENTER }
        content.addView(homeButton)

        val footer = TextView(this).apply {
            text = "v${BuildConfig.VERSION_NAME}  \u2022  mediadview.com"
            textSize = 10f
            setTextColor(colorFooter)
            gravity = Gravity.CENTER
            setPadding(0, dp(40), 0, 0)
            letterSpacing = 0.15f
        }
        content.addView(footer)

        val contentParams = FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        )
        content.layoutParams = contentParams
        root.addView(content)
        return root
    }

    private fun startPulseAnimation() {
        pulseAnim?.cancel()
        pulseAnim = ValueAnimator.ofFloat(0.35f, 1f, 0.35f).apply {
            duration = 1600
            repeatCount = ValueAnimator.INFINITE
            interpolator = AccelerateDecelerateInterpolator()
            addUpdateListener { anim ->
                statusDot.alpha = anim.animatedValue as Float
            }
            start()
        }
    }

    private fun formatCode(raw: String): String {
        val clean = raw.trim().uppercase()
        if (clean.isEmpty()) return "\u00b7  \u00b7  \u00b7  \u00b7  \u00b7  \u00b7"
        return clean.toCharArray().joinToString("  ")
    }

    private fun setStatus(text: String, color: Int) {
        statusText.text = text
        statusText.setTextColor(color)
        (statusDot.background as? GradientDrawable)?.setColor(color)
    }

    private fun startRegisterAndPoll() {
        job?.cancel()
        job = CoroutineScope(Dispatchers.IO).launch { registerAndPoll() }
    }

    private suspend fun registerAndPoll() {
        withContext(Dispatchers.Main) {
            // If we already have a persisted code from a previous run, show it
            // IMMEDIATELY so it doesn't flicker.
            if (lastActivationCode.isNotBlank()) {
                codeText.text = formatCode(lastActivationCode)
                setStatus("Waiting for activation...", colorCode)
            } else {
                setStatus("Connecting to server...", colorCode)
            }
            subStatusText.text = ""
            retryButton.visibility = View.GONE
        }

        val registered = try {
            val payload = JSONObject().apply {
                put("client_uuid", clientUuid)      // stable local UUID (backend key)
                put("device_id", clientUuid)        // legacy alias (backwards compat)
                put("device_name", "MediAd Player")
                put("device_model", android.os.Build.MODEL)
                put("model", android.os.Build.MODEL)
                put("os_version", "Android ${android.os.Build.VERSION.RELEASE}")
                put("app_version", BuildConfig.VERSION_NAME)
            }
            val res = PlayerApi.postJson(this@PairingActivity, "/api/devices/register", payload)
            val code = res.optString("activation_code", "")
            val srvId = res.optString("device_id", "")
            if (srvId.isNotBlank()) {
                serverDeviceId = srvId
            }
            if (code.isNotBlank()) {
                lastActivationCode = code
                DeviceIdentity.markRegistered(
                    this@PairingActivity,
                    if (srvId.isNotBlank()) srvId else clientUuid,
                    code
                )
            }
            // Persist so the code stays STABLE across relaunches / rotations.
            getSharedPreferences(PAIR_PREFS, Context.MODE_PRIVATE).edit()
                .putString(KEY_SERVER_DEVICE_ID, serverDeviceId)
                .putString(KEY_ACTIVATION_CODE, lastActivationCode)
                .apply()
            true
        } catch (e: Exception) {
            Log.e(PlayerApp.TAG, "Pairing: register failed: ${e.message}")
            PlayerDiagnostics.playerError("pairing register: ${e.message}")
            withContext(Dispatchers.Main) {
                // If we already had a cached code from before, keep showing it —
                // don't nuke the code just because network is momentarily down.
                if (lastActivationCode.isBlank()) {
                    setStatus("Connection error", colorError)
                    subStatusText.text = e.message?.take(80) ?: "could not reach server"
                    retryButton.visibility = View.VISIBLE
                } else {
                    setStatus("Reconnecting...", colorError)
                    subStatusText.text = "network offline — will keep trying"
                }
            }
            // Keep polling anyway if we have a cached code.
            lastActivationCode.isNotBlank()
        }

        if (!registered) return

        withContext(Dispatchers.Main) {
            codeText.text = formatCode(lastActivationCode)
            setStatus("Waiting for activation...", colorCode)
        }

        // Use the SERVER-issued device id for polling. Fall back to the local
        // UUID for legacy backends (they now support both).
        val pollId = if (serverDeviceId.isNotBlank()) serverDeviceId else clientUuid

        checkCount = 0
        while (job?.isActive == true) {
            checkCount++
            withContext(Dispatchers.Main) {
                subStatusText.text = "check #$checkCount"
            }
            try {
                val res = PlayerApi.getJson(this@PairingActivity, "/api/devices/$pollId/check")
                val status = res.optString("status", "pending")
                val code = res.optString("activation_code", "")
                if (code.isNotBlank() && code != lastActivationCode) {
                    lastActivationCode = code
                    getSharedPreferences(PAIR_PREFS, Context.MODE_PRIVATE).edit()
                        .putString(KEY_ACTIVATION_CODE, code)
                        .apply()
                }

                val screenId = res.optString("screen_id", "")
                if (PairingPolicy.decide(status, screenId) == PairingDecision.INVALID_ACTIVE_STATE) {
                    throw IllegalStateException("active device has no screen_id")
                }
                if (PairingPolicy.decide(status, screenId) == PairingDecision.START_PLAYER) {
                    val screenName = res.optString("screen_name", "")
                    val serverUrl = res.optString("server_url", "")
                    if (serverUrl.isNotBlank()) {
                        PlayerApi.setBaseUrl(this@PairingActivity, serverUrl)
                    }
                    DeviceIdentity.markPaired(
                        this@PairingActivity,
                        pollId,
                        lastActivationCode,
                        screenId,
                        screenName,
                    )
                    PlayerDiagnostics.identity(screenId, true)
                    HeartbeatWorker.enqueuePeriodic(this@PairingActivity)

                    withContext(Dispatchers.Main) {
                        codeText.text = formatCode(lastActivationCode)
                        pulseAnim?.cancel()
                        statusDot.alpha = 1f
                        setStatus("Paired with $screenName", colorSuccess)
                        subStatusText.text = "starting player..."
                    }
                    delay(1600)
                    withContext(Dispatchers.Main) { goToPlayer() }
                    return
                } else {
                    withContext(Dispatchers.Main) {
                        codeText.text = formatCode(lastActivationCode)
                        setStatus("Waiting for activation...", colorCode)
                    }
                }
            } catch (e: Exception) {
                Log.w(PlayerApp.TAG, "Pairing: check failed (#$checkCount): ${e.message}")
                PlayerDiagnostics.playerError("pairing check: ${e.message}")
                withContext(Dispatchers.Main) {
                    subStatusText.text = "check #$checkCount  \u2022  retrying network"
                }
            }
            delay(3000)
        }
    }

    private fun goToPlayer() {
        job?.cancel()
        pulseAnim?.cancel()
        startActivity(Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        })
        finish()
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_MENU || keyCode == KeyEvent.KEYCODE_F1) {
            val now = System.currentTimeMillis()
            if (now - lastMenuKeyTime > MENU_KEY_TIMEOUT) menuKeyCount = 0
            menuKeyCount++
            lastMenuKeyTime = now
            if (menuKeyCount >= MENU_KEY_COUNT_REQUIRED) {
                menuKeyCount = 0
                requestAdminAccess()
            }
            return true
        }
        if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER) {
            if (event?.repeatCount == 0) dpadCenterDownTime = System.currentTimeMillis()
            if (dpadCenterDownTime > 0 &&
                System.currentTimeMillis() - dpadCenterDownTime >= LONG_PRESS_DURATION
            ) {
                dpadCenterDownTime = Long.MAX_VALUE
                requestAdminAccess()
                return true
            }
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onKeyUp(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER) {
            dpadCenterDownTime = 0L
        }
        return super.onKeyUp(keyCode, event)
    }

    override fun onBackPressed() { /* blocked */ }

    private fun showAdminMenu() {
        val info = "Server URL: ${PlayerApi.baseUrl(this)}\n" +
                "Device ID: ${clientUuid.take(24)}\n" +
                "Version: ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})"
        AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
            .setTitle("Admin menu")
            .setMessage(info)
            .setPositiveButton("Close", null)
            .setNeutralButton("Manual pairing") { _, _ ->
                startActivity(Intent(this, SetupActivity::class.java))
            }
            .setNegativeButton("Reset device") { _, _ ->
                job?.cancel()
                pulseAnim?.cancel()
                DeviceIdentity.clearPairing(this)
                getSharedPreferences(MainActivity.PREF_NAME, Context.MODE_PRIVATE)
                    .edit().clear().apply()
                getSharedPreferences(PAIR_PREFS, Context.MODE_PRIVATE)
                    .edit().clear().apply()
                recreate()
            }
            .setCancelable(true)
            .show()
    }

    private fun requestAdminAccess() {
        val input = EditText(this).apply {
            hint = "Device PIN"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
            .setTitle("Admin access")
            .setView(input)
            .setPositiveButton("Unlock") { _, _ ->
                val allowed = DiagnosticAccessPolicy.matches(
                    input.text?.toString(),
                    lastActivationCode,
                    BuildConfig.DIAGNOSTICS_PIN,
                )
                if (allowed) showAdminMenu()
                else Toast.makeText(this, "Access denied", Toast.LENGTH_SHORT).show()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    override fun onDestroy() {
        job?.cancel()
        pulseAnim?.cancel()
        super.onDestroy()
    }

    override fun onResume() {
        super.onResume()
        if (::homeButton.isInitialized) {
            homeButton.visibility = if (KioskSetup.isDefaultHome(this)) View.GONE else View.VISIBLE
        }
    }
}
