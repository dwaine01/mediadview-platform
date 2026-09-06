import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, ActivityIndicator, TouchableOpacity,
  TextInput, Image, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import { workspaceAPI } from '../../src/services/api';
import AppDialog, { type DialogState } from '../../src/components/AppDialog';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

type Item = {
  id: string; type: 'media' | 'menu'; ref_id: string; title: string; duration: number;
};

type LibraryEntry = { id: string; title: string; kind: 'media' | 'menu'; thumb?: string | null };

export default function PlaylistEdit() {
  const insets = useSafeAreaInsets();
  const { id } = useLocalSearchParams<{ id: string }>();

  const [name, setName] = useState('');
  const [status, setStatus] = useState('draft');
  const [items, setItems] = useState<Item[]>([]);
  const [library, setLibrary] = useState<LibraryEntry[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState('');
  const [dialog, setDialog] = useState<DialogState>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true); setError('');
      const [plRes, mediaRes, menusRes] = await Promise.all([
        workspaceAPI.playlists(), workspaceAPI.media(), workspaceAPI.menus(),
      ]);
      const pl = (plRes.data || []).find((p: any) => p.id === id);
      if (!pl) { setError('Playlist no encontrada'); return; }
      setName(pl.name || '');
      setStatus(pl.status || 'draft');
      setItems((pl.items || []).map((it: any) => ({
        id: it.id, type: it.type, ref_id: it.ref_id,
        title: it.title || 'Contenido', duration: Number(it.duration) || 15,
      })));
      setLibrary([
        ...(menusRes.data || []).map((m: any) => ({ id: m.id, title: m.name || 'Menú', kind: 'menu' as const, thumb: null })),
        ...(mediaRes.data || []).map((m: any) => ({
          id: m.id, title: m.filename || 'Archivo', kind: 'media' as const,
          thumb: (m.content_type || '').startsWith('image') ? `${API_URL}/api/player/media/${m.id}` : null,
        })),
      ]);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'No se pudo cargar');
    } finally { setLoading(false); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const move = (index: number, delta: number) => {
    setItems(prev => {
      const next = [...prev];
      const target = index + delta;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
    setDirty(true);
  };

  const setDuration = (index: number, raw: string) => {
    const digits = raw.replace(/\D/g, '').slice(0, 4);
    setItems(prev => prev.map((it, i) => i === index ? { ...it, duration: digits === '' ? 0 : Number(digits) } : it));
    setDirty(true);
  };

  const remove = (index: number) => {
    setItems(prev => prev.filter((_, i) => i !== index));
    setDirty(true);
  };

  const addFromLibrary = (entry: LibraryEntry) => {
    setItems(prev => [...prev, {
      id: `new-${Date.now()}`, type: entry.kind, ref_id: entry.id, title: entry.title, duration: 15,
    }]);
    setDirty(true);
    setShowAdd(false);
  };

  const thumbFor = (it: Item) =>
    it.type === 'media' ? `${API_URL}/api/player/media/${it.ref_id}` : null;

  const save = useCallback(async () => {
    if (!name.trim()) { setDialog({ title: 'Ponle un nombre a la playlist' }); return; }
    if (items.some(it => it.duration < 3)) {
      setDialog({ title: 'Duración muy corta', message: 'Cada elemento debe durar al menos 3 segundos.' });
      return;
    }
    setSaving(true);
    try {
      await workspaceAPI.updatePlaylist(String(id), {
        name: name.trim(),
        items: items.map(it => ({ type: it.type, ref_id: it.ref_id, title: it.title, duration: it.duration })),
      });
      setDirty(false);
      setDialog({
        title: 'Cambios guardados',
        icon: 'checkmark-circle-outline',
        message: status === 'published'
          ? 'Tus pantallas se actualizarán en unos segundos.'
          : 'Publica la playlist cuando quieras verla en tus pantallas.',
        options: [{ label: 'Volver a Playlists', primary: true, onPress: () => router.push('/workspace/playlists') },
                  { label: 'Seguir editando' }],
      });
    } catch (e: any) {
      setDialog({ title: 'No se pudo guardar', message: e.response?.data?.detail || e.message });
    } finally { setSaving(false); }
  }, [id, name, items, status]);

  const total = items.reduce((sum, it) => sum + (it.duration || 0), 0);

  return (
    <View style={pe.root}>
      <ScrollView contentContainerStyle={[pe.content, { paddingBottom: insets.bottom + 32 }]} keyboardShouldPersistTaps="handled">
        <View style={pe.header}>
          <TouchableOpacity onPress={() => router.push('/workspace/playlists')} style={pe.backBtn} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
            <Ionicons name="arrow-back" size={20} color="#64748B" />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={pe.title}>Editar Playlist</Text>
            <Text style={pe.sub}>
              {items.length} elemento{items.length !== 1 ? 's' : ''} · ciclo de {Math.floor(total / 60)}m {total % 60}s
              {status === 'published' ? ' · en vivo' : ' · borrador'}
            </Text>
          </View>
        </View>

        {loading && <ActivityIndicator color="#0891B2" style={{ marginTop: 40 }} />}
        {error !== '' && !loading && <Text style={pe.error}>{error}</Text>}

        {!loading && !error && (
          <>
            <Text style={pe.label}>Nombre</Text>
            <TextInput
              style={pe.input}
              value={name}
              onChangeText={(t) => { setName(t); setDirty(true); }}
              placeholder="Nombre de la playlist"
              placeholderTextColor="#CBD5E1"
            />

            <Text style={[pe.label, { marginTop: 20 }]}>Orden y duración</Text>
            {items.length === 0 && (
              <Text style={pe.emptyHint}>Esta playlist está vacía. Agrega contenido abajo.</Text>
            )}
            {items.map((it, i) => {
              const uri = thumbFor(it);
              return (
                <View key={it.id} style={pe.itemRow}>
                  <Text style={pe.pos}>{i + 1}</Text>
                  {uri
                    ? <Image source={{ uri }} style={pe.thumb} resizeMode="cover" />
                    : <View style={pe.thumbFallback}><Ionicons name="restaurant" size={16} color="#0891B2" /></View>}
                  <View style={{ flex: 1 }}>
                    <Text style={pe.itemTitle} numberOfLines={1}>{it.title}</Text>
                    <View style={pe.durRow}>
                      <TextInput
                        style={pe.durInput}
                        value={String(it.duration || '')}
                        onChangeText={(t) => setDuration(i, t)}
                        keyboardType="number-pad"
                        maxLength={4}
                      />
                      <Text style={pe.durUnit}>segundos</Text>
                    </View>
                  </View>
                  <View style={pe.itemActions}>
                    <TouchableOpacity onPress={() => move(i, -1)} disabled={i === 0} style={pe.iconBtn}>
                      <Ionicons name="arrow-up" size={17} color={i === 0 ? '#CBD5E1' : '#0891B2'} />
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => move(i, 1)} disabled={i === items.length - 1} style={pe.iconBtn}>
                      <Ionicons name="arrow-down" size={17} color={i === items.length - 1 ? '#CBD5E1' : '#0891B2'} />
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => remove(i)} style={pe.iconBtn}>
                      <Ionicons name="close" size={18} color="#DC2626" />
                    </TouchableOpacity>
                  </View>
                </View>
              );
            })}

            <TouchableOpacity style={pe.addBtn} onPress={() => setShowAdd(v => !v)} activeOpacity={0.8}>
              <Ionicons name={showAdd ? 'chevron-up' : 'add'} size={16} color="#0891B2" />
              <Text style={pe.addBtnText}>{showAdd ? 'Cerrar biblioteca' : 'Agregar contenido'}</Text>
            </TouchableOpacity>

            {showAdd && library.map(l => (
              <TouchableOpacity key={`${l.kind}-${l.id}`} style={pe.libRow} onPress={() => addFromLibrary(l)} activeOpacity={0.8}>
                {l.thumb
                  ? <Image source={{ uri: l.thumb }} style={pe.thumb} resizeMode="cover" />
                  : <View style={pe.thumbFallback}><Ionicons name={l.kind === 'menu' ? 'restaurant' : 'document'} size={16} color="#0891B2" /></View>}
                <View style={{ flex: 1 }}>
                  <Text style={pe.itemTitle} numberOfLines={1}>{l.title}</Text>
                  <Text style={pe.libKind}>{l.kind === 'menu' ? 'Menú digital' : 'Imagen'}</Text>
                </View>
                <Ionicons name="add-circle-outline" size={22} color="#0891B2" />
              </TouchableOpacity>
            ))}

            <TouchableOpacity
              style={[pe.saveBtn, (!dirty || saving) && { opacity: 0.55 }]}
              onPress={save}
              disabled={!dirty || saving}
              activeOpacity={0.85}
            >
              {saving ? <ActivityIndicator color="#fff" /> : <Text style={pe.saveText}>Guardar Cambios</Text>}
            </TouchableOpacity>
          </>
        )}
      </ScrollView>

      <AppDialog state={dialog} onDismiss={() => setDialog(null)} />
    </View>
  );
}

