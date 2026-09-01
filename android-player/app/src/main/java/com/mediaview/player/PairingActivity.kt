package com.mediaview.player

import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.util.TypedValue
import android.view.Gravity
import android.view.ViewGroup
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

/**
 * OptiSigns-style pairing screen shown on first launch.
 *
 * Flow:
 *   1. POST /api/devices/register  → backend returns { device_id, activation_code }
 *   2. Show activation_code (e.g. "MV7K2N") in huge letters + instructions.
 *   3. Long-poll GET /api/devices/{device_id}/check every 3s.
 *   4. When status == "active" and screen_id is set → persist screen_id, mark
 *      the device as paired, and launch MainActivity.
 *
 * The customer never types anything on the TV remote.
 */
class PairingActivity : AppCompatActivity() {

    private lateinit var codeView: TextView
    private lateinit var statusView: TextView
    private lateinit var subStatusView: TextView
    private lateinit var retryBtn: Button
    private var pollingJob: Job? = null
    private val handler = Handler(Looper.getMainLooper())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        supportActionBar?.hide()

        // ─── Build UI programmatically (no XML dependency) ─────────────
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#030712"))
            setPadding(96, 64, 96, 64)
            gravity = Gravity.CENTER
        }

        // Logo badge (rounded blue square with "MV")
        val logoWrap = FrameLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                dp(88), dp(88)
            ).apply {
                gravity = Gravity.CENTER_HORIZONTAL
                bottomMargin = dp(20)
            }
            background = android.graphics.drawable.GradientDrawable().apply {
                shape = android.graphics.drawable.GradientDrawable.RECTANGLE
                cornerRadius = dp(20).toFloat()
                colors = intArrayOf(
                    Color.parseColor("#6366F1"),
                    Color.parseColor("#4338CA")
                )
                orientation = android.graphics.drawable.GradientDrawable.Orientation.TL_BR
            }
        }
        val logoText = TextView(this).apply {
            text = "MV"
            setTextColor(Color.WHITE)
            textSize = 28f
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            gravity = Gravity.CENTER
            layoutParams = FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
        }
        logoWrap.addView(logoText)

        // Title
        val title = TextView(this).apply {
            text = "MediAd View Player"
            setTextColor(Color.WHITE)
            textSize = 30f
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            gravity = Gravity.CENTER
        }

        // Subtitle
        val subtitle = TextView(this).apply {
            text = "Empareja esta pantalla con tu cuenta"
            setTextColor(Color.parseColor("#94A3B8"))
            textSize = 15f
            gravity = Gravity.CENTER
            setPadding(0, dp(6), 0, dp(40))
        }

        // Activation code — HUGE
        codeView = TextView(this).apply {
            text = "· · · · · ·"
            setTextColor(Color.parseColor("#818CF8"))
            setTextSize(TypedValue.COMPLEX_UNIT_DIP, 72f)
            typeface = Typeface.create(Typeface.MONOSPACE, Typeface.BOLD)
            gravity = Gravity.CENTER
            letterSpacing = 0.18f
            setPadding(dp(24), dp(28), dp(24), dp(28))
            background = android.graphics.drawable.GradientDrawable().apply {
                shape = android.graphics.drawable.GradientDrawable.RECTANGLE
                cornerRadius = dp(20).toFloat()
                setColor(Color.parseColor("#111827"))
                setStroke(dp(2), Color.parseColor("#1E293B"))
            }
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            )
        }

        // Instructions block
        val steps = TextView(this).apply {
            text = "1.  Abre  panel.mediadview.com  en tu computadora\n" +
                   "2.  Ve a  Screens  →  Pair Device\n" +
                   "3.  Ingresa el código de arriba"
            setTextColor(Color.parseColor("#CBD5E1"))
            textSize = 17f
            gravity = Gravity.START
            setLineSpacing(dp(8).toFloat(), 1f)
            setPadding(dp(8), dp(28), dp(8), dp(28))
        }

        // Status bar (waiting / connecting / error)
        statusView = TextView(this).apply {
            text = "⏳  Esperando activación..."
            setTextColor(Color.parseColor("#818CF8"))
            textSize = 14f
            gravity = Gravity.CENTER
            setPadding(0, dp(16), 0, dp(4))
        }

        // Sub status (small technical info)
        subStatusView = TextView(this).apply {
            text = ""
            setTextColor(Color.parseColor("#475569"))
            textSize = 11f
            gravity = Gravity.CENTER
            setPadding(0, 0, 0, dp(12))
        }

        // Retry button (initially hidden, shown on errors)
        retryBtn = Button(this).apply {
            text = "Reintentar"
            visibility = ViewGroup.GONE.let { android.view.View.GONE }
            setBackgroundColor(Color.parseColor("#4338CA"))
            setTextColor(Color.WHITE)
            setPadding(dp(48), dp(16), dp(48), dp(16))
            setOnClickListener {
                visibility = android.view.View.GONE
                registerAndPoll()
            }
        }

        // Footer with version
        val footer = TextView(this).apply {
            text = "v${BuildConfig.VERSION_NAME}  ·  ${PlayerApi.baseUrl(this@PairingActivity)}"
            setTextColor(Color.parseColor("#334155"))
            textSize = 10f
            gravity = Gravity.CENTER
            setPadding(0, dp(32), 0, 0)
        }

        root.addView(logoWrap)
        root.addView(title)
        root.addView(subtitle)
        root.addView(codeView)
        root.addView(steps)
        root.addView(statusView)
        root.addView(subStatusView)
        root.addView(retryBtn)
        root.addView(footer)

        setContentView(root)

        registerAndPoll()
    }

    /** Register with the backend (if not registered yet) and start polling. */
    private fun registerAndPoll() {
        statusView.setTextColor(Color.parseColor("#818CF8"))
        statusView.text = "⏳  Conectando al servidor..."
        subStatusView.text = ""

        CoroutineScope(Dispatchers.IO).launch {
            try {
                // Force a fresh registration every time this activity opens if not paired.
                // (DeviceRegistrar.registerIfNeeded is idempotent — it early-exits when paired.)
                val res = DeviceRegistrar.registerIfNeeded(this@PairingActivity)
                val backendId: String? = res?.optString("device_id")
                    ?: DeviceIdentity.getBackendDeviceId(this@PairingActivity)
                val code: String? = res?.optString("activation_code")
                    ?: DeviceIdentity.getActivationCode(this@PairingActivity)

                if (backendId.isNullOrBlank()) {
                    withContext(Dispatchers.Main) { showError("No pude registrar el dispositivo. Revisa la conexión de red.") }
                    return@launch
                }

                withContext(Dispatchers.Main) {
                    codeView.text = formatCode(code ?: "------")
                    statusView.setTextColor(Color.parseColor("#818CF8"))
                    statusView.text = "⏳  Esperando activación..."
                    subStatusView.text = "device_id: ${backendId.take(12)}"
                }

                startPolling(backendId)
            } catch (e: Exception) {
                Log.e(PlayerApp.TAG, "Register error: ${e.message}", e)
                withContext(Dispatchers.Main) { showError(e.message?.take(200) ?: "Error de red") }
            }
        }
    }

    /** Long-poll /api/devices/{id}/check until status is "active" and screen_id is set. */
    private fun startPolling(deviceId: String) {
        pollingJob?.cancel()
        pollingJob = CoroutineScope(Dispatchers.IO).launch {
            var attempts = 0
            while (isActive) {
                attempts++
                try {
                    val res = PlayerApi.getJson(this@PairingActivity, "/api/devices/$deviceId/check")
                    val status = res.optString("status")
                    val screenId = res.optString("screen_id")
                    val screenName = res.optString("screen_name")

                    if (status == "active" && screenId.isNotBlank()) {
                        // Success! Persist screen_id and launch MainActivity.
                        getSharedPreferences(MainActivity.PREF_NAME, Context.MODE_PRIVATE).edit()
                            .putString(MainActivity.PREF_SCREEN_ID, screenId)
                            .apply()
                        withContext(Dispatchers.Main) {
                            statusView.setTextColor(Color.parseColor("#34D399"))
                            statusView.text = "✓  Emparejado con: ${screenName.ifBlank { "pantalla" }}"
                            subStatusView.text = "Iniciando reproducción..."
                        }
                        delay(1400)
                        withContext(Dispatchers.Main) { goToPlayer() }
                        return@launch
                    }

                    // Still pending — refresh the code shown in case backend rotated it
                    val activationCode = res.optString("activation_code")
                    withContext(Dispatchers.Main) {
                        if (activationCode.isNotBlank()) {
                            codeView.text = formatCode(activationCode)
                        }
                        // Small subtle status "heartbeat" so the customer knows it's live
                        val dots = ".".repeat((attempts % 4))
                        subStatusView.text = "esperando$dots  ·  chequeo #$attempts"
                    }
                } catch (e: Exception) {
                    Log.w(PlayerApp.TAG, "Poll error: ${e.message}")
                    withContext(Dispatchers.Main) {
                        subStatusView.text = "sin conexión, reintentando..."
                    }
                }
                delay(3000L)
            }
        }
    }

    private fun goToPlayer() {
        startActivity(Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        })
        finish()
    }

    private fun showError(msg: String) {
        statusView.setTextColor(Color.parseColor("#FCA5A5"))
        statusView.text = "✗  $msg"
        subStatusView.text = ""
        retryBtn.visibility = android.view.View.VISIBLE
    }

    /** Format activation code like "MV-7K2N" or "MV 7K 2N" for readability. */
    private fun formatCode(code: String): String {
        val clean = code.replace("-", "").replace(" ", "")
        return if (clean.length == 6) {
            "${clean.substring(0, 2)}  ${clean.substring(2, 4)}  ${clean.substring(4, 6)}"
        } else {
            clean.chunked(2).joinToString("  ")
        }
    }

    private fun dp(v: Int): Int =
        (v * resources.displayMetrics.density + 0.5f).toInt()

    override fun onDestroy() {
        pollingJob?.cancel()
        super.onDestroy()
    }

    override fun onBackPressed() {
        // Block back navigation during pairing.
    }
}
