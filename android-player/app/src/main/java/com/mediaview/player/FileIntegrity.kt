package com.mediaview.player

import java.io.File
import java.security.MessageDigest

object FileIntegrity {
    fun matches(file: File, expectedBytes: Long, expectedSha256: String?): Boolean {
        if (!file.isFile || file.length() <= 0) return false
        if (expectedBytes > 0 && file.length() != expectedBytes) return false
        if (!expectedSha256.isNullOrBlank() && sha256(file) != expectedSha256.lowercase()) return false
        return true
    }

    fun commit(temp: File, target: File) {
        require(temp.isFile && temp.length() > 0) { "temporary download is empty" }
        val backup = File(target.parentFile, target.name + ".bak")
        backup.delete()
        val hadTarget = target.exists()
        if (hadTarget && !target.renameTo(backup)) error("cannot preserve ${target.name}")
        if (!temp.renameTo(target)) {
            if (hadTarget) backup.renameTo(target)
            error("atomic rename failed for ${target.name}")
        }
        backup.delete()
    }

    fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(64 * 1024)
            var count: Int
            while (input.read(buffer).also { count = it } > 0) digest.update(buffer, 0, count)
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}