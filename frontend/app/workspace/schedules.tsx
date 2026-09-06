import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, ScrollView, StyleSheet, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { workspaceAPI } from '../../src/services/api';

export default function WorkspaceHorarios() {
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try { setLoading(true); setError(''); const res = await workspaceAPI.schedules(); setItems(res.data); }
    catch (e: any) { setError(e.response?.data?.detail || e.message || 'No se pudo cargar'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const fmtDate = (d?: string) => d ? new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—';

  return (
    <ScrollView style={sq.root} contentContainerStyle={[sq.content, { paddingBottom: insets.bottom + 24 }]}>
      <Text style={sq.title}>Horarios</Text>
      <Text style={sq.sub}>{items.length} horario{items.length !== 1 ? 's' : ''}</Text>
      {loading && <ActivityIndicator color="#0891B2" style={{ marginTop: 40 }} />}
      {error !== '' && !loading && <Text style={sq.error}>{error}</Text>}
      {!loading && items.length === 0 && !error && (
        <View style={sq.empty}><Ionicons name="calendar-outline" size={40} color="#CBD5E1" />
          <Text style={sq.emptyTitle}>Todavía no tienes horarios</Text>
          <Text style={sq.emptyText}>Crea un horario para controlar cuándo se reproduce tu contenido en cada pantalla.</Text>
        </View>
      )}
      {items.map((c, i) => (
        <View key={c.id || i} style={sq.card}>
          <View style={sq.cardLeft}>
            <View style={sq.icon}><Ionicons name="calendar" size={18} color="#D97706" /></View>
            <View><Text style={sq.cardName}>{c.name || 'Unnamed'}</Text>
              <Text style={sq.cardMeta}>{c.schedule?.start_date ? `${c.schedule.start_date} → ${c.schedule.end_date || '...'}` : fmtDate(c.starts_at)}</Text>
            </View>
          </View>
          <View style={[sq.badge, { backgroundColor: c.status === 'active' || c.status === 'published' ? '#D1FAE5' : '#F8FAFC' }]}>
            <Text style={{ color: c.status === 'active' || c.status === 'published' ? '#059669' : '#64748B', fontSize: 11, fontWeight: '700' }}>{c.status || '—'}</Text>
          </View>
        </View>
      ))}
    </ScrollView>
  );
}

const sq = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' }, content: { padding: 20, gap: 12 },
  title: { fontSize: 22, fontWeight: '800', color: '#0F172A', marginBottom: 4 }, sub: { fontSize: 13, color: '#64748B', marginBottom: 8 },
  error: { color: '#DC2626', fontSize: 13, padding: 16 },
  empty: { alignItems: 'center', paddingVertical: 60, gap: 12 },
  emptyTitle: { fontSize: 16, fontWeight: '700', color: '#64748B' }, emptyText: { fontSize: 13, color: '#64748B', textAlign: 'center', maxWidth: 280 },
  card: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 12, padding: 14 },
  cardLeft: { flexDirection: 'row', alignItems: 'center', gap: 12, flex: 1 },
  icon: { width: 36, height: 36, borderRadius: 10, backgroundColor: '#D9770622', justifyContent: 'center', alignItems: 'center' },
  cardName: { fontSize: 13, fontWeight: '600', color: '#0F172A' }, cardMeta: { fontSize: 11, color: '#64748B', marginTop: 2 },
  badge: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: 20 },
});
