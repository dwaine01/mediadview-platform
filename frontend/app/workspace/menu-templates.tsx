/**
 * menu-templates.tsx — biblioteca de plantillas del cliente.
 *
 * Cada vez que la IA lee un menú diseñado, ese layout queda guardado acá. El
 * restaurante arma el menú de la semana en dos toques: elige la plantilla y
 * sólo cambia nombres, precios y fotos. El diseño se reusa tal cual.
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Image, ActivityIndicator, RefreshControl, FlatList,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { workspaceAPI } from '../../src/services/api';
import AppDialog, { type DialogState } from '../../src/components/AppDialog';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

type Template = {
  id: string;
  name: string;
  background_url: string;
  width: number;
  height: number;
  texts: number;
  photos: number;
};

export default function MenuTemplates() {
  const insets = useSafeAreaInsets();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [usingId, setUsingId] = useState<string | null>(null);
  const [dialog, setDialog] = useState<DialogState>(null);

  const load = useCallback(async () => {
    try {
      const res = await workspaceAPI.menuTemplates();
      setTemplates(res.data || []);
    } catch (e: any) {
      setDialog({
        title: 'No pudimos cargar tus plantillas',
        message: e.response?.data?.detail || e.message,
      });
    } finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const applyTemplate = async (template: Template) => {
    setUsingId(template.id);
    try {
      const res = await workspaceAPI.useMenuTemplate(template.id);
      router.push(`/workspace/menu-canvas?id=${res.data.menu_id}`);
    } catch (e: any) {
      setDialog({
        title: 'No se pudo usar la plantilla',
        message: e.response?.data?.detail || e.message,
      });
    } finally { setUsingId(null); }
  };

  const removeTemplate = (template: Template) => setDialog({
    title: `¿Borrar «${template.name}»?`,
    message: 'Los menús que ya armaste con esta plantilla no se tocan.',
    icon: 'trash-outline',
    options: [
      { label: 'Borrar plantilla', destructive: true, onPress: async () => {
        try { await workspaceAPI.deleteMenuTemplate(template.id); load(); }
        catch (e: any) {
          setDialog({ title: 'No se pudo borrar', message: e.response?.data?.detail || e.message });
        }
      }},
      { label: 'Cancelar' },
    ],
  });

  const renderTemplate = ({ item }: { item: Template }) => (
    <View style={st.card}>
      <TouchableOpacity
        style={st.preview}
        onPress={() => applyTemplate(item)}
        activeOpacity={0.85}
        testID={`template-${item.id}`}
      >
        <Image
          source={{ uri: `${API_URL}${item.background_url}` }}
          style={[st.previewImg, { aspectRatio: (item.width || 16) / (item.height || 9) }]}
          resizeMode="contain"
        />
      </TouchableOpacity>
      <View style={st.cardBody}>
        <View style={{ flex: 1 }}>
          <Text style={st.cardTitle} numberOfLines={1}>{item.name}</Text>
          <Text style={st.cardMeta}>
            {item.texts} texto{item.texts === 1 ? '' : 's'} · {item.photos} foto{item.photos === 1 ? '' : 's'}
          </Text>
        </View>
        <TouchableOpacity
          onPress={() => removeTemplate(item)}
          hitSlop={10}
          style={st.trashBtn}
          testID={`delete-template-${item.id}`}
        >
          <Ionicons name="trash-outline" size={17} color="#94A3B8" />
        </TouchableOpacity>
      </View>
      <TouchableOpacity
        style={[st.useBtn, usingId === item.id && { opacity: 0.6 }]}
        onPress={() => applyTemplate(item)}
        disabled={usingId === item.id}
        testID={`use-template-${item.id}`}
      >
        {usingId === item.id
          ? <ActivityIndicator size={15} color="#fff" />
          : <>
              <Ionicons name="duplicate-outline" size={17} color="#fff" />
              <Text style={st.useBtnText}>Usar esta plantilla</Text>
            </>}
      </TouchableOpacity>
    </View>
  );

  return (
    <View style={st.root}>
      <View style={[st.topBar, { paddingTop: insets.top + 8 }]}>
        <TouchableOpacity style={st.backBtn} onPress={() => router.back()} hitSlop={10}>
          <Ionicons name="arrow-back" size={20} color="#64748B" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={st.topTitle}>Mis plantillas</Text>
          <Text style={st.topSub}>Diseños listos para reusar</Text>
        </View>
      </View>

      {loading ? (
        <View style={st.center}><ActivityIndicator color="#0891B2" size="large" /></View>
      ) : (
        <FlatList
          data={templates}
          keyExtractor={item => item.id}
          renderItem={renderTemplate}
          contentContainerStyle={[st.list, { paddingBottom: insets.bottom + 32 }]}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} />
          }
          ListEmptyComponent={
            <View style={st.empty}>
              <View style={st.emptyIcon}>
                <Ionicons name="albums-outline" size={30} color="#7C3AED" />
              </View>
              <Text style={st.emptyTitle}>Todavía no tenés plantillas</Text>
              <Text style={st.emptyText}>
                Subí tu menú diseñado desde cualquier menú («Usar mi propio diseño») y la IA lo
                guarda acá como plantilla. Después armás menús nuevos en dos toques.
              </Text>
              <TouchableOpacity
                style={st.emptyBtn}
                onPress={() => router.push('/workspace/menus')}
                testID="go-to-menus"
              >
                <Text style={st.emptyBtnText}>Ir a mis menús</Text>
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
  topBar: {
    flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingBottom: 12,
    backgroundColor: '#FFFFFF', borderBottomWidth: 1, borderBottomColor: '#E2E8F0',
  },
  backBtn: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center', backgroundColor: '#F1F5F9' },
  topTitle: { fontSize: 16, fontWeight: '800', color: '#0F172A' },
  topSub: { fontSize: 11, color: '#64748B', fontWeight: '600' },

  list: { padding: 16, gap: 16 },
  card: { backgroundColor: '#FFFFFF', borderRadius: 16, borderWidth: 1, borderColor: '#E2E8F0', overflow: 'hidden' },
  preview: { backgroundColor: '#F1F5F9' },
  previewImg: { width: '100%' },
  cardBody: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 14, paddingTop: 12 },
  cardTitle: { fontSize: 15, fontWeight: '700', color: '#0F172A' },
  cardMeta: { fontSize: 11, color: '#64748B', marginTop: 2 },
  trashBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  useBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#7C3AED', margin: 14, minHeight: 46, borderRadius: 12 },
  useBtnText: { color: '#fff', fontSize: 14, fontWeight: '700' },

  empty: { alignItems: 'center', gap: 12, paddingTop: 60, paddingHorizontal: 12 },
  emptyIcon: { width: 64, height: 64, borderRadius: 18, backgroundColor: '#F5F3FF', justifyContent: 'center', alignItems: 'center' },
  emptyTitle: { fontSize: 18, fontWeight: '800', color: '#0F172A' },
  emptyText: { fontSize: 14, color: '#475569', textAlign: 'center', lineHeight: 21 },
  emptyBtn: { marginTop: 6, minHeight: 46, paddingHorizontal: 22, borderRadius: 12, backgroundColor: '#0891B2', justifyContent: 'center' },
  emptyBtnText: { color: '#fff', fontSize: 14, fontWeight: '700' },
});
