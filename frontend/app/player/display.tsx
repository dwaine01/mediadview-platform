import React, { useEffect, useState, useRef } from 'react';
import {
  View, Text, StyleSheet, Image, TouchableOpacity,
  AppState, useWindowDimensions,
} from 'react-native';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { VideoView, useVideoPlayer } from 'expo-video';
import { devicesAPI } from '../../src/services/api';
import { activateKeepAwakeAsync, deactivateKeepAwake } from 'expo-keep-awake';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

// ─── Media item shape from the playlist API ───────────────────────────────
interface MediaItem {
  campaign_id: string;
  media_id: string;
  filename: string;
  content_type: string;
  duration: number;
  download_url: string;
  size: number;
  checksum: string;
  display_mode?: string; // "cover" | "contain" | "stretch"  (default: cover)
}

// ─── resolveMediaFit ──────────────────────────────────────────────────────
// Single source of truth for fit mode. Priority: item.display_mode → "cover"
type ImageFit = 'cover' | 'contain' | 'stretch';
type VideoFit = 'cover' | 'contain' | 'fill';

function resolveImageFit(item?: MediaItem | null): ImageFit {
  const m = (item?.display_mode || '').toLowerCase();
  if (m === 'contain') return 'contain';
  if (m === 'stretch') return 'stretch';
  return 'cover'; // default
}

function resolveVideoFit(item?: MediaItem | null): VideoFit {
  const m = (item?.display_mode || '').toLowerCase();
  if (m === 'contain') return 'contain';
  if (m === 'stretch') return 'fill';
  return 'cover'; // default
}

