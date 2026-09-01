package com.mediaview.player

import android.content.Context
import android.content.Intent
import android.content.pm.ActivityInfo
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.util.Log
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
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
 * PairingActivity - native OptiSigns-style pairing screen.
 *
 * Shown whenever the device has not been paired to a screen yet.
 * Flow:
 *   1. Register against POST /api/devices/register (idempotent).
 *   2. Show the returned 6-char activation code in large text.
 *   3. Long-poll GET /api/devices/{device_id}/check every 3s until
 *      status=active with a screen_id.
 *   4. Persist screen_id and hand off to MainActivity.
 *
 * Hidden admin menu: press MENU 5x quickly, or hold DPAD_CENTER 5s.
 */
class PairingActivity : AppCompatActivity() {

    // Palette
    private val colorBg = Color.parseColor("#030712")
    private val colorCard = Color.parseColor("#111827")
    private val colorCardBorder = Color.parseColor("#1E293B")
    private val colorTextPrimary = Color.WHITE
    private val colorTextSecondary = Color.parseColor("#94A3B8")
    private val colorTextMuted = Color.parseColor("#475569")
    private val colorTextBody = Color.parseColor("#CBD5E1")
    private val colorAccentStart = Color.parseColor("#6366F1")
    private val colorAccentEnd = Color.parseColor("#4338CA")
    private val colorSuccess = Color.parseColor("#34D399")
    private val colorError = Color.parseColor("#FCA5A5")
    private val colorCode = Color.parseColor("#818CF8")
    private val colorFooter = Color.parseColor("#334155")

    private lateinit var codeText: TextView
    private lateinit var statusText: TextView
    private lateinit var subStatusText: TextView
    private lateinit var retryButton: Button

    private var job: Job? = null
    private var deviceId: String = ""
    private var checkCount: Int = 0
    private var lastActivationCode: String = ""

