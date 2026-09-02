package com.mediaview.player

import android.content.Context
import android.util.Log
import java.io.File

class ContentCache(private val context: Context) {
    private val root = File(context.filesDir, "media-cache").also { it.mkdirs() }

    fun materialize(item: PlaylistItemModel): PlaylistItemModel {
        if (item.kind == MediaKind.HTML && item.contentType == "widget") return item
        val target = File(root, safeFileName(item))
        if (isValid(target, item)) return item.copy(localPath = target.absolutePath)

        val temp = File(root, target.name + ".tmp")
        temp.delete()
        return try {
            val result = PlayerApi.downloadFile(item.sourceUrl, temp)
            val checksumOk = item.checksum == null || item.checksum.equals(result.sha256, ignoreCase = true)
            val sizeOk = item.expectedBytes <= 0 || item.expectedBytes == result.bytes
            if (!checksumOk || !sizeOk || result.bytes <= 0) {
                throw IllegalStateException("integrity failed for ${item.mediaId}")
            }
            FileIntegrity.commit(temp, target)
            item.copy(localPath = target.absolutePath)
        } catch (error: Exception) {
            temp.delete()
            if (isValid(target, item.copy(checksum = null, expectedBytes = 0))) {
                Log.w(PlayerApp.TAG, "Using previous cached asset ${item.mediaId}: ${error.message}")
                item.copy(localPath = target.absolutePath)
            } else {
                throw error
            }
        }
    }

    fun delete(path: String?) {
        if (!path.isNullOrBlank()) runCatching { File(path).delete() }
    }

    fun cleanup(retainedPaths: Set<String>) {
        root.listFiles()?.forEach { file ->
            if (!file.name.endsWith(".tmp") && file.absolutePath !in retainedPaths) file.delete()
            if (file.name.endsWith(".tmp")) file.delete()
        }
    }

    private fun isValid(file: File, item: PlaylistItemModel): Boolean {
        return FileIntegrity.matches(file, item.expectedBytes, item.checksum)
    }

    private fun safeFileName(item: PlaylistItemModel): String {
        val ext = item.filename.substringAfterLast('.', "bin").lowercase().replace(Regex("[^a-z0-9]"), "")
        return item.mediaId.replace(Regex("[^a-zA-Z0-9_-]"), "_") + "." + ext.ifBlank { "bin" }
    }
}