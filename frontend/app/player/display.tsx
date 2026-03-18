import React, { useEffect, useState, useRef, useCallback } from 'react';
import {
  View, Text, StyleSheet, Image, Dimensions, AppState,
  TouchableOpacity, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { devicesAPI } from '../../src/services/api';

const { width: SW, height: SH } = Dimensions.get('window');
const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface PlaylistItem {
  campaign_id: string;
  media_id: string;
  filename: string;
  content_type: string;
  duration: number;
  download_url: string;
  size: number;
}

export default function PlayerDisplayScreen() {
  const router = useRouter();
  const [playlist, setPlaylist] = useState<PlaylistItem[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showOverlay, setShowOverlay] = useState(false);
  const [lastSync, setLastSync] = useState<string>('');
  const [deviceId, setDeviceId] = useState('');

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const overlayTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    init();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (pollRef.current) clearInterval(pollRef.current);
      if (heartbeatRef.current) clearInterval(heartbeatRef.current);
    };
  }, []);

  const init = async () => {
    const id = await AsyncStorage.getItem('player_device_id');
    if (!id) { router.replace('/player'); return; }
    setDeviceId(id);
    await fetchPlaylist(id);

    // Poll for playlist updates every 60s
    pollRef.current = setInterval(() => fetchPlaylist(id), 60000);
    // Send heartbeat every 30s
    heartbeatRef.current = setInterval(() => sendHeartbeat(id), 30000);
  };

  const fetchPlaylist = async (id: string) => {
    try {
      const res = await devicesAPI.playlist(id);
      const items = res.data.items || [];
      setOffline(false);
      setLastSync(new Date().toLocaleTimeString());

      // Cache playlist
      await AsyncStorage.setItem('player_cached_playlist', JSON.stringify(items));

      if (JSON.stringify(items.map((i: any) => i.media_id)) !== JSON.stringify(playlist.map(i => i.media_id))) {
        setPlaylist(items);
        setCurrentIndex(0);
      }
      setLoading(false);
    } catch (e) {
      setOffline(true);
      // Try cached playlist
      try {
        const cached = await AsyncStorage.getItem('player_cached_playlist');
        if (cached) {
          const items = JSON.parse(cached);
          if (items.length > 0 && playlist.length === 0) {
            setPlaylist(items);
            setCurrentIndex(0);
          }
        }
      } catch (ce) {}
      setLoading(false);
    }
  };

  const sendHeartbeat = async (id: string) => {
    try {
      await devicesAPI.heartbeat(id, {
        status: 'online',
        current_media_id: playlist[currentIndex]?.media_id || null,
        cached_media_count: playlist.length,
      });
    } catch (e) {}
  };

  // Auto-advance to next item
  useEffect(() => {
    if (playlist.length === 0) return;
    const item = playlist[currentIndex];
    if (!item) return;

    const duration = (item.duration || 15) * 1000;
    timerRef.current = setTimeout(() => {
      setCurrentIndex(prev => (prev + 1) % playlist.length);
    }, duration);

    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [currentIndex, playlist]);

  const handlePress = () => {
    setShowOverlay(true);
    if (overlayTimerRef.current) clearTimeout(overlayTimerRef.current);
    overlayTimerRef.current = setTimeout(() => setShowOverlay(false), 5000);
  };

  const currentItem = playlist[currentIndex];
  const mediaUrl = currentItem ? `${API_URL}/api${currentItem.download_url}` : null;

  if (loading) {
    return (
      <View style={styles.container}>
        <ActivityIndicator size="large" color="#4F46E5" />
        <Text style={styles.loadingText}>Loading content...</Text>
      </View>
    );
  }

  if (playlist.length === 0) {
    return (
      <View style={styles.container}>
        <View style={styles.noContent}>
          <View style={styles.noContentIcon}>
            <Text style={styles.noContentIconText}>TV</Text>
          </View>
          <Text style={styles.noContentTitle}>MediaView Player</Text>
          <Text style={styles.noContentSub}>No content scheduled</Text>
          <Text style={styles.noContentInfo}>Waiting for campaigns to be assigned...</Text>
          {offline && <Text style={styles.offlineBadge}>OFFLINE</Text>}
        </View>
        <TouchableOpacity style={styles.infoBtn} onPress={() => router.push('/player/info')}>
          <Text style={styles.infoBtnText}>Info</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <TouchableOpacity style={styles.container} activeOpacity={1} onPress={handlePress}>
      {currentItem?.content_type?.startsWith('image/') ? (
        <Image
          source={{ uri: mediaUrl || '' }}
          style={styles.fullMedia}
          resizeMode="contain"
        />
      ) : (
        <View style={styles.fullMedia}>
          <Text style={styles.videoPlaceholder}>Video: {currentItem?.filename}</Text>
        </View>
      )}

      {/* Status Overlay */}
      {showOverlay && (
        <View style={styles.overlay}>
          <View style={styles.overlayTop}>
            <View style={styles.overlayLogo}>
              <Text style={styles.overlayLogoText}>TV</Text>
            </View>
            <Text style={styles.overlayTitle}>MediaView Player</Text>
            <View style={{ flex: 1 }} />
            {offline && <Text style={styles.offlineTag}>OFFLINE</Text>}
            <Text style={styles.overlaySync}>Sync: {lastSync}</Text>
          </View>
          <View style={styles.overlayBottom}>
            <Text style={styles.overlayInfo}>
              {currentIndex + 1}/{playlist.length} | {currentItem?.filename} | {currentItem?.duration}s
            </Text>
            <TouchableOpacity style={styles.overlayInfoBtn} onPress={() => router.push('/player/info')}>
              <Text style={styles.overlayInfoBtnText}>Device Info</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000000', justifyContent: 'center', alignItems: 'center' },
  loadingText: { color: '#64748B', fontSize: 16, marginTop: 16 },
  noContent: { alignItems: 'center' },
  noContentIcon: {
    width: 80, height: 80, borderRadius: 20, backgroundColor: '#1E1B4B',
    justifyContent: 'center', alignItems: 'center', marginBottom: 20,
  },
  noContentIconText: { fontSize: 28, fontWeight: '800', color: '#4F46E5' },
  noContentTitle: { fontSize: 32, fontWeight: '700', color: '#FFFFFF' },
  noContentSub: { fontSize: 18, color: '#64748B', marginTop: 8 },
  noContentInfo: { fontSize: 14, color: '#475569', marginTop: 4 },
  offlineBadge: {
    fontSize: 12, fontWeight: '700', color: '#F59E0B', backgroundColor: '#422006',
    paddingHorizontal: 12, paddingVertical: 4, borderRadius: 8, marginTop: 16,
  },
  infoBtn: { position: 'absolute', bottom: 30, right: 30 },
  infoBtnText: { fontSize: 13, color: '#334155' },
  fullMedia: { width: SW, height: SH },
  videoPlaceholder: { color: '#FFF', fontSize: 24, textAlign: 'center', marginTop: SH / 2 - 20 },
  overlay: {
    ...StyleSheet.absoluteFillObject, justifyContent: 'space-between',
    backgroundColor: 'rgba(0,0,0,0.7)',
  },
  overlayTop: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingHorizontal: 24, paddingTop: 24,
  },
  overlayLogo: {
    width: 36, height: 36, borderRadius: 8, backgroundColor: '#4F46E5',
    justifyContent: 'center', alignItems: 'center',
  },
  overlayLogoText: { fontSize: 12, fontWeight: '800', color: '#FFF' },
  overlayTitle: { fontSize: 16, fontWeight: '700', color: '#FFFFFF' },
  overlaySync: { fontSize: 12, color: '#94A3B8' },
  offlineTag: {
    fontSize: 11, fontWeight: '700', color: '#F59E0B', backgroundColor: '#422006',
    paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4, marginRight: 12,
  },
  overlayBottom: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: 24, paddingBottom: 24,
  },
  overlayInfo: { fontSize: 14, color: '#94A3B8' },
  overlayInfoBtn: { backgroundColor: '#1E293B', paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8 },
  overlayInfoBtnText: { fontSize: 13, fontWeight: '600', color: '#FFFFFF' },
});
