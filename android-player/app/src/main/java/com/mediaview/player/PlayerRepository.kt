package com.mediaview.player

import android.content.Context
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

data class SyncResult(val snapshot: PlaylistSnapshot, val fromCache: Boolean, val rejectedItems: Int)
class DeviceUnpairedException : IllegalStateException("device is not activated")

class PlayerRepository(private val context: Context) {
    private val dao = PlayerDatabase.get(context).playerDao()
    private val cache = ContentCache(context)

    suspend fun loadCached(): PlaylistSnapshot? = withContext(Dispatchers.IO) {
        val state = dao.state() ?: return@withContext null
        val items = dao.media().mapNotNull { entity ->
            if (entity.contentType != "widget" && (entity.localPath.isNullOrBlank() || !File(entity.localPath).isFile)) {
                null
            } else entity.toModel()
        }
        PlaylistSnapshot(
            state.screenId, state.screenName, state.resolution,
            state.playlistVersion, state.lastSyncEpochMs.toString(), items,
        )
    }

    suspend fun sync(deviceId: String): SyncResult = withContext(Dispatchers.IO) {
        val result = PlayerApi.getJsonResult(context, "/api/devices/$deviceId/playlist")
        if (result.body.optString("status") == "not_activated") throw DeviceUnpairedException()
        val snapshot = PlaylistJsonParser.parse(result.body, PlayerApi.baseUrl(context))
        val prepared = ArrayList<PlaylistItemModel>()
        var rejected = 0
        snapshot.items.forEach { item ->
            try {
                prepared += cache.materialize(item)
            } catch (error: Exception) {
                rejected++
                Log.e(PlayerApp.TAG, "Rejected media ${item.mediaId}: ${error.message}")
                PlayerDiagnostics.playerError("Cache ${item.filename}: ${error.message}")
            }
        }

        val previous = loadCached()
        if (snapshot.items.isNotEmpty() && prepared.isEmpty() && previous?.items?.isNotEmpty() == true) {
            return@withContext SyncResult(previous, true, rejected)
        }

        val syncedAt = System.currentTimeMillis()
        val playable = snapshot.copy(items = prepared)
        dao.replacePlaylist(
            prepared.map { it.toEntity(syncedAt) },
            PlayerStateEntity(
                screenId = snapshot.screenId,
                screenName = snapshot.screenName,
                resolution = snapshot.resolution,
                playlistVersion = snapshot.version,
                lastSyncEpochMs = syncedAt,
            ),
        )
        cache.cleanup(prepared.mapNotNull { it.localPath }.toSet())
        PlayerDiagnostics.synced(syncedAt)
        SyncResult(playable, false, rejected)
    }

    suspend fun invalidate(item: PlaylistItemModel) = withContext(Dispatchers.IO) {
        cache.delete(item.localPath)
        dao.deleteMedia(item.mediaId)
    }

    suspend fun clearCache() = withContext(Dispatchers.IO) {
        dao.deleteMedia()
        cache.cleanup(emptySet())
    }

    private fun CachedMediaEntity.toModel() = PlaylistItemModel(
        mediaId, campaignId, filename, contentType, durationSeconds, rotation,
        sourceUrl, checksum, expectedBytes, orderIndex, localPath,
    )

    private fun PlaylistItemModel.toEntity(now: Long) = CachedMediaEntity(
        mediaId, campaignId, filename, contentType, durationSeconds, rotation,
        sourceUrl, checksum, expectedBytes, orderIndex, localPath, now,
    )
}