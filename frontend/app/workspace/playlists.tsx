import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, ActivityIndicator, TouchableOpacity,
  TextInput, Modal, Image, useWindowDimensions, Platform, KeyboardAvoidingView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { workspaceAPI } from '../../src/services/api';
import EmptyState from '../../src/components/EmptyState';
import AppDialog, { type DialogState } from '../../src/components/AppDialog';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

type Library = { id: string; title: string; kind: 'media' | 'menu'; thumb?: string | null };

export default function WorkspacePlaylists() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { new: newParam } = useLocalSearchParams<{ new?: string }>();

  const [dialog, setDialog] = useState<DialogState>(null);
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Builder state
  const [showBuilder, setShowBuilder] = useState(false);
  const [name, setName] = useState('');
  const [library, setLibrary] = useState<Library[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [screens, setScreens] = useState<any[]>([]);
  const [pickedScreens, setPickedScreens] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [builderError, setBuilderError] = useState('');

  const load = useCallback(async () => {
    try { setLoading(true); setError(''); const res = await workspaceAPI.playlists(); setItems(res.data); }
    catch (e: any) { setError(e.response?.data?.detail || e.message || 'No se pudo cargar'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openBuilder = useCallback(async () => {
    setName(''); setSelected([]); setPickedScreens([]); setBuilderError('');
    setShowBuilder(true);
    try {
      const [mediaRes, menusRes, screensRes] = await Promise.all([
        workspaceAPI.media(), workspaceAPI.menus(), workspaceAPI.screens(),
      ]);
      const lib: Library[] = [
        ...(menusRes.data || []).map((m: any) => ({
          id: m.id, title: m.name || 'Menú', kind: 'menu' as const, thumb: null,
        })),
        ...(mediaRes.data || []).map((m: any) => ({
          id: m.id,
          title: m.filename || 'Archivo',
          kind: 'media' as const,
          thumb: (m.content_type || '').startsWith('image') ? `${API_URL}/api/player/media/${m.id}` : null,
        })),
      ];
      setLibrary(lib);
      setScreens(screensRes.data || []);
      setPickedScreens((screensRes.data || []).map((s: any) => s.id));
    } catch (e: any) {
      setBuilderError(e.response?.data?.detail || 'No se pudo cargar tu biblioteca');
    }
  }, []);

  useEffect(() => { if (newParam === '1') openBuilder(); }, [newParam, openBuilder]);

  const toggle = (id: string) =>
    setSelected(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  const toggleScreen = (id: string) =>
    setPickedScreens(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);

  const save = useCallback(async (publish: boolean) => {
    if (!name.trim()) { setBuilderError('Ponle un nombre a tu playlist.'); return; }
    if (selected.length === 0) { setBuilderError('Elige al menos un contenido.'); return; }
    if (publish && pickedScreens.length === 0) { setBuilderError('Elige al menos una pantalla para publicar.'); return; }
    setSaving(true); setBuilderError('');
    try {
      const payloadItems = selected.map(id => {
        const entry = library.find(l => l.id === id)!;
        return { type: entry.kind, ref_id: id, title: entry.title, duration: 15 };
      });
      const created = await workspaceAPI.createPlaylist({ name: name.trim(), items: payloadItems });
      if (publish) {
        await workspaceAPI.publishPlaylist(created.data.id, pickedScreens);
      }
      setShowBuilder(false);
      await load();
      setDialog({
        title: publish ? '¡Playlist publicada!' : 'Playlist guardada',
        icon: 'checkmark-circle-outline',
        message: publish
          ? `"${name.trim()}" ya se está reproduciendo en ${pickedScreens.length} pantalla(s).`
          : `"${name.trim()}" quedó como borrador. Publícala cuando quieras.`,
      });
    } catch (e: any) {
      setBuilderError(e.response?.data?.detail || e.message || 'No se pudo guardar');
    } finally { setSaving(false); }
  }, [name, selected, pickedScreens, library, load]);

  const publishExisting = useCallback(async (p: any) => {
    try {
      await workspaceAPI.publishPlaylist(p.id);
      await load();
    } catch (e: any) {
      setDialog({ title: 'No se pudo publicar', message: e.response?.data?.detail || 'Intenta de nuevo' });
    }
  }, [load]);

  return (
    <View style={sp.root}>
      <ScrollView contentContainerStyle={[sp.content, { paddingBottom: insets.bottom + 24 }]}>
        <View style={sp.header}>
          <View style={{ flex: 1 }}>
            <Text style={sp.title}>Playlists</Text>
            <Text style={sp.sub}>{items.length} playlist{items.length !== 1 ? 's' : ''}</Text>
          </View>
          {items.length > 0 && (
            <TouchableOpacity style={sp.addBtn} onPress={openBuilder} activeOpacity={0.85}>
              <Ionicons name="add" size={16} color="#fff" />
              <Text style={sp.addBtnText}>Nueva Playlist</Text>
            </TouchableOpacity>
          )}
        </View>

        {loading && <ActivityIndicator color="#0891B2" style={{ marginTop: 40 }} />}
        {error !== '' && !loading && <Text style={sp.error}>{error}</Text>}

        {!loading && items.length === 0 && !error && (
          <EmptyState
            icon="list-outline"
            title="Todavía no tienes playlists"
            text="Una playlist es la secuencia que se reproduce en tu pantalla: fotos, promos y tu menú digital, uno detrás del otro."
            primary={{ label: 'Crear Playlist', icon: 'add', onPress: openBuilder }}
            secondary={{ label: 'Subir contenido primero', icon: 'cloud-upload-outline', onPress: () => router.push('/workspace/content') }}
          />
        )}

        {items.map((p, i) => {
          const published = p.status === 'published';
          return (
            <View key={p.id || i} style={sp.card}>
              <TouchableOpacity
                style={sp.cardLeft}
                activeOpacity={0.8}
                onPress={() => router.push({ pathname: '/workspace/playlist-edit', params: { id: p.id } })}
              >
                <View style={sp.icon}><Ionicons name="list" size={18} color="#0891B2" /></View>
                <View style={{ flex: 1 }}>
                  <Text style={sp.cardName}>{p.name || 'Playlist'}</Text>
                  <Text style={sp.cardMeta}>
                    {(p.items || []).length} elemento{(p.items || []).length !== 1 ? 's' : ''}
                    {' · '}{(p.screen_ids || []).length} pantalla{(p.screen_ids || []).length !== 1 ? 's' : ''}
                  </Text>
                </View>
                <Ionicons name="create-outline" size={17} color="#94A3B8" />
              </TouchableOpacity>
              {published ? (
                <View style={[sp.badge, { backgroundColor: '#D1FAE5' }]}>
                  <Text style={{ color: '#059669', fontSize: 11, fontWeight: '700' }}>Publicada</Text>
                </View>
              ) : (
                <TouchableOpacity style={sp.publishBtn} onPress={() => publishExisting(p)} activeOpacity={0.8}>
                  <Text style={sp.publishBtnText}>Publicar</Text>
                </TouchableOpacity>
              )}
            </View>
          );
        })}
      </ScrollView>

      {/* Builder */}
      <Modal visible={showBuilder} transparent animationType="slide" onRequestClose={() => setShowBuilder(false)}>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={[sp.overlay, width > 900 && sp.overlayCentered]}
        >
          <View style={[
            sp.modal,
            width > 900 && sp.modalCentered,
            { width: Math.min(width - 24, 560), maxHeight: '92%' },
          ]}>
            <View style={sp.modalHeader}>
              <Text style={sp.modalTitle}>Nueva Playlist</Text>
              <TouchableOpacity onPress={() => setShowBuilder(false)} hitSlop={{ top: 12, right: 12, bottom: 12, left: 12 }}>
                <Ionicons name="close" size={22} color="#64748B" />
              </TouchableOpacity>
            </View>

            <ScrollView style={{ maxHeight: 460 }} keyboardShouldPersistTaps="handled">
              <Text style={sp.inputLabel}>Nombre</Text>
              <TextInput
                style={sp.input}
                value={name}
                onChangeText={setName}
                placeholder="ej. Promos de la semana"
                placeholderTextColor="#CBD5E1"
              />

              <Text style={[sp.inputLabel, { marginTop: 18 }]}>Contenido ({selected.length} seleccionado{selected.length !== 1 ? 's' : ''})</Text>
              {library.length === 0 ? (
                <TouchableOpacity
                  style={sp.libEmpty}
                  onPress={() => { setShowBuilder(false); router.push('/workspace/content'); }}
                >
                  <Ionicons name="cloud-upload-outline" size={16} color="#0891B2" />
                  <Text style={sp.libEmptyText}>Aún no tienes contenido. Toca aquí para subir fotos.</Text>
                </TouchableOpacity>
              ) : library.map(l => {
                const on = selected.includes(l.id);
                return (
                  <TouchableOpacity key={l.id} style={[sp.libRow, on && sp.libRowOn]} onPress={() => toggle(l.id)} activeOpacity={0.8}>
                    {l.thumb
                      ? <Image source={{ uri: l.thumb }} style={sp.libThumb} resizeMode="cover" />
                      : <View style={sp.libThumbFallback}>
                          <Ionicons name={l.kind === 'menu' ? 'restaurant' : 'document'} size={16} color="#0891B2" />
                        </View>}
                    <View style={{ flex: 1 }}>
                      <Text style={sp.libTitle} numberOfLines={1}>{l.title}</Text>
                      <Text style={sp.libKind}>{l.kind === 'menu' ? 'Menú digital' : 'Imagen'}</Text>
                    </View>
                    <Ionicons
                      name={on ? 'checkmark-circle' : 'ellipse-outline'}
                      size={22}
                      color={on ? '#0891B2' : '#CBD5E1'}
                    />
                  </TouchableOpacity>
                );
              })}

              <Text style={[sp.inputLabel, { marginTop: 18 }]}>Pantallas</Text>
              {screens.length === 0 ? (
                <Text style={sp.noScreens}>Todavía no tienes pantallas conectadas. Puedes guardar la playlist como borrador.</Text>
              ) : screens.map(s => {
                const on = pickedScreens.includes(s.id);
                return (
                  <TouchableOpacity key={s.id} style={[sp.libRow, on && sp.libRowOn]} onPress={() => toggleScreen(s.id)} activeOpacity={0.8}>
                    <View style={sp.libThumbFallback}><Ionicons name="tv" size={16} color="#0891B2" /></View>
                    <Text style={[sp.libTitle, { flex: 1 }]} numberOfLines={1}>{s.name}</Text>
                    <Ionicons name={on ? 'checkmark-circle' : 'ellipse-outline'} size={22} color={on ? '#0891B2' : '#CBD5E1'} />
                  </TouchableOpacity>
                );
              })}
            </ScrollView>

            {!!builderError && <Text style={sp.builderErr}>{builderError}</Text>}

            <TouchableOpacity
              style={[sp.primaryBtn, saving && { opacity: 0.6 }]}
              onPress={() => save(true)}
              disabled={saving}
              activeOpacity={0.85}
            >
              {saving ? <ActivityIndicator color="#fff" size="small" />
                : <Text style={sp.primaryBtnText}>Crear y Publicar</Text>}
            </TouchableOpacity>
            <TouchableOpacity style={sp.ghostBtn} onPress={() => save(false)} disabled={saving} activeOpacity={0.8}>
              <Text style={sp.ghostBtnText}>Guardar como borrador</Text>
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      <AppDialog state={dialog} onDismiss={() => setDialog(null)} />
    </View>
  );
}

const sp = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  content: { padding: 20, gap: 12 },
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, marginBottom: 4 },
  title: { fontSize: 22, fontWeight: '800', color: '#0F172A', marginBottom: 4 },
  sub: { fontSize: 13, color: '#64748B' },
  addBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#0891B2', paddingHorizontal: 14, paddingVertical: 11, borderRadius: 10, minHeight: 44 },
  addBtnText: { color: '#fff', fontSize: 13, fontWeight: '700' },
  error: { color: '#DC2626', fontSize: 13, padding: 16 },
  card: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 12, padding: 14, gap: 10 },
  cardLeft: { flexDirection: 'row', alignItems: 'center', gap: 12, flex: 1 },
  icon: { width: 36, height: 36, borderRadius: 10, backgroundColor: '#ECFEFF', justifyContent: 'center', alignItems: 'center' },
  cardName: { fontSize: 13.5, fontWeight: '700', color: '#0F172A' },
  cardMeta: { fontSize: 11.5, color: '#64748B', marginTop: 2 },
  badge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 20 },
  publishBtn: { backgroundColor: '#ECFEFF', borderWidth: 1, borderColor: '#CFFAFE', paddingHorizontal: 14, paddingVertical: 9, borderRadius: 10, minHeight: 40, justifyContent: 'center' },
  publishBtnText: { color: '#0E7490', fontSize: 12.5, fontWeight: '700' },

  overlay: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(15,23,42,0.45)' },
  overlayCentered: { justifyContent: 'center', alignItems: 'center' },
  modalCentered: { borderRadius: 20, paddingBottom: 22 },
  modal: { backgroundColor: '#FFFFFF', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 22, paddingBottom: 30, alignSelf: 'center' },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  modalTitle: { fontSize: 18, fontWeight: '800', color: '#0F172A' },
  inputLabel: { fontSize: 11, fontWeight: '700', color: '#64748B', letterSpacing: 0.6, textTransform: 'uppercase', marginBottom: 8 },
  input: { fontSize: 15, color: '#0F172A', backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 10, padding: 14 },
  libRow: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 12, padding: 10, marginBottom: 8, minHeight: 56 },
  libRowOn: { borderColor: '#06B6D4', backgroundColor: '#ECFEFF' },
  libThumb: { width: 48, height: 36, borderRadius: 8, backgroundColor: '#E2E8F0' },
  libThumbFallback: { width: 48, height: 36, borderRadius: 8, backgroundColor: '#CFFAFE', justifyContent: 'center', alignItems: 'center' },
  libTitle: { fontSize: 13, fontWeight: '600', color: '#0F172A' },
  libKind: { fontSize: 11, color: '#64748B', marginTop: 2 },
  libEmpty: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: '#ECFEFF', borderWidth: 1, borderColor: '#CFFAFE', borderRadius: 12, padding: 14 },
  libEmptyText: { fontSize: 12.5, color: '#0E7490', fontWeight: '600', flex: 1 },
  noScreens: { fontSize: 12.5, color: '#64748B', lineHeight: 18, marginBottom: 4 },
  builderErr: { color: '#DC2626', fontSize: 13, marginTop: 12, textAlign: 'center' },
  primaryBtn: { backgroundColor: '#0891B2', borderRadius: 12, padding: 16, alignItems: 'center', marginTop: 16 },
  primaryBtnText: { color: '#fff', fontSize: 15, fontWeight: '700' },
  ghostBtn: { alignItems: 'center', paddingVertical: 12, minHeight: 44, justifyContent: 'center' },
  ghostBtnText: { color: '#0891B2', fontSize: 13.5, fontWeight: '700' },
});