const pe = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  content: { padding: 20 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 18 },
  backBtn: { width: 40, height: 40, borderRadius: 12, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', alignItems: 'center', justifyContent: 'center' },
  title: { fontSize: 20, fontWeight: '800', color: '#0F172A' },
  sub: { fontSize: 12.5, color: '#64748B', marginTop: 2 },
  error: { color: '#DC2626', fontSize: 13, padding: 16 },
  label: { fontSize: 11, fontWeight: '700', color: '#64748B', letterSpacing: 0.6, textTransform: 'uppercase', marginBottom: 8 },
  input: {
    fontSize: 15, color: '#0F172A', backgroundColor: '#FFFFFF', borderWidth: 1,
    borderColor: '#E2E8F0', borderRadius: 12, padding: 14,
    ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : null),
  },
  emptyHint: { fontSize: 12.5, color: '#94A3B8', marginBottom: 8 },
  itemRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#FFFFFF',
    borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 12, padding: 12, marginBottom: 8,
  },
  pos: { width: 18, fontSize: 12, fontWeight: '800', color: '#94A3B8', textAlign: 'center' },
  thumb: { width: 52, height: 40, borderRadius: 8, backgroundColor: '#E2E8F0' },
  thumbFallback: { width: 52, height: 40, borderRadius: 8, backgroundColor: '#CFFAFE', alignItems: 'center', justifyContent: 'center' },
  itemTitle: { fontSize: 13, fontWeight: '600', color: '#0F172A' },
  durRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 5 },
  durInput: {
    width: 56, fontSize: 13, fontWeight: '700', color: '#0F172A', textAlign: 'center',
    backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 8,
    paddingVertical: 6,
    ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : null),
  },
  durUnit: { fontSize: 11.5, color: '#64748B' },
  itemActions: { flexDirection: 'row', gap: 2 },
  iconBtn: { width: 34, height: 34, borderRadius: 9, alignItems: 'center', justifyContent: 'center', backgroundColor: '#F8FAFC' },
  addBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: '#ECFEFF', borderWidth: 1, borderColor: '#CFFAFE', borderRadius: 12,
    paddingVertical: 14, marginTop: 6, marginBottom: 10, minHeight: 46,
  },
  addBtnText: { fontSize: 13.5, color: '#0E7490', fontWeight: '700' },
  libRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#FFFFFF',
    borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 12, padding: 10, marginBottom: 8,
  },
  libKind: { fontSize: 11, color: '#64748B', marginTop: 2 },
  saveBtn: { backgroundColor: '#0891B2', borderRadius: 14, paddingVertical: 16, alignItems: 'center', marginTop: 18 },
  saveText: { color: '#FFFFFF', fontSize: 15, fontWeight: '700' },
});
