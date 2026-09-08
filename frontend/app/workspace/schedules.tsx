import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, ActivityIndicator, TouchableOpacity, RefreshControl,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { workspaceAPI } from '../../src/services/api';
import EmptyState from '../../src/components/EmptyState';

type Row = {
  id: string; name: string; status: string; priority: number; items_count: number;
  schedule: { mode: 'always' | 'scheduled'; days: number[]; start_time: string; end_time: string };
  in_window: boolean; screen_ids: string[]; screen_names: string[]; live_now: boolean;
};

const DAY_LABELS = ['L', 'M', 'M', 'J', 'V', 'S', 'D'];

function daysText(days: number[]): string {
  if (days.length === 7) return 'Todos los días';
  if (days.length === 5 && [0, 1, 2, 3, 4].every(d => days.includes(d))) return 'Lunes a viernes';
  if (days.length === 2 && days.includes(5) && days.includes(6)) return 'Fines de semana';
  return days.sort().map(d => DAY_LABELS[d]).join(' · ');
}

export default function WorkspaceHorarios() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async (isRefresh = false) => {
    try {
      if (isRefresh) setRefreshing(true); else setLoading(true);
      setError('');
      const res = await workspaceAPI.schedules();
      setRows(res.data || []);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'No se pudo cargar');
    } finally { setRefreshing(false); setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <ScrollView
      style={sq.root}
      contentContainerStyle={[sq.content, { paddingBottom: insets.bottom + 24 }]}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor="#0891B2" />}
    >
      <View>
        <Text style={sq.title}>Horarios</Text>
        <Text style={sq.sub}>Programa qué se ve a cada hora: desayuno, comida y cena se cambian solos</Text>
      </View>

      {loading && <ActivityIndicator color="#0891B2" style={{ marginTop: 40 }} />}
      {error !== '' && !loading && <Text style={sq.error}>{error}</Text>}

      {!loading && !error && rows.length === 0 && (
        <EmptyState
          icon="calendar-outline"
          title="Todavía no tienes horarios"
          text="Crea una playlist (por ejemplo 'Menú de desayuno'), elige de qué hora a qué hora se ve y publícala. Al terminar la franja, MediaView cambia sola a la siguiente."
          primary={{ label: 'Crear Playlist', icon: 'add', onPress: () => router.push('/workspace/playlists?new=1') }}
          secondary={{ label: 'Ver mis playlists', icon: 'list-outline', onPress: () => router.push('/workspace/playlists') }}
        />
      )}

      {rows.map(row => {
        const scheduled = row.schedule.mode === 'scheduled';
        return (
          <TouchableOpacity
            key={row.id}
            style={[sq.card, row.live_now && sq.cardLive]}
            onPress={() => router.push({ pathname: '/workspace/playlist-edit', params: { id: row.id } })}
            activeOpacity={0.85}
          >
            <View style={sq.cardTop}>
              <View style={[sq.icon, row.live_now && { backgroundColor: '#D1FAE5' }]}>
                <Ionicons
                  name={scheduled ? 'time' : 'infinite'}
                  size={17}
                  color={row.live_now ? '#059669' : '#0891B2'}
                />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={sq.name}>{row.name}</Text>
                <Text style={sq.window}>
                  {scheduled ? `${row.schedule.start_time} – ${row.schedule.end_time}` : 'Todo el día'}
                  {' · '}{daysText(row.schedule.days)}
                </Text>
              </View>
              {row.live_now ? (
                <View style={sq.liveBadge}>
                  <View style={sq.liveDot} />
                  <Text style={sq.liveText}>EN VIVO</Text>
                </View>
              ) : row.status !== 'published' ? (
                <View style={sq.draftBadge}><Text style={sq.draftText}>Borrador</Text></View>
              ) : row.in_window ? (
                <View style={sq.waitBadge}><Text style={sq.waitText}>En franja</Text></View>
              ) : (
                <View style={sq.offBadge}><Text style={sq.offText}>Fuera de horario</Text></View>
              )}
            </View>

            <View style={sq.cardBottom}>
              <Text style={sq.meta}>
                {row.items_count} elemento{row.items_count !== 1 ? 's' : ''}
                {' · '}
                {row.screen_names.length ? row.screen_names.join(', ') : 'sin pantallas'}
                {scheduled ? ` · prioridad ${row.priority}` : ''}
              </Text>
              <Ionicons name="create-outline" size={16} color="#94A3B8" />
            </View>
          </TouchableOpacity>
        );
      })}

      {rows.length > 0 && (
        <TouchableOpacity style={sq.newBtn} onPress={() => router.push('/workspace/playlists?new=1')} activeOpacity={0.8}>
          <Ionicons name="add" size={16} color="#0891B2" />
          <Text style={sq.newBtnText}>Nueva franja (playlist)</Text>
        </TouchableOpacity>
      )}
    </ScrollView>
  );
}

const sq = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  content: { padding: 20, gap: 12 },
  title: { fontSize: 22, fontWeight: '800', color: '#0F172A', marginBottom: 4 },
  sub: { fontSize: 13, color: '#64748B', marginBottom: 8, lineHeight: 18 },
  error: { color: '#DC2626', fontSize: 13, padding: 16 },
  card: { backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 14, padding: 14, gap: 10 },
  cardLive: { borderColor: '#A7F3D0', backgroundColor: '#F0FDF9' },
  cardTop: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  icon: { width: 36, height: 36, borderRadius: 10, backgroundColor: '#ECFEFF', alignItems: 'center', justifyContent: 'center' },
  name: { fontSize: 14, fontWeight: '700', color: '#0F172A' },
  window: { fontSize: 12, color: '#64748B', marginTop: 2 },
  cardBottom: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, borderTopWidth: 1, borderTopColor: '#F1F5F9', paddingTop: 9 },
  meta: { fontSize: 11.5, color: '#94A3B8', flex: 1 },
  liveBadge: { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: '#D1FAE5', paddingHorizontal: 9, paddingVertical: 4, borderRadius: 20 },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#059669' },
  liveText: { fontSize: 9.5, fontWeight: '800', color: '#065F46', letterSpacing: 0.5 },
  waitBadge: { backgroundColor: '#ECFEFF', paddingHorizontal: 9, paddingVertical: 4, borderRadius: 20 },
  waitText: { fontSize: 10, fontWeight: '700', color: '#0E7490' },
  offBadge: { backgroundColor: '#F1F5F9', paddingHorizontal: 9, paddingVertical: 4, borderRadius: 20 },
  offText: { fontSize: 10, fontWeight: '700', color: '#64748B' },
  draftBadge: { backgroundColor: '#FEF9C3', paddingHorizontal: 9, paddingVertical: 4, borderRadius: 20 },
  draftText: { fontSize: 10, fontWeight: '700', color: '#A16207' },
  newBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: '#ECFEFF', borderWidth: 1, borderColor: '#CFFAFE', borderRadius: 12,
    paddingVertical: 14, minHeight: 46, marginTop: 4,
  },
  newBtnText: { fontSize: 13.5, color: '#0E7490', fontWeight: '700' },
});
