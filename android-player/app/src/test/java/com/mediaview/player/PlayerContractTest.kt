package com.mediaview.player

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class PlayerContractTest {
    @get:Rule val temp = TemporaryFolder()

    @Test fun emptyPlaylistIsAValidControlledState() {
        val parsed = PlaylistJsonParser.parse(JSONObject("""{"screen_id":"s1","items":[]}"""), "https://example.com")
        assertEquals("s1", parsed.screenId)
        assertTrue(parsed.items.isEmpty())
    }

    @Test fun parsesVideoImageAndHtmlItems() {
        val items = JSONArray()
            .put(item("video/mp4", "/v.mp4"))
            .put(item("image/jpeg", "/i.jpg"))
            .put(item("widget", "/widget"))
        val parsed = PlaylistJsonParser.parse(JSONObject().put("items", items), "https://example.com")
        assertEquals(listOf(MediaKind.VIDEO, MediaKind.IMAGE, MediaKind.HTML), parsed.items.map { it.kind })
        assertEquals("https://example.com/v.mp4", parsed.items.first().sourceUrl)
    }

    @Test fun invalidItemsAreRejectedWithoutBreakingPlaylist() {
        val items = JSONArray().put(JSONObject().put("media_id", "missing-url")).put(item("image/png", "/ok.png"))
        val parsed = PlaylistJsonParser.parse(JSONObject().put("items", items), "https://example.com")
        assertEquals(1, parsed.items.size)
    }

    @Test fun networkRetryIsBoundedAndResets() {
        assertEquals(5_000L, RetryPolicy.delayMs(0))
        assertEquals(300_000L, RetryPolicy.delayMs(20))
        assertTrue(RetryPolicy.delayMs(2) > RetryPolicy.delayMs(1))
    }

    @Test fun playlistChangeIsDetected() {
        val original = listOf(model("a", 15))
        val changed = listOf(model("a", 30))
        assertNotEquals(PlaylistUpdatePolicy.signature(original), PlaylistUpdatePolicy.signature(changed))
        assertFalse(PlaylistUpdatePolicy.shouldApply(PlaylistUpdatePolicy.signature(original), original))
        assertTrue(PlaylistUpdatePolicy.shouldApply(PlaylistUpdatePolicy.signature(original), changed))
    }

    @Test fun nativePairingOnlyStartsWithAnAssignedScreen() {
        assertEquals(PairingDecision.WAIT, PairingPolicy.decide("pending", null))
        assertEquals(PairingDecision.INVALID_ACTIVE_STATE, PairingPolicy.decide("active", ""))
        assertEquals(PairingDecision.START_PLAYER, PairingPolicy.decide("active", "screen-123"))
    }

    @Test fun atomicCacheRejectsCorruptAndCommitsValidFile() {
        val target = temp.newFile("asset.mp4").apply { writeText("old") }
        val partial = temp.newFile("asset.mp4.tmp").apply { writeText("new-complete") }
        assertFalse(FileIntegrity.matches(partial, 999, null))
        val sha = FileIntegrity.sha256(partial)
        assertTrue(FileIntegrity.matches(partial, partial.length(), sha))
        FileIntegrity.commit(partial, target)
        assertEquals("new-complete", target.readText())
        assertFalse(partial.exists())
    }

    @Test fun bootAndPackageReplacementTriggerRecovery() {
        assertTrue(StartupPolicy.shouldAttemptLaunch("android.intent.action.BOOT_COMPLETED"))
        assertTrue(StartupPolicy.shouldAttemptLaunch("android.intent.action.MY_PACKAGE_REPLACED"))
        assertFalse(StartupPolicy.shouldAttemptLaunch("android.intent.action.SCREEN_OFF"))
    }

    private fun item(type: String, url: String) = JSONObject()
        .put("media_id", "m-$type")
        .put("campaign_id", "c1")
        .put("filename", url.substringAfterLast('/'))
        .put("content_type", type)
        .put("download_url", url)
        .put("duration", 15)

    private fun model(id: String, duration: Int) = PlaylistItemModel(
        id, "c", "$id.mp4", "video/mp4", duration, 0,
        "https://example.com/$id.mp4", null, 0, 0,
    )
}