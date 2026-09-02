package com.mediaview.player

import android.annotation.SuppressLint
import android.app.Activity
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.view.View
import android.webkit.RenderProcessGoneDetail
import android.webkit.SslErrorHandler
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.ImageView
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView
import coil.load
import java.io.File

interface PlaybackEvents {
    fun onPreparing(item: PlaylistItemModel)
    fun onReady(item: PlaylistItemModel)
    fun onError(item: PlaylistItemModel, message: String)
}

/** Keeps the active surface visible until the next surface is fully rendered. */
class PlaybackController(
    private val activity: Activity,
    private val host: FrameLayout,
    private val events: PlaybackEvents,
) {
    private data class RenderSession(
        val item: PlaylistItemModel,
        val view: View,
        val player: ExoPlayer? = null,
        val page: WebView? = null,
    )

    private val handler = android.os.Handler(android.os.Looper.getMainLooper())
    private var items: List<PlaylistItemModel> = emptyList()
    private var index = -1
    private var signature = ""
    private var activeSession: RenderSession? = null
    private var pendingSession: RenderSession? = null
    private var advanceRunnable: Runnable? = null
    private var failureRunnable: Runnable? = null
    private var prepareTimeoutRunnable: Runnable? = null
    private val quarantine = mutableMapOf<String, Pair<String?, Long>>()
    private var lastPosition = -1L
    private var lastProgressAt = System.currentTimeMillis()

    val currentItem: PlaylistItemModel?
        get() = activeSession?.item ?: items.getOrNull(index)

    fun setPlaylist(newItems: List<PlaylistItemModel>) {
        val now = System.currentTimeMillis()
        quarantine.entries.removeAll { it.value.second <= now }
        val accepted = newItems.filter { item ->
            val blocked = quarantine[item.mediaId]
            blocked == null || blocked.first != item.checksum || blocked.second <= now
        }
        if (!PlaylistUpdatePolicy.shouldApply(signature, accepted) && activeSession != null) return

        val playing = activeSession?.item
        items = accepted
        signature = PlaylistUpdatePolicy.signature(accepted)
        if (items.isEmpty()) {
            index = -1
            clearSurface()
            return
        }

        val preserved = playing?.let { active -> items.indexOfFirst { it.mediaId == active.mediaId } } ?: -1
        if (preserved >= 0) {
            index = preserved
            val incoming = items[preserved]
            if (playing != null && visualMatches(playing, incoming)) {
                scheduleAdvance(incoming.durationSeconds)
                return
            }
        } else {
            index = 0
        }
        prepareCurrent()
    }

    fun pause() {
        activeSession?.player?.pause()
        pendingSession?.player?.pause()
        activeSession?.page?.onPause()
        pendingSession?.page?.onPause()
    }

    fun resume() {
        activeSession?.player?.play()
        pendingSession?.player?.play()
        activeSession?.page?.onResume()
        pendingSession?.page?.onResume()
    }

    fun release() {
        clearSurface()
        items = emptyList()
    }

    fun watchdogTick() {
        val player = activeSession?.player ?: return
        if (!player.isPlaying) return
        val position = player.currentPosition
        if (position > lastPosition + 250) {
            lastPosition = position
            lastProgressAt = System.currentTimeMillis()
            return
        }
        if (System.currentTimeMillis() - lastProgressAt > 30_000) {
            failCurrent("video stalled for 30 seconds", activeSession)
        }
    }

    private fun prepareCurrent() {
        val item = items.getOrNull(index) ?: return
        pendingSession?.let(::disposeSession)
        pendingSession = null
        cancelPrepareTimeout()
        advanceRunnable?.let(handler::removeCallbacks)
        advanceRunnable = null
        events.onPreparing(item)
        prepareTimeoutRunnable = Runnable {
            failCurrent("renderer did not become ready in 30 seconds", pendingSession)
        }.also { handler.postDelayed(it, 30_000) }
        when (item.kind) {
            MediaKind.IMAGE -> prepareImage(item)
            MediaKind.VIDEO -> prepareVideo(item)
            MediaKind.HTML -> prepareHtml(item)
        }
    }

    private fun prepareImage(item: PlaylistItemModel) {
        val image = ImageView(activity).apply {
            setBackgroundColor(Color.BLACK)
            scaleType = imageScaleType(item.displayMode)
            rotation = item.rotation.toFloat()
            alpha = 0f
        }
        val session = RenderSession(item, image)
        pendingSession = session
        host.addView(image, fillParams())
        val source: Any = item.localPath?.let(::File) ?: item.sourceUrl
        image.load(source) {
            listener(
                onSuccess = { _, _ -> activatePending(item) },
                onError = { _, result -> failCurrent("image decode: ${result.throwable.message}", session) },
            )
        }
    }

    private fun prepareVideo(item: PlaylistItemModel) {
        val player = ExoPlayer.Builder(activity).build()
        val view = PlayerView(activity).apply {
            useController = false
            setShutterBackgroundColor(Color.TRANSPARENT)
            resizeMode = videoResizeMode(item.displayMode)
            this.player = player
            rotation = item.rotation.toFloat()
            alpha = 0f
        }
        val session = RenderSession(item, view, player = player)
        pendingSession = session
        host.addView(view, fillParams())
        player.addListener(object : Player.Listener {
            override fun onRenderedFirstFrame() {
                lastPosition = player.currentPosition
                lastProgressAt = System.currentTimeMillis()
                activatePending(item)
            }

            override fun onPlaybackStateChanged(playbackState: Int) {
                if (playbackState == Player.STATE_ENDED &&
                    activeSession?.player === player && pendingSession == null
                ) next()
            }

            override fun onPlayerError(error: PlaybackException) {
                failCurrent("video ${error.errorCodeName}: ${error.message}", session)
            }
        })
        val uri = item.localPath?.let { Uri.fromFile(File(it)) } ?: Uri.parse(item.sourceUrl)
        player.setMediaItem(MediaItem.fromUri(uri))
        player.repeatMode = Player.REPEAT_MODE_OFF
        player.prepare()
        player.playWhenReady = true
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun prepareHtml(item: PlaylistItemModel) {
        val page = WebView(activity).apply {
            setBackgroundColor(Color.BLACK)
            alpha = 0f
        }
        val session = RenderSession(item, page, page = page)
        pendingSession = session
        page.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = false
            mediaPlaybackRequiresUserGesture = false
            allowContentAccess = false
            allowFileAccess = item.localPath != null
            @Suppress("DEPRECATION")
            allowFileAccessFromFileURLs = false
            @Suppress("DEPRECATION")
            allowUniversalAccessFromFileURLs = false
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            cacheMode = WebSettings.LOAD_DEFAULT
            userAgentString = "$userAgentString MediAdView/${BuildConfig.VERSION_NAME}"
        }
        page.webViewClient = object : WebViewClient() {
            override fun onPageCommitVisible(view: WebView?, url: String?) {
                PlayerDiagnostics.http(url ?: item.sourceUrl, 200)
                activatePending(item)
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) activatePending(item)
            }

            override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: WebResourceError?) {
                if (request?.isForMainFrame == true) {
                    failCurrent("WebView ${error?.errorCode}: ${error?.description}", session)
                }
            }

            @Suppress("DEPRECATION")
            override fun onReceivedError(view: WebView?, errorCode: Int, description: String?, failingUrl: String?) {
                if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {
                    failCurrent("WebView $errorCode: $description", session)
                }
            }

            override fun onReceivedHttpError(view: WebView?, request: WebResourceRequest?, response: WebResourceResponse?) {
                if (request?.isForMainFrame == true) {
                    PlayerDiagnostics.http(request.url.toString(), response?.statusCode ?: 0)
                    failCurrent("WebView HTTP ${response?.statusCode}", session)
                }
            }

            override fun onReceivedSslError(view: WebView?, handler: SslErrorHandler?, error: android.net.http.SslError?) {
                handler?.cancel()
                failCurrent("SSL ${error?.primaryError} at ${error?.url}", session)
            }

            override fun onRenderProcessGone(view: WebView?, detail: RenderProcessGoneDetail?): Boolean {
                failCurrent("WebView renderer terminated; crashed=${detail?.didCrash()}", session)
                return true
            }
        }
        host.addView(page, fillParams())
        val url = item.localPath?.let { Uri.fromFile(File(it)).toString() } ?: item.sourceUrl
        PlayerDiagnostics.http(url, 0)
        page.loadUrl(url)
    }

    private fun activatePending(item: PlaylistItemModel) {
        val incoming = pendingSession ?: return
        if (incoming.item.mediaId != item.mediaId || items.getOrNull(index)?.mediaId != item.mediaId) return
        cancelPrepareTimeout()
        pendingSession = null
        val previous = activeSession
        activeSession = incoming
        incoming.view.bringToFront()
        lastPosition = -1L
        lastProgressAt = System.currentTimeMillis()

        if (previous == null) {
            incoming.view.alpha = 1f
            events.onReady(item)
            scheduleAdvance(item.durationSeconds)
            return
        }

        previous.view.animate().alpha(0f).setDuration(220).start()
        incoming.view.animate().alpha(1f).setDuration(220).withEndAction {
            disposeSession(previous)
            events.onReady(item)
            scheduleAdvance(item.durationSeconds)
        }.start()
    }

    private fun failCurrent(message: String, session: RenderSession?) {
        if (failureRunnable != null || session == null) return
        if (session !== pendingSession && session !== activeSession) return
        val failed = session.item
        quarantine[failed.mediaId] = failed.checksum to (System.currentTimeMillis() + 5 * 60_000L)
        PlayerDiagnostics.playerError(message)
        PlayerDiagnostics.webError(if (failed.kind == MediaKind.HTML) message else null)
        if (pendingSession === session) {
            pendingSession = null
            disposeSession(session)
        }
        cancelPrepareTimeout()
        events.onError(failed, message)
        if (session === activeSession && pendingSession != null) return
        failureRunnable = Runnable {
            failureRunnable = null
            items = items.filterNot { it.mediaId == failed.mediaId }
            signature = PlaylistUpdatePolicy.signature(items)
            if (items.isEmpty()) {
                index = -1
                return@Runnable
            }
            val activeIndex = activeSession?.item?.let { active ->
                items.indexOfFirst { it.mediaId == active.mediaId }
            } ?: -1
            index = if (activeIndex >= 0) (activeIndex + 1) % items.size else 0
            prepareCurrent()
        }.also { handler.postDelayed(it, 250) }
    }

    private fun next() {
        if (items.isEmpty() || pendingSession != null) return
        if (items.size == 1) {
            activeSession?.player?.let { player -> player.seekTo(0); player.play() }
            scheduleAdvance(items.first().durationSeconds)
            return
        }
        val activeIndex = activeSession?.item?.let { active ->
            items.indexOfFirst { it.mediaId == active.mediaId }
        } ?: index
        index = (activeIndex + 1) % items.size
        prepareCurrent()
    }

    private fun scheduleAdvance(seconds: Int) {
        advanceRunnable?.let(handler::removeCallbacks)
        advanceRunnable = Runnable { next() }.also {
            handler.postDelayed(it, seconds.coerceAtLeast(1) * 1_000L)
        }
    }

    private fun clearSurface() {
        advanceRunnable?.let(handler::removeCallbacks)
        advanceRunnable = null
        failureRunnable?.let(handler::removeCallbacks)
        failureRunnable = null
        cancelPrepareTimeout()
        pendingSession?.let(::disposeSession)
        activeSession?.let(::disposeSession)
        pendingSession = null
        activeSession = null
        host.removeAllViews()
    }

    private fun disposeSession(session: RenderSession) {
        session.view.animate().cancel()
        session.player?.release()
        session.page?.let { page -> page.stopLoading(); page.destroy() }
        host.removeView(session.view)
    }

    private fun cancelPrepareTimeout() {
        prepareTimeoutRunnable?.let(handler::removeCallbacks)
        prepareTimeoutRunnable = null
    }

    private fun visualMatches(current: PlaylistItemModel, incoming: PlaylistItemModel): Boolean =
        current.mediaId == incoming.mediaId &&
            current.checksum == incoming.checksum &&
            current.sourceUrl == incoming.sourceUrl &&
            current.rotation == incoming.rotation &&
            current.displayMode == incoming.displayMode

    private fun imageScaleType(mode: DisplayMode): ImageView.ScaleType = when (mode) {
        DisplayMode.COVER -> ImageView.ScaleType.CENTER_CROP
        DisplayMode.CONTAIN -> ImageView.ScaleType.FIT_CENTER
        DisplayMode.STRETCH -> ImageView.ScaleType.FIT_XY
    }

    private fun videoResizeMode(mode: DisplayMode): Int = when (mode) {
        DisplayMode.COVER -> AspectRatioFrameLayout.RESIZE_MODE_ZOOM
        DisplayMode.CONTAIN -> AspectRatioFrameLayout.RESIZE_MODE_FIT
        DisplayMode.STRETCH -> AspectRatioFrameLayout.RESIZE_MODE_FILL
    }

    private fun fillParams() = FrameLayout.LayoutParams(
        FrameLayout.LayoutParams.MATCH_PARENT,
        FrameLayout.LayoutParams.MATCH_PARENT,
    )
}