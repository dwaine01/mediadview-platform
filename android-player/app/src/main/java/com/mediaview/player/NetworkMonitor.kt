package com.mediaview.player

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.os.Build

class NetworkMonitor(context: Context, private val onChanged: (Boolean) -> Unit) {
    private val manager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
    private val callback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) = publish()
        override fun onLost(network: Network) = publish()
        override fun onCapabilitiesChanged(network: Network, capabilities: NetworkCapabilities) = publish()
    }
    private var registered = false

    fun start() {
        if (registered) return
        val request = NetworkRequest.Builder()
            .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .build()
        manager.registerNetworkCallback(request, callback)
        registered = true
        publish()
    }

    fun stop() {
        if (!registered) return
        runCatching { manager.unregisterNetworkCallback(callback) }
        registered = false
    }

    fun isOnline(): Boolean {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val network = manager.activeNetwork ?: return false
            val capabilities = manager.getNetworkCapabilities(network) ?: return false
            return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
        }
        @Suppress("DEPRECATION")
        return manager.activeNetworkInfo?.isConnected == true
    }

    private fun publish() {
        val online = isOnline()
        PlayerDiagnostics.connectivity(online)
        onChanged(online)
    }
}