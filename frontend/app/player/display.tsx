import React, { useEffect, useState, useRef } from 'react';
import {
  View, Text, StyleSheet, Image, Dimensions, TouchableOpacity,
  ActivityIndicator, AppState,
} from 'react-native';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { devicesAPI } from '../../src/services/api';
import { activateKeepAwakeAsync, deactivateKeepAwake } from 'expo-keep-awake';

const { width: SW, height: SH } = Dimensions.get('window');
const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface MediaItem {
  campaign_id: string;
  media_id: string;
  filename: string;
  content_type: string;
  duration: number;
  download_url: string;
  size: number;
  checksum: string;
}

export default function PlayerDisplay() {
  const router = useRouter();
  const [playlist, setPlaylist] = useState<MediaItem[]>([]);
  const [idx, setIdx] = useState(0);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [showOverlay, setShowOverlay] = useState(false);
  const [lastSync, setLastSync] = useState('');
  const [deviceId, setDeviceId] = useState('');
  const [screenName, setScreenName] = useState('');
  const [uptime, setUptime] = useState(0);

  const timerRef = useRef<any>(null);
  const pollRef = useRef<any>(null);
  const heartbeatRef = useRef<any>(null);
  const uptimeRef = useRef<any>(null);
  const overlayRef = useRef<any>(null);
  const startTime = useRef(Date.now());
  const retryCount = useRef(0);

  useEffect(() => {
    activateKeepAwakeAsync().catch(() => {});
    // init runs once on mount — intentional single-run effect
    init();
    return () => {
      deactivateKeepAwake();
      [timerRef, pollRef, heartbeatRef, uptimeRef].forEach(r => {
        if (r.current) clearInterval(r.current);
      });
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Track app state for reconnection
  useEffect(() => {
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active' && deviceId) {
        fetchPlaylist(deviceId);
      }
    });
    return () => sub.remove();
  // fetchPlaylist is defined in scope; deviceId is the reactive dep we care about
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deviceId]);

  const init = async () => {
    const id = await AsyncStorage.getItem('mv_device_id');
    if (!id) { router.replace('/player'); return; }
    setDeviceId(id);
    await fetchPlaylist(id);

    pollRef.current = setInterval(() => fetchPlaylist(id), 60000);
    heartbeatRef.current = setInterval(() => sendHeartbeat(id), 30000);
    uptimeRef.current = setInterval(() => {
      setUptime(Math.floor((Date.now() - startTime.current) / 1000));
    }, 1000);
  };

  const fetchPlaylist = async (id: string) => {
    try {
      const res = await devicesAPI.playlist(id);
      const items: MediaItem[] = res.data.items || [];
      setOffline(false);
      setLastSync(new Date().toLocaleTimeString());
      setScreenName(res.data.screen_name || '');
      retryCount.current = 0;

      await AsyncStorage.setItem('mv_cached_playlist', JSON.stringify(items));

      const newIds = items.map(i => i.media_id).join(',');
      const oldIds = playlist.map(i => i.media_id).join(',');
      if (newIds !== oldIds) {
        setPlaylist(items);
        if (items.length > 0) setIdx(0);
      }
      setLoading(false);
    } catch (e: any) {
      setOffline(true);
      retryCount.current++;

      // Load from cache
      if (playlist.length === 0) {
        try {
          const cached = await AsyncStorage.getItem('mv_cached_playlist');
          if (cached) {
            const items = JSON.parse(cached);
            if (items.length > 0) {
              setPlaylist(items);
              setIdx(0);
            }
          }
        } catch {}
      }
      setLoading(false);

      // Send error log
      try {
        await devicesAPI.heartbeat(id, { status: 'error', last_error: `Playlist fetch failed: ${e.message}` });
      } catch {}
    }
  };

  const sendHeartbeat = async (id: string) => {
    try {
      const res = await devicesAPI.heartbeat(id, {
        status: offline ? 'degraded' : 'online',
        current_media_id: playlist[idx]?.media_id || null,
        cached_media_count: playlist.length,
        uptime_seconds: Math.floor((Date.now() - startTime.current) / 1000),
        app_version: '1.0.0',
      });
      // Check if server wants us to do something
      if (res.data.action === 'wait') {
        // Device was unlinked - go back to activation
        router.replace('/player/activate');
      }
    } catch {}
  };

  // Auto-advance
  useEffect(() => {
    if (playlist.length === 0) return;
    const item = playlist[idx];
    if (!item) return;
    const dur = (item.duration || 15) * 1000;
    timerRef.current = setTimeout(() => {
      setIdx(prev => (prev + 1) % playlist.length);
    }, dur);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [idx, playlist]);

  const toggleOverlay = () => {
    setShowOverlay(true);
    if (overlayRef.current) clearTimeout(overlayRef.current);
    overlayRef.current = setTimeout(() => setShowOverlay(false), 6000);
  };

  const formatUptime = (s: number) => {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return `${h}h ${m}m`;
  };

  const item = playlist[idx];
  const mediaUrl = item ? `${API_URL}/api${item.download_url}` : null;

  // Loading state
  if (loading) {
    return (
      <View style={styles.container}>
        <View style={styles.loadingBox}>
          <ActivityIndicator size="large" color="#6366F1" />
          <Text style={styles.loadingText}>Loading content...</Text>
        </View>
      </View>
    );
  }

  // No content - fallback screen
  if (playlist.length === 0) {
    return (
      <TouchableOpacity style={styles.container} activeOpacity={1} onPress={toggleOverlay}>
        <View style={styles.fallback}>
          <View style={styles.fallbackLogo}>
            <Text style={styles.fallbackLogoText}>MV</Text>
          </View>
          <Text style={styles.fallbackTitle}>MediaView</Text>
          <Text style={styles.fallbackSub}>{screenName || 'Digital Signage'}</Text>
          <View style={styles.fallbackDivider} />
          <Text style={styles.fallbackStatus}>
            {offline ? 'Offline - Waiting for connection...' : 'No campaigns scheduled'}
          </Text>
          {offline && <Text style={styles.fallbackRetry}>Auto-retry every 60s</Text>}
        </View>
        {showOverlay && (
          <View style={styles.overlayBar}>
            <TouchableOpacity onPress={() => router.push('/player/info')} style={styles.overlayInfoBtn}>
              <Text style={styles.overlayInfoText}>Device Info</Text>
            </TouchableOpacity>
          </View>
        )}
      </TouchableOpacity>
    );
  }

  // Playing content
  return (
    <TouchableOpacity style={styles.container} activeOpacity={1} onPress={toggleOverlay}>
      {item?.content_type?.startsWith('image/') ? (
        <Image
          source={{ uri: mediaUrl || '' }}
          style={styles.fullscreen}
          resizeMode="contain"
        />
      ) : (
        <View style={styles.fullscreen}>
          <Text style={styles.videoLabel}>Video: {item?.filename}</Text>
        </View>
      )}

      {/* HUD Overlay */}
      {showOverlay && (
        <View style={styles.overlay}>
          <View style={styles.overlayTop}>
            <View style={styles.overlayBrand}>
              <View style={styles.overlayMiniLogo}><Text style={styles.overlayLogoT}>MV</Text></View>
              <Text style={styles.overlayBrandName}>MediaView Player</Text>
            </View>
            <View style={{ flex: 1 }} />
            {offline && (
              <View style={styles.offlinePill}>
                <Text style={styles.offlinePillText}>OFFLINE</Text>
              </View>
            )}
            <Text style={styles.overlayMeta}>Uptime: {formatUptime(uptime)}</Text>
            <Text style={styles.overlayMeta}>Sync: {lastSync}</Text>
          </View>
          <View style={styles.overlayBottom}>
            <Text style={styles.overlayInfo}>
              {idx + 1}/{playlist.length} | {item?.filename} | {item?.duration}s
            </Text>
            <Text style={styles.overlayScreen}>{screenName}</Text>
            <TouchableOpacity onPress={() => router.push('/player/info')} style={styles.overlayInfoBtn}>
              <Text style={styles.overlayInfoText}>Device Info</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },
  loadingBox: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { color: '#64748B', fontSize: 16, marginTop: 16 },
  fullscreen: { width: SW, height: SH, justifyContent: 'center', alignItems: 'center' },
  videoLabel: { color: '#FFF', fontSize: 20 },
  // Fallback
  fallback: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#09090F' },
  fallbackLogo: {
    width: 80, height: 80, borderRadius: 20, backgroundColor: '#1E1B4B',
    justifyContent: 'center', alignItems: 'center', marginBottom: 20,
    borderWidth: 2, borderColor: '#312E81',
  },
  fallbackLogoText: { fontSize: 28, fontWeight: '900', color: '#6366F1' },
  fallbackTitle: { fontSize: 36, fontWeight: '800', color: '#E2E8F0' },
  fallbackSub: { fontSize: 16, color: '#6366F1', marginTop: 4 },
  fallbackDivider: { width: 80, height: 2, backgroundColor: '#1E293B', marginVertical: 24 },
  fallbackStatus: { fontSize: 15, color: '#64748B' },
  fallbackRetry: { fontSize: 12, color: '#475569', marginTop: 4 },
  // Overlay
  overlay: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.75)', justifyContent: 'space-between' },
  overlayTop: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingHorizontal: 28, paddingTop: 24,
  },
  overlayBrand: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  overlayMiniLogo: {
    width: 30, height: 30, borderRadius: 6, backgroundColor: '#4F46E5',
    justifyContent: 'center', alignItems: 'center',
  },
  overlayLogoT: { fontSize: 10, fontWeight: '900', color: '#FFF' },
  overlayBrandName: { fontSize: 14, fontWeight: '700', color: '#E2E8F0' },
  overlayMeta: { fontSize: 12, color: '#94A3B8', marginLeft: 16 },
  offlinePill: {
    backgroundColor: '#7C2D12', paddingHorizontal: 10, paddingVertical: 3,
    borderRadius: 6, marginRight: 8,
  },
  offlinePillText: { fontSize: 10, fontWeight: '800', color: '#FB923C' },
  overlayBottom: {
    flexDirection: 'row', alignItems: 'center', gap: 16,
    paddingHorizontal: 28, paddingBottom: 24,
  },
  overlayInfo: { fontSize: 13, color: '#94A3B8', flex: 1 },
  overlayScreen: { fontSize: 13, color: '#6366F1', fontWeight: '600' },
  overlayInfoBtn: { backgroundColor: '#1E293B', paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8 },
  overlayInfoText: { fontSize: 13, fontWeight: '600', color: '#E2E8F0' },
  overlayBar: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    backgroundColor: 'rgba(0,0,0,0.7)', padding: 16, alignItems: 'flex-end',
  },
});
