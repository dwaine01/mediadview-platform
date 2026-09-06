import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, ScrollView, StyleSheet, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { workspaceAPI } from '../../src/services/api';

export default function WorkspacePlaylists() {
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try { setLoading(true); setError(''); const res = await workspaceAPI.playlists(); setItems(res.data); }
    catch (e: any) { setError(e.response?.data?.detail || e.message || 'No se pudo cargar'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <ScrollView style={sp.root} contentContainerStyle={[sp.content, { paddingBottom: insets.bottom + 24 }]}>
      <Text style={sp.title}>Playlists</Text>
      <Text style={sp.sub}>{items.length} playlist{items.length !== 1 ? 's' : ''}</Text>
      {loading && <ActivityIndicator color="#0891B2" style={{ marginTop: 40 }} />}
      {error !== '' && !loading && <Text style={sp.error}>{error}</Text>}
      {!loading && items.length === 0 && !error && (
        <View style={sp.empty}><Ionicons name="list-outline" size={40} color="#CBD5E1" />
          <Text style={sp.emptyTitle}>Todavía no tienes playlists</Text>
          <Text style={sp.emptyText}>Crea una playlist para organizar y programar tu contenido.</Text>
        </View>
      )}
      {items.map((p, i) => (
        <View key={p.id || i} style={sp.card}>
          <View style={sp.cardLeft}>
            <View style={sp.icon}><Ionicons name="list" size={18} color="#10B981" /></View>
            <View><Text style={sp.cardName}>{p.name || 'Unnamed Playlist'}</Text>
              <Text style={sp.cardMeta}>{(p.screen_ids || []).length} screen{(p.screen_ids || []).length !== 1 ? 's' : ''}</Text>
            </View>
          </View>
          <View style={[sp.badge, { backgroundColor: p.status === 'published' ? '#D1FAE5' : '#F8FAFC' }]}>
            <Text style={{ color: p.status === 'published' ? '#059669' : '#64748B', fontSize: 11, fontWeight: '700' }}>{p.status || 'draft'}</Text>
          </View>
        </View>
      ))}
    </ScrollView>
  );
}

const sp = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' }, content: { padding: 20, gap: 12 },
  title: { fontSize: 22, fontWeight: '800', color: '#0F172A', marginBottom: 4 }, sub: { fontSize: 13, color: '#64748B', marginBottom: 8 },
  error: { color: '#DC2626', fontSize: 13, padding: 16 },
  empty: { alignItems: 'center', paddingVertical: 60, gap: 12 },
  emptyTitle: { fontSize: 16, fontWeight: '700', color: '#64748B' }, emptyText: { fontSize: 13, color: '#64748B', textAlign: 'center', maxWidth: 280 },
  card: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 12, padding: 14 },
  cardLeft: { flexDirection: 'row', alignItems: 'center', gap: 12, flex: 1 },
  icon: { width: 36, height: 36, borderRadius: 10, backgroundColor: '#10B98122', justifyContent: 'center', alignItems: 'center' },
  cardName: { fontSize: 13, fontWeight: '600', color: '#0F172A' }, cardMeta: { fontSize: 11, color: '#64748B', marginTop: 2 },
  badge: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: 20 },
});
