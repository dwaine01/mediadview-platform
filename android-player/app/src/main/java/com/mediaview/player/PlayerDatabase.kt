package com.mediaview.player

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.Transaction

@Entity(tableName = "cached_media")
data class CachedMediaEntity(
    @PrimaryKey val mediaId: String,
    val campaignId: String,
    val filename: String,
    val contentType: String,
    val durationSeconds: Int,
    val rotation: Int,
    val sourceUrl: String,
    val checksum: String?,
    val expectedBytes: Long,
    val orderIndex: Int,
    val localPath: String?,
    val cachedAt: Long,
)

@Entity(tableName = "player_state")
data class PlayerStateEntity(
    @PrimaryKey val key: String = "active",
    val screenId: String,
    val screenName: String,
    val resolution: String,
    val playlistVersion: Long,
    val lastSyncEpochMs: Long,
)

@Dao
abstract class PlayerDao {
    @Query("SELECT * FROM cached_media ORDER BY orderIndex")
    abstract suspend fun media(): List<CachedMediaEntity>

    @Query("SELECT * FROM player_state WHERE `key` = 'active' LIMIT 1")
    abstract suspend fun state(): PlayerStateEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun insertMedia(items: List<CachedMediaEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun insertState(state: PlayerStateEntity)

    @Query("DELETE FROM cached_media")
    abstract suspend fun deleteMedia()

    @Query("DELETE FROM cached_media WHERE mediaId = :mediaId")
    abstract suspend fun deleteMedia(mediaId: String)

    @Transaction
    open suspend fun replacePlaylist(items: List<CachedMediaEntity>, state: PlayerStateEntity) {
        deleteMedia()
        if (items.isNotEmpty()) insertMedia(items)
        insertState(state)
    }
}

@Database(entities = [CachedMediaEntity::class, PlayerStateEntity::class], version = 1, exportSchema = false)
abstract class PlayerDatabase : RoomDatabase() {
    abstract fun playerDao(): PlayerDao

    companion object {
        @Volatile private var instance: PlayerDatabase? = null

        fun get(context: Context): PlayerDatabase = instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(
                context.applicationContext,
                PlayerDatabase::class.java,
                "mediaview-player.db",
            ).fallbackToDestructiveMigration().build().also { instance = it }
        }
    }
}