    private var menuKeyCount = 0
    private var lastMenuKeyTime = 0L
    private val MENU_KEY_TIMEOUT = 3000L
    private val MENU_KEY_COUNT_REQUIRED = 5
    private var dpadCenterDownTime = 0L
    private val LONG_PRESS_DURATION = 5000L

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        supportActionBar?.hide()
        requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        deviceId = DeviceIdentity.getDeviceId(this)
        setContentView(buildUi())
        startRegisterAndPoll()
    }

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density).toInt()

    private fun buildUi(): View {
        val root = FrameLayout(this).apply { setBackgroundColor(colorBg) }
        val scroll = ScrollView(this).apply { isFillViewport = true }
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(96), dp(64), dp(96), dp(64))
        }

        val logo = TextView(this).apply {
            text = "MV"
            textSize = 28f
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(dp(88), dp(88))
            background = GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                intArrayOf(colorAccentStart, colorAccentEnd)
            ).apply { cornerRadius = dp(20).toFloat() }
        }
        content.addView(logo)

        val title = TextView(this).apply {
            text = "MediAd View Player"
            textSize = 30f
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(colorTextPrimary)
            gravity = Gravity.CENTER
            setPadding(0, dp(20), 0, 0)
        }
        content.addView(title)

        val subtitle = TextView(this).apply {
            text = "Empareja esta pantalla con tu cuenta"
            textSize = 15f
            setTextColor(colorTextSecondary)
            gravity = Gravity.CENTER
            setPadding(0, dp(4), 0, dp(40))
        }
        content.addView(subtitle)

        val codeCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(24), dp(28), dp(24), dp(28))
            background = GradientDrawable().apply {
                setColor(colorCard)
                setStroke(dp(2), colorCardBorder)
                cornerRadius = dp(20).toFloat()
            }
        }
        codeText = TextView(this).apply {
            text = "\u00b7 \u00b7 \u00b7 \u00b7 \u00b7 \u00b7"
            textSize = 72f
            setTypeface(Typeface.MONOSPACE, Typeface.BOLD)
            setTextColor(colorCode)
            gravity = Gravity.CENTER
            letterSpacing = 0.18f
        }
        codeCard.addView(codeText)
        content.addView(codeCard)

        val instructions = TextView(this).apply {
            text = "1.  Abre  panel.mediadview.com  en tu computadora\n" +
                "2.  Ve a  Screens  \u2192  Pair Device\n" +
                "3.  Ingresa el codigo de arriba"
            textSize = 17f
            setTextColor(colorTextBody)
            gravity = Gravity.CENTER
            setLineSpacing(dp(8).toFloat(), 1f)
            setPadding(0, dp(40), 0, 0)
        }
        content.addView(instructions)

        statusText = TextView(this).apply {
            text = "\u23f3  Conectando al servidor..."
            textSize = 14f
            setTextColor(colorCode)
            gravity = Gravity.CENTER
            setPadding(0, dp(28), 0, 0)
        }
        content.addView(statusText)

        subStatusText = TextView(this).apply {
            text = ""
            textSize = 11f
            setTextColor(colorTextMuted)
            gravity = Gravity.CENTER
            setPadding(0, dp(6), 0, 0)
        }
        content.addView(subStatusText)

        retryButton = Button(this).apply {
            text = "Reintentar"
            setAllCaps(false)
            setTextColor(Color.WHITE)
            setBackgroundColor(colorAccentEnd)
            setPadding(dp(48), dp(16), dp(48), dp(16))
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
            topMargin = dp(20)
            gravity = Gravity.CENTER
        }
        retryButton.layoutParams = retryParams
        content.addView(retryButton)

        val footer = TextView(this).apply {
            text = "v${BuildConfig.VERSION_NAME}  \u00b7  https://mediadview.com"
            textSize = 10f
            setTextColor(colorFooter)
            gravity = Gravity.CENTER
            setPadding(0, dp(32), 0, 0)
        }
        content.addView(footer)

        scroll.addView(
            content,
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.WRAP_CONTENT
        )
        root.addView(scroll)
        return root
    }

    private fun formatCode(raw: String): String {
        val clean = raw.trim().uppercase()
        if (clean.isEmpty()) return "\u00b7 \u00b7 \u00b7 \u00b7 \u00b7 \u00b7"
        return clean.chunked(2).joinToString("  ")
    }

    private fun setStatus(text: String, color: Int) {
        statusText.text = text
        statusText.setTextColor(color)
    }

    private fun startRegisterAndPoll() {
        job?.cancel()
        job = CoroutineScope(Dispatchers.IO).launch {
            registerAndPoll()
        }
    }

    private suspend fun registerAndPoll() {
        withContext(Dispatchers.Main) {
            setStatus("\u23f3  Conectando al servidor...", colorCode)
            subStatusText.text = ""
            retryButton.visibility = View.GONE
        }

        val registered = try {
            val payload = JSONObject().apply {
                put("device_id", deviceId)
                put("device_name", "MediAd Player")
                put("model", "Android TV")
            }
            val res = PlayerApi.postJson(this@PairingActivity, "/api/devices/register", payload)
            val code = res.optString("activation_code", "")
            if (code.isNotBlank()) {
                lastActivationCode = code
                DeviceIdentity.markRegistered(this@PairingActivity, res.optString("device_id", deviceId), code)
            }
            true
        } catch (e: Exception) {
            Log.e(PlayerApp.TAG, "Pairing: register failed: ${e.message}")
            withContext(Dispatchers.Main) {
                setStatus("\u2717  Error de conexion", colorError)
                subStatusText.text = e.message?.take(80) ?: "no se pudo contactar al servidor"
                retryButton.visibility = View.VISIBLE
            }
            false
        }

        if (!registered) return

        withContext(Dispatchers.Main) {
            codeText.text = formatCode(lastActivationCode)
            setStatus("\u23f3  Esperando activacion...", colorCode)
        }

        checkCount = 0
        while (job?.isActive == true) {
            checkCount++
            withContext(Dispatchers.Main) {
                subStatusText.text = "esperando..  \u00b7  chequeo #$checkCount"
            }
            try {
                val res = PlayerApi.getJson(this@PairingActivity, "/api/devices/$deviceId/check")
                val status = res.optString("status", "pending")
                val code = res.optString("activation_code", "")
                if (code.isNotBlank()) lastActivationCode = code

                if (status == "active") {
                    val screenId = res.optString("screen_id", "")
                    val screenName = res.optString("screen_name", "")
                    val serverUrl = res.optString("server_url", "")

                    if (serverUrl.isNotBlank()) {
                        PlayerApi.setBaseUrl(this@PairingActivity, serverUrl)
                    }
                    getSharedPreferences(MainActivity.PREF_NAME, Context.MODE_PRIVATE)
                        .edit()
                        .putString(MainActivity.PREF_SCREEN_ID, screenId)
                        .putString(MainActivity.PREF_DEVICE_NAME, screenName)
                        .apply()

                    withContext(Dispatchers.Main) {
                        codeText.text = formatCode(lastActivationCode)
                        setStatus("\u2713  Emparejado con: $screenName", colorSuccess)
                        subStatusText.text = ""
                    }

                    delay(1400)
                    withContext(Dispatchers.Main) { goToPlayer() }
                    return
                } else {
                    withContext(Dispatchers.Main) {
                        codeText.text = formatCode(lastActivationCode)
                        setStatus("\u23f3  Esperando activacion...", colorCode)
                    }
                }
            } catch (e: Exception) {
                Log.w(PlayerApp.TAG, "Pairing: check failed (#$checkCount): ${e.message}")
                withContext(Dispatchers.Main) {
                    subStatusText.text = "esperando..  \u00b7  chequeo #$checkCount  \u00b7  reintentando red"
                }
            }
            delay(3000)
        }
    }

    private fun goToPlayer() {
        job?.cancel()
        startActivity(
            Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            }
        )
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
                showAdminMenu()
            }
            return true
        }

        if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER) {
            if (event?.repeatCount == 0) {
                dpadCenterDownTime = System.currentTimeMillis()
            }
            if (dpadCenterDownTime > 0 &&
                System.currentTimeMillis() - dpadCenterDownTime >= LONG_PRESS_DURATION
            ) {
                dpadCenterDownTime = Long.MAX_VALUE
                showAdminMenu()
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

    override fun onBackPressed() {
        // Blocked: kiosk pairing screen, nowhere to go back.
    }

    private fun showAdminMenu() {
        val info = "Server URL: ${PlayerApi.baseUrl(this)}\n" +
            "Device ID: $deviceId\n" +
            "Version: ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})"

        AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
            .setTitle("Menu de administrador")
            .setMessage(info)
            .setPositiveButton("Cerrar", null)
            .setNeutralButton("Emparejamiento manual") { _, _ ->
                startActivity(Intent(this, SetupActivity::class.java))
            }
            .setNegativeButton("Reset device") { _, _ ->
                job?.cancel()
                getSharedPreferences("mediaview_identity", Context.MODE_PRIVATE).edit().clear().apply()
                getSharedPreferences(MainActivity.PREF_NAME, Context.MODE_PRIVATE).edit().clear().apply()
                recreate()
            }
            .setCancelable(true)
            .show()
    }

    override fun onDestroy() {
        job?.cancel()
        super.onDestroy()
    }
}