// ─── Component ────────────────────────────────────────────────────────────
export default function PlayerDisplay() {
  const router = useRouter();
  const { width: W, height: H } = useWindowDimensions();

  const [playlist, setPlaylist] = useState<MediaItem[]>([]);
  const [idx, setIdx] = useState(0);
  // isReady: false until FIRST playlist fetch completes (show clean splash, no spinner)
  const [isReady, setIsReady] = useState(false);
  const [offline, setOffline] = useState(false);
  const [showOverlay, setShowOverlay] = useState(false);
  const [lastSync, setLastSync] = useState('');
  const [deviceId, setDeviceId] = useState('');
  const [screenName, setScreenName] = useState('');
  const [uptime, setUptime] = useState(0);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const uptimeRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const overlayRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startTime = useRef(Date.now());
  const retryCount = useRef(0);
  // Prevent double-advance when both timer and video-end fire
  const advancedRef = useRef(false);

  // ── Expo-video player (persistent instance, source replaced per item) ──
  const videoPlayer = useVideoPlayer(null, p => {
    p.muted = true;
    p.loop = false;
  });

  // ── Mount / unmount ───────────────────────────────────────────────────
  useEffect(() => {
    activateKeepAwakeAsync().catch(() => {});
    // init runs once on mount — intentional single-run effect
    init();
    return () => {
      deactivateKeepAwake();
      videoPlayer.pause();
      [pollRef, heartbeatRef, uptimeRef].forEach(r => {
        if (r.current) clearInterval(r.current);
      });
      if (timerRef.current) clearTimeout(timerRef.current);
      if (overlayRef.current) clearTimeout(overlayRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Reconnect when app comes back to foreground ───────────────────────
  useEffect(() => {
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active' && deviceId) fetchPlaylist(deviceId);
    });
    return () => sub.remove();
  // fetchPlaylist is stable within render cycle; deviceId is the reactive dep
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deviceId]);

  // ── Update video source whenever the current item changes ─────────────
  useEffect(() => {
    const item = playlist[idx];
    if (!item) return;
    if (item.content_type?.startsWith('video/')) {
      const uri = `${API_URL}/api${item.download_url}`;
      videoPlayer.replace({ uri });
      videoPlayer.play();
    } else {
      videoPlayer.pause();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx, playlist]);

  // ── Video end → advance early (before timer) ──────────────────────────
  useEffect(() => {
    const sub = videoPlayer.addListener('playToEnd', () => {
      if (!advancedRef.current) {
        advancedRef.current = true;
        if (timerRef.current) clearTimeout(timerRef.current);
        setIdx(prev => {
          const len = playlist.length;
          return len > 0 ? (prev + 1) % len : 0;
        });
      }
    });
    return () => sub.remove();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoPlayer]);

  // ── Timer-based item advancement ──────────────────────────────────────
  useEffect(() => {
    if (playlist.length === 0) return;
    const item = playlist[idx];
    if (!item) return;
    advancedRef.current = false;
    const dur = (item.duration || 15) * 1000;
    timerRef.current = setTimeout(() => {
      if (!advancedRef.current) {
        advancedRef.current = true;
        setIdx(prev => (prev + 1) % playlist.length);
      }
    }, dur);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [idx, playlist]);

  // ─────────────────────────────────────────────────────────────────────
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
      const newSig = items.map(i => i.media_id).join(',');
      const oldSig = playlist.map(i => i.media_id).join(',');
      if (newSig !== oldSig) {
        setPlaylist(items);
        if (items.length > 0) setIdx(0);
      }
    } catch (e: any) {
      setOffline(true);
      retryCount.current++;
      // On first load, try to restore from cache
      if (playlist.length === 0) {
        try {
          const cached = await AsyncStorage.getItem('mv_cached_playlist');
          if (cached) {
            const items = JSON.parse(cached) as MediaItem[];
            if (items.length > 0) { setPlaylist(items); setIdx(0); }
          }
        } catch {}
      }
      try {
        await devicesAPI.heartbeat(id, {
          status: 'error',
          last_error: `Playlist fetch failed: ${e.message}`,
        });
      } catch {}
    } finally {
      // Mark ready after first fetch attempt (success or fail)
      setIsReady(true);
    }
  };

  const sendHeartbeat = async (id: string) => {
    try {
      const res = await devicesAPI.heartbeat(id, {
        status: offline ? 'degraded' : 'online',
        current_media_id: playlist[idx]?.media_id ?? null,
        cached_media_count: playlist.length,
        uptime_seconds: Math.floor((Date.now() - startTime.current) / 1000),
        app_version: '1.0.0',
      });
      if (res.data.action === 'wait') router.replace('/player/activate');
    } catch {}
  };

  const toggleOverlay = () => {
    setShowOverlay(true);
    if (overlayRef.current) clearTimeout(overlayRef.current);
    overlayRef.current = setTimeout(() => setShowOverlay(false), 6000);
  };

  const formatUptime = (s: number) => `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;

  const item = playlist[idx];
  const mediaUrl = item ? `${API_URL}/api${item.download_url}` : null;
  const isVideo = item?.content_type?.startsWith('video/');
  const imageFit = resolveImageFit(item);
  const videoFit = resolveVideoFit(item);

  // ── SPLASH SCREEN ─────────────────────────────────────────────────────
  // Shown ONLY before first fetch completes, or when there's genuinely no content.
  // NO spinner. NO loading text. Clean MediaView branding.
  const showSplash = !isReady || playlist.length === 0;

  return (
    <TouchableOpacity
      style={[styles.root, { width: W, height: H }]}
      activeOpacity={1}
      onPress={toggleOverlay}
    >
      {/* ── ACTIVE CONTENT ─────────────────────────────────────────────── */}
      {!showSplash && item && (
        <>
          {isVideo ? (
            <VideoView
              player={videoPlayer}
              style={styles.fill}
              contentFit={videoFit}
              nativeControls={false}
              allowsFullscreen={false}
              allowsPictureInPicture={false}
            />
          ) : (
            <Image
              key={item.media_id}
              source={{ uri: mediaUrl! }}
              style={styles.fill}
              resizeMode={imageFit}
              fadeDuration={0}
            />
          )}
        </>
      )}

      {/* ── SPLASH (initial load or empty playlist) ────────────────────── */}
      {showSplash && (
        <View style={styles.splash}>
          <View style={styles.splashLogo}>
            <Text style={styles.splashLogoText}>MV</Text>
          </View>
          <Text style={styles.splashTitle}>MediaView</Text>
          <Text style={styles.splashSub}>{screenName || 'Digital Signage'}</Text>
          <View style={styles.splashDivider} />
          <Text style={styles.splashStatus}>
            {!isReady
              ? 'Connecting...'
              : offline
              ? 'Offline — Waiting for connection'
              : 'No campaigns scheduled'}
          </Text>
        </View>
      )}

      {/* ── HUD OVERLAY (tap to reveal, auto-dismisses in 6s) ─────────── */}
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
              {playlist.length > 0 ? `${idx + 1}/${playlist.length} · ${item?.filename} · ${item?.duration}s · ${(item?.display_mode || 'cover').toUpperCase()}` : 'No content'}
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
  // Root fills the entire screen — no safe area insets for a signage player
  root: {
    backgroundColor: '#000',
    overflow: 'hidden',
  },
  // Media fills root completely
  fill: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
  },
  // Clean splash — no loading indicators visible to the public
  splash: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#09090F',
  },
  splashLogo: {
    width: 80,
    height: 80,
    borderRadius: 20,
    backgroundColor: '#1E1B4B',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 20,
    borderWidth: 2,
    borderColor: '#312E81',
  },
  splashLogoText: { fontSize: 28, fontWeight: '900', color: '#6366F1' },
  splashTitle: { fontSize: 36, fontWeight: '800', color: '#E2E8F0' },
  splashSub: { fontSize: 16, color: '#6366F1', marginTop: 4 },
  splashDivider: { width: 80, height: 2, backgroundColor: '#1E293B', marginVertical: 24 },
  splashStatus: { fontSize: 15, color: '#64748B' },
  // HUD
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.75)',
    justifyContent: 'space-between',
  },
  overlayTop: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 28,
    paddingTop: 24,
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
    backgroundColor: '#7C2D12',
    paddingHorizontal: 10,
    paddingVertical: 3,
    borderRadius: 6,
    marginRight: 8,
  },
  offlinePillText: { fontSize: 10, fontWeight: '800', color: '#FB923C' },
  overlayBottom: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
    paddingHorizontal: 28,
    paddingBottom: 24,
  },
  overlayInfo: { fontSize: 13, color: '#94A3B8', flex: 1 },
  overlayScreen: { fontSize: 13, color: '#6366F1', fontWeight: '600' },
  overlayInfoBtn: {
    backgroundColor: '#1E293B',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
  },
  overlayInfoText: { fontSize: 13, fontWeight: '600', color: '#E2E8F0' },
});
