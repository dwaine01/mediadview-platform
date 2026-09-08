import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, Image, StyleSheet, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { workspaceAPI } from '../services/api';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

export type ScreenLive = {
  screen_id: string;
  screen_name: string;
  location?: string | null;
  is_online: boolean;
  connectivity?: 'ONLINE' | 'STALE' | 'OFFLINE' | 'NEVER';
  player_state?: string | null;
  app_version?: string | null;
  sync_progress?: {
    files_done: number; files_total: number; percent: number;
    bytes_done: number; bytes_total: number; current_file?: string | null;
  } | null;
  last_seen_seconds?: number | null;
  cycle_seconds: number;
  now_playing?: {
    index: number; total: number; title: string;
    kind: 'image' | 'video' | 'menu';
    thumb_url?: string | null;
    duration: number; seconds_left: number; playlist_name?: string | null;
  } | null;
};

/** Etiquetas en español de los estados que reporta el reproductor. */
const STATE_LABELS: Record<string, string> = {
  BOOTING: 'Encendiendo', INITIALIZING: 'Iniciando', UNPAIRED: 'Sin emparejar',
  PAIRING: 'Emparejando', PAIRED: 'Emparejada', WAITING_FOR_ASSIGNMENT: 'Sin contenido',
  SYNCING: 'Sincronizando', DOWNLOADING: 'Descargando', VALIDATING: 'Validando',
  READY: 'Lista', PLAYING: 'Reproduciendo', OFFLINE_PLAYING_CACHE: 'Sin internet · usando caché',
  DEGRADED: 'Necesita atención', ERROR: 'Error', RECOVERING: 'Recuperándose',
  UPDATING: 'Actualizando', RESTARTING: 'Reiniciando',
};

function lastSeen(seconds?: number | null): string {
  if (seconds === null || seconds === undefined) return 'nunca conectada';
  if (seconds < 60) return `hace ${seconds}s`;
  if (seconds < 3600) return `hace ${Math.round(seconds / 60)} min`;
  if (seconds < 86400) return `hace ${Math.round(seconds / 3600)} h`;
  return `hace ${Math.round(seconds / 86400)} d`;
}

/** One screen card with a thumbnail of whatever is on air right now. */
function LiveCard({ item, onPress }: { item: ScreenLive; onPress?: () => void }) {
  // Regla de oro: si el reproductor no está en línea, NO mostramos lo que
  // "debería" verse como si fuera real. Solo lo anunciamos como programado.
  const np = item.is_online ? item.now_playing : null;
  const scheduled = item.is_online ? null : item.now_playing;
  // Local 1s tick so the countdown feels live between polls
  const [left, setLeft] = useState(np?.seconds_left ?? 0);

  useEffect(() => {
    setLeft(np?.seconds_left ?? 0);
    if (!np) return;
    const timer = setInterval(() => setLeft(v => (v > 0 ? v - 1 : 0)), 1000);
    return () => clearInterval(timer);
  }, [np?.title, np?.seconds_left, np]);
  return (
    <TouchableOpacity style={lv.card} onPress={onPress} activeOpacity={onPress ? 0.85 : 1} disabled={!onPress}>
      <View style={lv.stage}>
        {np?.thumb_url ? (
          <Image source={{ uri: `${API_URL}${np.thumb_url}` }} style={lv.thumb} resizeMode="cover" />
        ) : np?.kind === 'menu' ? (
          <View style={[lv.thumb, lv.menuThumb]}>
            <Ionicons name="restaurant" size={26} color="#0891B2" />
            <Text style={lv.menuThumbText} numberOfLines={1}>{np.title}</Text>
          </View>
        ) : (
          <View style={[lv.thumb, lv.blankThumb]}>
            <Ionicons name={item.is_online ? 'power-outline' : 'cloud-offline-outline'} size={24} color="#94A3B8" />
            <Text style={lv.blankText}>
              {item.is_online ? 'Sin contenido' : 'Sin señal del reproductor'}
            </Text>
          </View>
        )}

        <View style={[
          lv.badge,
          item.is_online ? lv.badgeLive : item.connectivity === 'STALE' ? lv.badgeStale : lv.badgeOff,
        ]}>
          <View style={[lv.dot, {
            backgroundColor: item.is_online ? '#22C55E' : item.connectivity === 'STALE' ? '#D97706' : '#94A3B8',
          }]} />
          <Text style={[lv.badgeText, {
            color: item.is_online ? '#065F46' : item.connectivity === 'STALE' ? '#92400E' : '#475569',
          }]}>
            {item.is_online ? 'EN VIVO' : item.connectivity === 'STALE' ? 'SIN SEÑAL' : 'OFFLINE'}
          </Text>
        </View>

        {!!item.sync_progress && (
          <View style={lv.syncOverlay}>
            <Text style={lv.syncText}>
              Sincronizando {Math.round(item.sync_progress.percent)}% · {item.sync_progress.files_done} de {item.sync_progress.files_total}
            </Text>
            <View style={lv.syncTrack}>
              <View style={[lv.syncFill, { width: `${Math.min(100, item.sync_progress.percent)}%` }]} />
            </View>
          </View>
        )}

        {!!np && (
          <View style={lv.stamp}>
            <Text style={lv.stampText}>{np.index}/{np.total} · {left}s</Text>
          </View>
        )}
      </View>

      <View style={lv.meta}>
        <Text style={lv.name} numberOfLines={1}>{item.screen_name}</Text>
        <Text style={lv.detail} numberOfLines={1}>
          {np
            ? `${np.title}${np.playlist_name ? ` · ${np.playlist_name}` : ''}`
            : scheduled
              ? `Programado: ${scheduled.title} · última señal ${lastSeen(item.last_seen_seconds)}`
              : `Última señal ${lastSeen(item.last_seen_seconds)}`}
        </Text>
        {!!item.player_state && (
          <Text style={lv.state} numberOfLines={1}>
            {STATE_LABELS[item.player_state] || item.player_state}
            {item.app_version ? ` · v${item.app_version}` : ''}
          </Text>
        )}
      </View>
    </TouchableOpacity>
  );
}

