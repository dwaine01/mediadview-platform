package com.mediaview.player

import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

/**
 * Pairing screen — shown on first launch (and any time the device is not paired).
 * Customer enters: Device ID (pairing code) + Secret Key + optional Server URL.
 * On success, persists config and launches MainActivity.
 */
class SetupActivity : AppCompatActivity() {

    private lateinit var deviceIdInput: EditText
    private lateinit var secretInput: EditText
    private lateinit var serverInput: EditText
    private lateinit var connectBtn: Button
    private lateinit var statusView: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        supportActionBar?.hide()

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#0A0A0A"))
            setPadding(80, 80, 80, 80)
            gravity = Gravity.CENTER
        }

        val title = TextView(this).apply {
            text = "MediAd View Player"
            textSize = 32f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
        }

        val subtitle = TextView(this).apply {
            text = "Connect this device to a screen on your MediAd View dashboard"
            textSize = 14f
            setTextColor(Color.parseColor("#9CA3AF"))
            gravity = Gravity.CENTER
            setPadding(0, 12, 0, 48)
        }

        deviceIdInput = makeInput("Device ID", "MV-XXXX-XXXX")
        secretInput   = makeInput("Secret Key", "Secret provided by your admin")
        serverInput   = makeInput("Server URL (optional)", PlayerApp.DEFAULT_SERVER_URL)
        serverInput.setText(PlayerApi.baseUrl(this))

        connectBtn = Button(this).apply {
            text = "Connect Device"
            textSize = 18f
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.parseColor("#2563EB"))
            setPadding(60, 36, 60, 36)
        }
        val btnParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { topMargin = 32 }
        connectBtn.layoutParams = btnParams

        statusView = TextView(this).apply {
            textSize = 14f
            setTextColor(Color.parseColor("#9CA3AF"))
            gravity = Gravity.CENTER
            setPadding(0, 24, 0, 0)
        }

        val footer = TextView(this).apply {
            text = "v${BuildConfig.VERSION_NAME}  ·  Need help? Contact your administrator."
            textSize = 11f
            setTextColor(Color.parseColor("#525866"))
            gravity = Gravity.CENTER
            setPadding(0, 48, 0, 0)
        }

        root.addView(title)
        root.addView(subtitle)
        root.addView(deviceIdInput)
        root.addView(secretInput)
        root.addView(serverInput)
        root.addView(connectBtn)
        root.addView(statusView)
        root.addView(footer)

        setContentView(root)

        connectBtn.setOnClickListener { doPair() }
    }

    private fun makeInput(label: String, hint: String): EditText {
        val labelView = TextView(this).apply {
            text = label
            textSize = 13f
            setTextColor(Color.parseColor("#E5E7EB"))
            setPadding(8, 12, 0, 6)
        }
        // attach the label as a sibling via reflection? simpler: just keep it inline via the EditText's hint
        return EditText(this).apply {
            this.hint = "$label: $hint"
            setHintTextColor(Color.parseColor("#6B7280"))
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.parseColor("#1F2937"))
            setPadding(32, 28, 32, 28)
            textSize = 17f
            inputType = InputType.TYPE_CLASS_TEXT
            setSingleLine(true)
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = 12 }
        }
    }

    private fun doPair() {
        val code = deviceIdInput.text.toString().trim().uppercase()
        val secret = secretInput.text.toString().trim()
        val server = serverInput.text.toString().trim()

        if (code.isEmpty() || secret.isEmpty()) {
            statusView.setTextColor(Color.parseColor("#FCA5A5"))
            statusView.text = "Please fill in Device ID and Secret Key."
            return
        }
        if (server.isNotBlank()) PlayerApi.setBaseUrl(this, server)

        connectBtn.isEnabled = false
        connectBtn.text = "Connecting..."
        statusView.setTextColor(Color.parseColor("#9CA3AF"))
        statusView.text = "Verifying credentials with server..."

        CoroutineScope(Dispatchers.IO).launch {
            val payload = JSONObject().apply {
                put("pairing_code",   code)
                put("pairing_secret", secret)
                put("device_model",   DeviceIdentity.deviceModel())
                put("device_name",    "MediAd View A40 — ${android.os.Build.MODEL}")
                put("os_version",     DeviceIdentity.osVersion())
                put("app_version",    BuildConfig.VERSION_NAME)
                put("app_version_code", BuildConfig.VERSION_CODE)
                put("client_uuid",    DeviceIdentity.getDeviceId(this@SetupActivity))
            }
            try {
                val res = PlayerApi.postJson(this@SetupActivity, "/api/devices/pair", payload)
                val backendId = res.optString("device_id")
                val screenName = res.optString("screen_name", "-")
                val screenId   = res.optString("screen_id")
                DeviceIdentity.markRegistered(this@SetupActivity, backendId, code)
                // Save the screen_id for the player to load
                getSharedPreferences("mediaview_identity", Context.MODE_PRIVATE).edit()
                    .putString("screen_id", screenId)
                    .putString("screen_name", screenName)
                    .apply()
                withContext(Dispatchers.Main) {
                    statusView.setTextColor(Color.parseColor("#86EFAC"))
                    statusView.text = "✓ Connected to: $screenName\nStarting playback..."
                    // After 1.2s, launch MainActivity
                    connectBtn.postDelayed({
                        startActivity(Intent(this@SetupActivity, MainActivity::class.java).apply {
                            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
                        })
                        finish()
                    }, 1200)
                }
            } catch (e: Exception) {
                val msg = e.message ?: "Unknown error"
                withContext(Dispatchers.Main) {
                    connectBtn.isEnabled = true
                    connectBtn.text = "Connect Device"
                    statusView.setTextColor(Color.parseColor("#FCA5A5"))
                    statusView.text = "✗ ${msg.take(200)}"
                }
            }
        }
    }
}
