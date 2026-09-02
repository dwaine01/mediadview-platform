package com.mediaview.player

import org.json.JSONObject
import java.net.URL

enum class MediaKind { VIDEO, IMAGE, HTML }
enum class DisplayMode(val wireValue: String) {
    COVER("cover"), CONTAIN("contain"), STRETCH("stretch");

    companion object {
        fun parse(value: String?): DisplayMode = entries.firstOrNull {
            it.wireValue == value?.trim()?.lowercase()
        } ?: COVER
    }
}

data class PlaylistItemModel(
    val mediaId: String,
    val campaignId: String,
    val filename: String,
    val contentType: String,
    val durationSeconds: Int,
    val rotation: Int,
    val displayMode: DisplayMode,
    val sourceUrl: String,
    val checksum: String?,
    val expectedBytes: Long,
    val orderIndex: Int,
    val localPath: String? = null,
) {
    val kind: MediaKind
        get() = when {
            contentType.startsWith("image/") -> MediaKind.IMAGE
            contentType == "widget" || contentType.contains("html") -> MediaKind.HTML
            else -> MediaKind.VIDEO
        }
}

data class PlaylistSnapshot(
    val screenId: String,
    val screenName: String,
    val resolution: String,
    val version: Long,
    val generatedAt: String,
    val items: List<PlaylistItemModel>,
)

object PlaylistJsonParser {
    fun parse(json: JSONObject, baseUrl: String): PlaylistSnapshot {
        val array = json.optJSONArray("items")
        val items = ArrayList<PlaylistItemModel>()
        if (array != null) {
            for (index in 0 until array.length()) {
                val raw = array.getJSONObject(index)
                val path = raw.optString("download_url", raw.optString("media_url", ""))
                if (raw.optString("media_id").isBlank() || path.isBlank()) continue
                items += PlaylistItemModel(
                    mediaId = raw.getString("media_id"),
                    campaignId = raw.optString("campaign_id", ""),
                    filename = raw.optString("filename", raw.getString("media_id")),
                    contentType = raw.optString("content_type", "application/octet-stream"),
                    durationSeconds = raw.optInt("duration", 15).coerceIn(1, 86_400),
                    rotation = raw.optInt("rotation", 0),
                    displayMode = DisplayMode.parse(raw.optString("display_mode", "cover")),
                    sourceUrl = absoluteUrl(baseUrl, path),
                    checksum = raw.optString("checksum", "").takeIf { it.matches(Regex("[0-9a-fA-F]{64}")) },
                    expectedBytes = raw.optLong("size", 0L).coerceAtLeast(0L),
                    orderIndex = index,
                )
            }
        }
        return PlaylistSnapshot(
            screenId = json.optString("screen_id", ""),
            screenName = json.optString("screen_name", "Screen"),
            resolution = json.optString("resolution", "1920x1080"),
            version = json.optLong("playlist_version", 0L),
            generatedAt = json.optString("generated_at", ""),
            items = items,
        )
    }

    private fun absoluteUrl(baseUrl: String, path: String): String =
        if (path.startsWith("http://") || path.startsWith("https://")) path
        else URL(URL(baseUrl.trimEnd('/') + "/"), path.trimStart('/')).toExternalForm()
}

object RetryPolicy {
    fun delayMs(attempt: Int): Long {
        val safeAttempt = attempt.coerceIn(0, 8)
        return (5_000L shl safeAttempt).coerceAtMost(300_000L)
    }
}

object PlaylistUpdatePolicy {
    fun signature(items: List<PlaylistItemModel>): String = items.joinToString("|") {
        "${it.mediaId}:${it.checksum}:${it.durationSeconds}:${it.rotation}:${it.displayMode.wireValue}"
    }

    fun shouldApply(currentSignature: String, incoming: List<PlaylistItemModel>): Boolean =
        currentSignature != signature(incoming)
}

object RealtimeEventPolicy {
    fun shouldSync(event: String): Boolean = event == "playlist.updated" || event == "reload"
}

object DiagnosticAccessPolicy {
    fun matches(candidate: String?, activationCode: String?, configuredPin: String?): Boolean {
        val entered = candidate?.trim()?.uppercase().orEmpty()
        if (entered.isBlank()) return false
        return listOfNotNull(configuredPin, activationCode)
            .map { it.trim().uppercase() }
            .filter { it.isNotBlank() }
            .any { it == entered }
    }
}

enum class PairingDecision { WAIT, START_PLAYER, INVALID_ACTIVE_STATE }

object PairingPolicy {
    fun decide(status: String, screenId: String?): PairingDecision = when {
        status != "active" -> PairingDecision.WAIT
        screenId.isNullOrBlank() -> PairingDecision.INVALID_ACTIVE_STATE
        else -> PairingDecision.START_PLAYER
    }
}

object StartupPolicy {
    private val supportedActions = setOf(
        "android.intent.action.BOOT_COMPLETED",
        "android.intent.action.QUICKBOOT_POWERON",
        "android.intent.action.REBOOT",
        "android.intent.action.MY_PACKAGE_REPLACED",
    )

    fun shouldAttemptLaunch(action: String?): Boolean = action in supportedActions
}