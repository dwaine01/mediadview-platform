/** designs.tsx — «Mis diseños»: lo que el cliente armó desde las plantillas. */
import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, FlatList, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { workspaceAPI } from '../../src/services/api';
import AppDialog, { type DialogState } from '../../src/components/AppDialog';

export default function Designs() {
  const insets = useSafeAreaInsets();
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialog, setDialog] = useState<DialogState>(null);

  const load = useCallback(async () => {
    try {
      setRows((await workspaceAPI.designs()).data || []);
    } catch (e: any) {
      setDialog({ title: 'No pudimos cargar tus diseños',
                  message: e.response?.data?.detail || e.message });
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const remove = (row: any) => setDialog({
    title: `¿Borrar «${row.name}»?`,
    message: 'Si está en vivo, las pantallas dejan de mostrarlo.',
    icon: 'trash-outline',
    options: [
      { label: 'Borrar', destructive: true, onPress: async () => {
        try { await workspaceAPI.deleteDesign(row.id); load(); }
        catch (e: any) { setDialog({ title: 'No se pudo borrar',
                                     message: e.response?.data?.detail || e.message }); }
      }},
      { label: 'Cancelar' },
    ],
  });

  return (
    <View style={st.root}>
      <View style={[st.topBar, { paddingTop: insets.top + 8 }]}>
        <TouchableOpacity style={st.backBtn} onPress={() => router.back()} hitSlop={10}>
          <Ionicons name="arrow-back" size={20} color="#64748B" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={st.topTitle}>Mis diseños</Text>
          <Text style={st.topSub}>{rows.length} diseño{rows.length === 1 ? '' : 's'}</Text>
        </View>
        <TouchableOpacity
          style={st.newBtn}
          onPress={() => router.push('/workspace/signage-templates')}
          testID="new-design"
        >
          <Ionicons name="add" size={16} color="#fff" />
          <Text style={st.newBtnText}>Nuevo</Text>
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={st.center}><ActivityIndicator size="large" color="#7C3AED" /></View>
      ) : (
        <FlatList
          data={rows}
          keyExtractor={row => row.id}
          contentContainerStyle={[st.list, { paddingBottom: insets.bottom + 24 }]}
          renderItem={({ item }) => (
            <TouchableOpacity
              style={st.card}
              onPress={() => router.push(`/workspace/design-edit?id=${item.id}`)}
              testID={`design-${item.id}`}
            >
              <View style={[st.dot, { backgroundColor: item.status === 'published' ? '#059669' : '#CBD5E1' }]} />
              <View style={{ flex: 1 }}>
                <Text style={st.cardName} numberOfLines={1}>{item.name}</Text>
                <Text style={st.cardMeta}>
                  {item.status === 'published'
                    ? `En vivo en ${(item.screen_ids || []).length} pantalla${(item.screen_ids || []).length === 1 ? '' : 's'}`
                    : 'Sin publicar'}
                </Text>
              </View>
              <TouchableOpacity onPress={() => remove(item)} hitSlop={10} style={st.trash}
                                testID={`delete-design-${item.id}`}>
                <Ionicons name="trash-outline" size={17} color="#94A3B8" />
              </TouchableOpacity>
            </TouchableOpacity>
          )}
          ListEmptyComponent={
            <View style={st.empty}>
              <Ionicons name="color-wand-outline" size={30} color="#94A3B8" />
              <Text style={st.emptyText}>
                Todavía no armaste ninguno. Elegí una plantilla profesional y reemplazá los
                productos por los tuyos.
              </Text>
              <TouchableOpacity
                style={st.emptyBtn}
                onPress={() => router.push('/workspace/signage-templates')}
                testID="browse-templates"
              >
                <Text style={st.emptyBtnText}>Ver plantillas</Text>
              </TouchableOpacity>
            </View>
          }
        />
      )}

      <AppDialog state={dialog} onDismiss={() => setDialog(null)} />
    </View>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  topBar: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingBottom: 12, backgroundColor: '#FFFFFF', borderBottomWidth: 1, borderBottomColor: '#E2E8F0' },
  backBtn: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center', backgroundColor: '#F1F5F9' },
  topTitle: { fontSize: 16, fontWeight: '800', color: '#0F172A' },
  topSub: { fontSize: 11, color: '#64748B', fontWeight: '600' },
  newBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: '#7C3AED', paddingHorizontal: 13, minHeight: 40, borderRadius: 10, justifyContent: 'center' },
  newBtnText: { color: '#fff', fontSize: 13, fontWeight: '700' },
  list: { padding: 16, gap: 10 },
  card: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#FFFFFF', borderRadius: 14, borderWidth: 1, borderColor: '#E2E8F0', paddingHorizontal: 14, minHeight: 68 },
  dot: { width: 9, height: 9, borderRadius: 5 },
  cardName: { fontSize: 15, fontWeight: '700', color: '#0F172A' },
  cardMeta: { fontSize: 12, color: '#64748B', marginTop: 2 },
  trash: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  empty: { alignItems: 'center', gap: 12, paddingTop: 60, paddingHorizontal: 18 },
  emptyText: { fontSize: 14, color: '#475569', textAlign: 'center', lineHeight: 21 },
  emptyBtn: { minHeight: 46, paddingHorizontal: 22, borderRadius: 12, backgroundColor: '#7C3AED', justifyContent: 'center' },
  emptyBtnText: { color: '#fff', fontSize: 14, fontWeight: '700' },
});