type Props = { onPressScreen?: () => void; refreshMs?: number };

/** Auto-refreshing grid of live screen thumbnails. */
export default function LiveScreens({ onPressScreen, refreshMs = 15000 }: Props) {
  const [screens, setScreens] = useState<ScreenLive[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const res = await workspaceAPI.nowPlaying();
      setScreens(res.data || []);
      setError('');
    } catch (e: any) {
      setError(e.response?.data?.detail || 'No se pudo cargar la vista en vivo');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, refreshMs);
    return () => clearInterval(timer);
  }, [load, refreshMs]);

  if (loading) return <ActivityIndicator color="#0891B2" style={{ marginVertical: 24 }} />;
  if (error) return <Text style={lv.error}>{error}</Text>;
  if (screens.length === 0) return null;

  return (
    <View style={lv.grid}>
      {screens.map(s => <LiveCard key={s.screen_id} item={s} onPress={onPressScreen} />)}
    </View>
  );
}

const lv = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 14 },
  card: {
    flexGrow: 1, flexBasis: 210, minWidth: 200, maxWidth: 300,
    backgroundColor: '#FFFFFF', borderWidth: 1,
    borderColor: '#E2E8F0', borderRadius: 14, overflow: 'hidden',
  },
  stage: { position: 'relative', backgroundColor: '#0F172A', aspectRatio: 16 / 9 },
  thumb: { width: '100%', height: '100%' },
  menuThumb: { backgroundColor: '#ECFEFF', alignItems: 'center', justifyContent: 'center', gap: 6, paddingHorizontal: 12 },
  menuThumbText: { fontSize: 12, fontWeight: '700', color: '#0E7490' },
  blankThumb: { backgroundColor: '#F1F5F9', alignItems: 'center', justifyContent: 'center', gap: 6 },
  blankText: { fontSize: 11.5, color: '#94A3B8', fontWeight: '600' },
  badge: {
    position: 'absolute', top: 8, left: 8, flexDirection: 'row', alignItems: 'center',
    gap: 5, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 20,
  },
  badgeLive: { backgroundColor: '#D1FAE5' },
  badgeOff: { backgroundColor: '#E2E8F0' },
  badgeStale: { backgroundColor: '#FEF3C7' },
  syncOverlay: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    backgroundColor: 'rgba(15,23,42,0.82)', paddingHorizontal: 10, paddingVertical: 8, gap: 6,
  },
  syncText: { fontSize: 10.5, fontWeight: '700', color: '#FFFFFF' },
  syncTrack: { height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.25)', overflow: 'hidden' },
  syncFill: { height: 4, borderRadius: 2, backgroundColor: '#22D3EE' },
  dot: { width: 6, height: 6, borderRadius: 3 },
  badgeText: { fontSize: 9.5, fontWeight: '800', letterSpacing: 0.6 },
  stamp: {
    position: 'absolute', bottom: 8, right: 8, backgroundColor: 'rgba(15,23,42,0.72)',
    paddingHorizontal: 7, paddingVertical: 3, borderRadius: 6,
  },
  stampText: { fontSize: 10, color: '#FFFFFF', fontWeight: '700' },
  meta: { padding: 12, gap: 2 },
  name: { fontSize: 13.5, fontWeight: '700', color: '#0F172A' },
  detail: { fontSize: 11.5, color: '#64748B' },
  state: { fontSize: 10.5, color: '#0891B2', fontWeight: '700', marginTop: 2 },
  error: { fontSize: 12.5, color: '#DC2626', paddingVertical: 12 },
});
