package com.mediaview.player

import android.annotation.SuppressLint
import android.app.Activity
import android.graphics.Color
import android.net.Uri
import android.os.Build
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
import androidx.media3.ui.PlayerView
import coil.load
import java.io.File

interface PlaybackEvents {
    fun onPreparing(item: PlaylistItemModel)
    fun onReady(item: PlaylistItemModel)
    fun onError(item: PlaylistItemModel, message: String)
}

class PlaybackController(
    private val activity: Activity,
    private val host: FrameLayout,
    private val events: PlaybackEvents,
) {
    private val handler = android.os.Handler(android.os.Looper.getMainLooper())
    private var items: List<PlaylistItemModel> = emptyList()
    private var index = -1
    private var signature = ""
    private var exoPlayer: ExoPlayer? = null
    private var webView: WebView? = null
    private var advanceRunnable: Runnable? = null
    private var failureRunnable: Runnable? = null
    private var prepareTimeoutRunnable: Runnable? = null
    private val quarantine = mutableMapOf<String, Pair<String?, Long>>()
    private var lastPosition = -1L
    private var lastProgressAt = System.currentTimeMillis()

    val currentItem: PlaylistItemModel?
        get() = items.getOrNull(index)

    fun setPlaylist(newItems: List<PlaylistItemModel>) {
        val now = System.currentTimeMillis()
        quarantine.entries.removeAll { it.value.second <= now }
        val accepted = newItems.filter { item ->
            val blocked = quarantine[item.mediaId]
            blocked == null || blocked.first != item.checksum || blocked.second <= now
        }
        val newSignature = PlaylistUpdatePolicy.signature(accepted)
        if (!PlaylistUpdatePolicy.shouldApply(signature, accepted) && currentItem != null) return
        val currentId = currentItem?.mediaId
        items = accepted
        signature = newSignature
        index = currentId?.let { id -> accepted.indexOfFirst { it.mediaId == id } } ?: -1
        if (index < 0) index = 0
        if (items.isEmpty()) {
            clearSurface()
        } else {
            playCurrent()
        }
    }

    fun pause() {
        exoPlayer?.pause()
        webView?.onPause()
    }

    fun resume() {
        exoPlayer?.play()
        webView?.onResume()
    }

    fun release() {
        clearSurface()
        items = emptyList()
    }

    fun watchdogTick() {
        val player = exoPlayer ?: return
        if (!player.isPlaying) return
        val position = player.currentPosition
        if (position > lastPosition + 250) {
            lastPosition = position
            lastProgressAt = System.currentTimeMillis()
            return
        }
        if (System.currentTimeMillis() - lastProgressAt > 30_000) {
            failCurrent("video stalled for 30 seconds")
        }
    }

    private fun playCurrent() {
        val item = currentItem ?: return
        clearSurface()
        events.onPreparing(item)
        prepareTimeoutRunnable = Runnable { failCurrent("renderer did not become ready in 30 seconds") }.also {
            handler.postDelayed(it, 30_000)
        }
        when (item.kind) {
            MediaKind.IMAGE -> showImage(item)
            MediaKind.VIDEO -> showVideo(item)
            MediaKind.HTML -> showHtml(item)
        }
    }

    private fun showImage(item: PlaylistItemModel) {
        val image = ImageView(activity).apply {
            setBackgroundColor(Color.BLACK)
            scaleType = ImageView.ScaleType.FIT_CENTER
            rotation = item.rotation.toFloat()
            alpha = 0f
        }
        host.addView(image, fillParams())
        val source: Any = item.localPath?.let(::File) ?: item.sourceUrl
        image.load(source) {
            listener(
                onSuccess = { _, _ ->
                    image.animate().alpha(1f).setDuration(300).start()
                    markReady(item)
                },
                onError = { _, result -> failCurrent("image decode: ${result.throwable.message}") },
            )
        }
    }

    private fun showVideo(item: PlaylistItemModel) {
        val player = ExoPlayer.Builder(activity).build()
        exoPlayer = player
        val view = PlayerView(activity).apply {
            useController = false
            setShutterBackgroundColor(Color.BLACK)
            this.player = player
            rotation = item.rotation.toFloat()
        }
        host.addView(view, fillParams())
        player.addListener(object : Player.Listener {
            override fun onRenderedFirstFrame() {
                lastPosition = player.currentPosition
                lastProgressAt = System.currentTimeMillis()
                markReady(item)
            }

            override fun onPlaybackStateChanged(playbackState: Int) {
                if (playbackState == Player.STATE_ENDED) next()
            }

            override fun onPlayerError(error: PlaybackException) {
                failCurrent("video ${error.errorCodeName}: ${error.message}")
            }
        })
        val uri = item.localPath?.let { Uri.fromFile(File(it)) } ?: Uri.parse(item.sourceUrl)
        player.setMediaItem(MediaItem.fromUri(uri))
        player.repeatMode = Player.REPEAT_MODE_OFF
        player.prepare()
        player.playWhenReady = true
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun showHtml(item: PlaylistItemModel) {
        val page = WebView(activity)
        webView = page
        page.setBackgroundColor(Color.BLACK)
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
                markReady(item)
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {
                    markReady(item)
                }
            }

            override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: WebResourceError?) {
                if (request?.isForMainFrame == true) failCurrent("WebView ${error?.errorCode}: ${error?.description}")
            }

            @Suppress("DEPRECATION")
            override fun onReceivedError(view: WebView?, errorCode: Int, description: String?, failingUrl: String?) {
                if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) failCurrent("WebView $errorCode: $description")
            }

            override fun onReceivedHttpError(view: WebView?, request: WebResourceRequest?, response: WebResourceResponse?) {
                if (request?.isForMainFrame == true) {
                    PlayerDiagnostics.http(request.url.toString(), response?.statusCode ?: 0)
                    failCurrent("WebView HTTP ${response?.statusCode}")
                }
            }

            override fun onReceivedSslError(view: WebView?, handler: SslErrorHandler?, error: android.net.http.SslError?) {
                handler?.cancel()
                failCurrent("SSL ${error?.primaryError} at ${error?.url}")
            }

            override fun onRenderProcessGone(view: WebView?, detail: RenderProcessGoneDetail?): Boolean {
                webView = null
                view?.let { host.removeView(it); it.destroy() }
                failCurrent("WebView renderer terminated; crashed=${detail?.didCrash()}")
                return true
            }
        }
        host.addView(page, fillParams())
        val url = item.localPath?.let { Uri.fromFile(File(it)).toString() } ?: item.sourceUrl
        PlayerDiagnostics.http(url, 0)
        page.loadUrl(url)
    }

    private fun failCurrent(message: String) {
        if (failureRunnable != null) return
        val failed = currentItem ?: return
        quarantine[failed.mediaId] = failed.checksum to (System.currentTimeMillis() + 5 * 60_000L)
        PlayerDiagnostics.playerError(message)
        PlayerDiagnostics.webError(if (failed.kind == MediaKind.HTML) message else null)
        events.onError(failed, message)
        failureRunnable = Runnable {
            failureRunnable = null
            items = items.filterNot { it.mediaId == failed.mediaId }
            signature = PlaylistUpdatePolicy.signature(items)
            if (items.isEmpty()) {
                index = -1
                clearSurface()
            } else {
                if (index >= items.size) index = 0
                playCurrent()
            }
        }.also { handler.postDelayed(it, 2_000) }
    }

    private fun markReady(item: PlaylistItemModel) {
        if (failureRunnable != null || currentItem?.mediaId != item.mediaId) return
        prepareTimeoutRunnable?.let(handler::removeCallbacks)
        prepareTimeoutRunnable = null
        events.onReady(item)
        scheduleAdvance(item.durationSeconds)
    }

    private fun next() {
        if (items.isEmpty()) return
        index = (index + 1) % items.size
        playCurrent()
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
        prepareTimeoutRunnable?.let(handler::removeCallbacks)
        prepareTimeoutRunnable = null
        exoPlayer?.release()
        exoPlayer = null
        webView?.let { view -> host.removeView(view); view.stopLoading(); view.destroy() }
        webView = null
        host.removeAllViews()
    }

    private fun fillParams() = FrameLayout.LayoutParams(
        FrameLayout.LayoutParams.MATCH_PARENT,
        FrameLayout.LayoutParams.MATCH_PARENT,
    )
}