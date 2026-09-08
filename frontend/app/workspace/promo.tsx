import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity, TextInput, Image,
  ActivityIndicator, Platform, Linking,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { workspaceAPI } from '../../src/services/api';
import AppDialog, { type DialogState } from '../../src/components/AppDialog';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const MAX_BYTES = 12 * 1024 * 1024;

type Promo = {
  id: string; name: string; kind: 'image' | 'text'; text?: string | null;
  screen_ids: string[]; seconds_remaining?: number | null;
};

const DURATIONS: { label: string; minutes: number | null }[] = [
  { label: '15 min', minutes: 15 },
  { label: '1 hora', minutes: 60 },
  { label: '4 horas', minutes: 240 },
  { label: 'Hasta apagarla', minutes: null },
];

function remaining(seconds?: number | null): string {
  if (seconds === null || seconds === undefined) return 'hasta que la apagues';
  if (seconds < 60) return `${seconds}s restantes`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min restantes`;
  return `${Math.round(seconds / 3600)} h restantes`;
}

export default function WorkspacePromo() {
  const insets = useSafeAreaInsets();
  const [kind, setKind] = useState<'text' | 'image'>('text');
  const [text, setText] = useState('');
  const [subtitle, setSubtitle] = useState('');
  const [minutes, setMinutes] = useState<number | null>(60);
  const [library, setLibrary] = useState<any[]>([]);
  const [pickedMedia, setPickedMedia] = useState<string | null>(null);
  const [active, setActive] = useState<Promo[]>([]);
  const [screensCount, setScreensCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [launching, setLaunching] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dialog, setDialog] = useState<DialogState>(null);

  const load = useCallback(async () => {
    try {
      const [promos, media, screens] = await Promise.all([
        workspaceAPI.activePromos(), workspaceAPI.media(), workspaceAPI.screens(),
      ]);
      setActive(promos.data || []);
      setLibrary((media.data || []).filter((m: any) => (m.content_type || '').startsWith('image')));
      setScreensCount((screens.data || []).length);
    } catch (e: any) {
      setDialog({ title: 'No se pudo cargar', message: e.response?.data?.detail || e.message });
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const uploadNewPhoto = useCallback(async () => {
    if (Platform.OS !== 'web') {
      const current = await ImagePicker.getMediaLibraryPermissionsAsync();
      let status = current.status; let canAskAgain = current.canAskAgain;
      if (status !== 'granted' && canAskAgain) {
        const asked = await ImagePicker.requestMediaLibraryPermissionsAsync();
        status = asked.status; canAskAgain = asked.canAskAgain;
      }
      if (status !== 'granted') {
        setDialog({
          title: 'Permiso necesario',
          message: 'Necesitamos acceso a tus fotos para usar una imagen en la promo.',
          options: canAskAgain
            ? [{ label: 'Entendido', primary: true }]
            : [{ label: 'Abrir Ajustes', primary: true, onPress: () => Linking.openSettings() }, { label: 'Cancelar' }],
        });
        return;
      }
    }
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], base64: true, quality: 0.9 });
    if (res.canceled || !res.assets?.length) return;
    const asset = res.assets[0];
    if (!asset.base64) { setDialog({ title: 'No pudimos leer la foto' }); return; }
    if (asset.fileSize && asset.fileSize > MAX_BYTES) {
      setDialog({ title: 'Foto muy grande', message: 'Usa una imagen de menos de 12 MB.' });
      return;
    }
    setUploading(true);
    try {
      const up = await workspaceAPI.uploadMedia({
        filename: asset.fileName || `promo-${Date.now()}.jpg`,
        content_type: asset.mimeType || 'image/jpeg',
        data: asset.base64,
      });
      await load();
      setPickedMedia(up.data.id);
      setKind('image');
    } catch (e: any) {
      setDialog({ title: 'No se pudo subir', message: e.response?.data?.detail || e.message });
    } finally { setUploading(false); }
  }, [load]);

  const launch = useCallback(async () => {
    if (screensCount === 0) {
      setDialog({ title: 'Conecta una pantalla', message: 'Necesitas al menos una pantalla para lanzar una promo.' });
      return;
    }
    if (kind === 'text' && text.trim().length < 2) {
      setDialog({ title: 'Escribe el mensaje', message: 'Por ejemplo: 2x1 en pizzas hoy.' });
      return;
    }
    if (kind === 'image' && !pickedMedia) {
      setDialog({ title: 'Elige una foto', message: 'Selecciona una imagen de tu biblioteca o sube una nueva.' });
      return;
    }
    setLaunching(true);
    try {
      const res = await workspaceAPI.launchPromo({
        kind,
        text: kind === 'text' ? text.trim() : undefined,
        subtitle: kind === 'text' ? subtitle.trim() || undefined : undefined,
        media_id: kind === 'image' ? pickedMedia! : undefined,
        duration_minutes: minutes,
      });
      await load();
      setText(''); setSubtitle(''); setPickedMedia(null);
      setDialog({
        title: '¡Promo en el aire!',
        icon: 'megaphone',
        message: `Se está mostrando en ${res.data.screens} pantalla(s) · ${remaining(res.data.seconds_remaining)}.`,
      });
    } catch (e: any) {
      setDialog({ title: 'No se pudo lanzar', message: e.response?.data?.detail || e.message });
    } finally { setLaunching(false); }
  }, [kind, text, subtitle, pickedMedia, minutes, screensCount, load]);

  const stop = (promo: Promo) => {
    setDialog({
      title: '¿Apagar la promo?',
      message: 'Tus pantallas volverán al contenido normal enseguida.',
      icon: 'power-outline',
      options: [
        { label: 'Apagar promo', destructive: true, onPress: async () => {
          try { await workspaceAPI.stopPromo(promo.id); await load(); }
          catch (e: any) { setDialog({ title: 'No se pudo apagar', message: e.response?.data?.detail }); }
        }},
        { label: 'Dejarla' },
      ],
    });
  };

  return (
    <View style={pr.root}>
      <ScrollView contentContainerStyle={[pr.content, { paddingBottom: insets.bottom + 32 }]} keyboardShouldPersistTaps="handled">
        <View>
          <Text style={pr.title}>Promo Instantánea</Text>
          <Text style={pr.sub}>Lanza una promoción a todas tus pantallas con un solo toque</Text>
        </View>

        {loading && <ActivityIndicator color="#0891B2" style={{ marginTop: 30 }} />}

        {active.map(promo => (
          <View key={promo.id} style={pr.liveCard}>
            <View style={pr.liveTop}>
              <View style={pr.liveDot} />
              <Text style={pr.liveLabel}>PROMO EN EL AIRE</Text>
            </View>
            <Text style={pr.liveName}>{promo.text || promo.name}</Text>
            <Text style={pr.liveMeta}>
              {promo.screen_ids.length} pantalla{promo.screen_ids.length !== 1 ? 's' : ''} · {remaining(promo.seconds_remaining)}
            </Text>
            <TouchableOpacity style={pr.stopBtn} onPress={() => stop(promo)} activeOpacity={0.85}>
              <Ionicons name="power" size={16} color="#DC2626" />
              <Text style={pr.stopText}>Apagar y volver al contenido normal</Text>
            </TouchableOpacity>
          </View>
        ))}

        {!loading && (
          <>
            <View style={pr.kindRow}>
              <TouchableOpacity style={[pr.kindBtn, kind === 'text' && pr.kindBtnOn]} onPress={() => setKind('text')} activeOpacity={0.8}>
                <Ionicons name="text-outline" size={18} color={kind === 'text' ? '#0891B2' : '#94A3B8'} />
                <Text style={[pr.kindText, kind === 'text' && pr.kindTextOn]}>Mensaje</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[pr.kindBtn, kind === 'image' && pr.kindBtnOn]} onPress={() => setKind('image')} activeOpacity={0.8}>
                <Ionicons name="image-outline" size={18} color={kind === 'image' ? '#0891B2' : '#94A3B8'} />
                <Text style={[pr.kindText, kind === 'image' && pr.kindTextOn]}>Foto</Text>
              </TouchableOpacity>
            </View>

            {kind === 'text' ? (
              <View style={pr.card}>
                <Text style={pr.label}>Mensaje grande</Text>
                <TextInput
                  style={[pr.input, pr.inputBig]}
                  value={text}
                  onChangeText={setText}
                  placeholder="2x1 EN PIZZAS HOY"
                  placeholderTextColor="#CBD5E1"
                  maxLength={60}
                />
                <Text style={[pr.label, { marginTop: 14 }]}>Segunda línea (opcional)</Text>
                <TextInput
                  style={pr.input}
                  value={subtitle}
                  onChangeText={setSubtitle}
                  placeholder="Solo hasta las 9 pm"
                  placeholderTextColor="#CBD5E1"
                  maxLength={80}
                />
                <View style={pr.preview}>
                  <Text style={pr.previewTitle} numberOfLines={2}>{(text || 'TU MENSAJE AQUÍ').toUpperCase()}</Text>
                  {!!subtitle && <Text style={pr.previewSub} numberOfLines={1}>{subtitle}</Text>}
                </View>
              </View>
            ) : (
              <View style={pr.card}>
                <View style={pr.libHeader}>
                  <Text style={pr.label}>Elige una foto</Text>
                  <TouchableOpacity style={pr.uploadBtn} onPress={uploadNewPhoto} disabled={uploading} activeOpacity={0.8}>
                    {uploading
                      ? <ActivityIndicator size="small" color="#0891B2" />
                      : <><Ionicons name="cloud-upload-outline" size={15} color="#0891B2" />
                          <Text style={pr.uploadText}>Subir nueva</Text></>}
                  </TouchableOpacity>
                </View>
                {library.length === 0 ? (
                  <Text style={pr.emptyLib}>Tu biblioteca no tiene fotos todavía. Sube una para usarla en la promo.</Text>
                ) : (
                  <View style={pr.thumbGrid}>
                    {library.map(m => {
                      const on = pickedMedia === m.id;
                      return (
                        <TouchableOpacity key={m.id} onPress={() => setPickedMedia(m.id)} activeOpacity={0.85}>
                          <Image
                            source={{ uri: `${API_URL}/api/player/media/${m.id}` }}
                            style={[pr.thumb, on && pr.thumbOn]}
                            resizeMode="cover"
                          />
                          {on && (
                            <View style={pr.thumbCheck}>
                              <Ionicons name="checkmark-circle" size={20} color="#0891B2" />
                            </View>
                          )}
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                )}
              </View>
            )}

            <Text style={[pr.label, { marginTop: 20 }]}>¿Cuánto dura?</Text>
            <View style={pr.durRow}>
              {DURATIONS.map(d => {
                const on = minutes === d.minutes;
                return (
                  <TouchableOpacity
                    key={d.label}
                    style={[pr.dur, on && pr.durOn]}
                    onPress={() => setMinutes(d.minutes)}
                    activeOpacity={0.8}
                  >
                    <Text style={[pr.durText, on && pr.durTextOn]}>{d.label}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            <TouchableOpacity
              style={[pr.launchBtn, launching && { opacity: 0.65 }]}
              onPress={launch}
              disabled={launching}
              activeOpacity={0.85}
            >
              {launching ? <ActivityIndicator color="#fff" /> : (
                <>
                  <Ionicons name="megaphone" size={19} color="#FFFFFF" />
                  <Text style={pr.launchText}>
                    Lanzar a {screensCount} pantalla{screensCount !== 1 ? 's' : ''}
                  </Text>
                </>
              )}
            </TouchableOpacity>

            <TouchableOpacity style={pr.linkBtn} onPress={() => router.push('/workspace')} activeOpacity={0.8}>
              <Text style={pr.linkText}>Ver mis pantallas en vivo →</Text>
            </TouchableOpacity>
          </>
        )}
      </ScrollView>

      <AppDialog state={dialog} onDismiss={() => setDialog(null)} />
    </View>
  );
}

const pr = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  content: { padding: 20, gap: 6 },
  title: { fontSize: 22, fontWeight: '800', color: '#0F172A', marginBottom: 4 },
  sub: { fontSize: 13, color: '#64748B', marginBottom: 12, lineHeight: 18 },
  liveCard: { backgroundColor: '#0F172A', borderRadius: 16, padding: 18, gap: 6, marginBottom: 10 },
  liveTop: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  liveDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#22C55E' },
  liveLabel: { fontSize: 10, fontWeight: '800', color: '#67E8F9', letterSpacing: 1 },
  liveName: { fontSize: 18, fontWeight: '800', color: '#FFFFFF' },
  liveMeta: { fontSize: 12, color: '#94A3B8' },
  stopBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: '#FEF2F2', borderRadius: 12, paddingVertical: 13, marginTop: 8, minHeight: 46,
  },
  stopText: { fontSize: 13.5, fontWeight: '700', color: '#DC2626' },
  kindRow: { flexDirection: 'row', gap: 10, marginBottom: 12 },
  kindBtn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: '#FFFFFF', borderWidth: 1.5, borderColor: '#E2E8F0', borderRadius: 12,
    paddingVertical: 14, minHeight: 48,
  },
  kindBtnOn: { borderColor: '#06B6D4', backgroundColor: '#ECFEFF' },
  kindText: { fontSize: 14, fontWeight: '700', color: '#64748B' },
  kindTextOn: { color: '#0E7490' },
  card: { backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 14, padding: 16 },
  label: { fontSize: 11, fontWeight: '700', color: '#64748B', letterSpacing: 0.6, textTransform: 'uppercase', marginBottom: 8 },
  input: {
    fontSize: 15, color: '#0F172A', backgroundColor: '#F8FAFC', borderWidth: 1,
    borderColor: '#E2E8F0', borderRadius: 10, padding: 14,
    ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : null),
  },
  inputBig: { fontSize: 18, fontWeight: '800' },
  preview: { backgroundColor: '#0F172A', borderRadius: 12, padding: 22, marginTop: 16, alignItems: 'center', gap: 8 },
  previewTitle: { fontSize: 22, fontWeight: '900', color: '#FFFFFF', textAlign: 'center' },
  previewSub: { fontSize: 13, fontWeight: '700', color: '#22D3EE', textAlign: 'center' },
  libHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  uploadBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 8, minHeight: 40 },
  uploadText: { fontSize: 12.5, fontWeight: '700', color: '#0891B2' },
  emptyLib: { fontSize: 12.5, color: '#94A3B8', lineHeight: 18 },
  thumbGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  thumb: { width: 96, height: 72, borderRadius: 10, backgroundColor: '#E2E8F0', borderWidth: 2, borderColor: 'transparent' },
  thumbOn: { borderColor: '#06B6D4' },
  thumbCheck: { position: 'absolute', top: 4, right: 4, backgroundColor: '#FFFFFF', borderRadius: 10 },
  durRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  dur: {
    backgroundColor: '#FFFFFF', borderWidth: 1.5, borderColor: '#E2E8F0', borderRadius: 20,
    paddingHorizontal: 16, paddingVertical: 11, minHeight: 44, justifyContent: 'center',
  },
  durOn: { borderColor: '#06B6D4', backgroundColor: '#ECFEFF' },
  durText: { fontSize: 13, fontWeight: '700', color: '#64748B' },
  durTextOn: { color: '#0E7490' },
  launchBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10,
    backgroundColor: '#0891B2', borderRadius: 16, paddingVertical: 18, marginTop: 22,
  },
  launchText: { color: '#FFFFFF', fontSize: 16, fontWeight: '800' },
  linkBtn: { alignItems: 'center', paddingVertical: 14, minHeight: 44 },
  linkText: { fontSize: 13, fontWeight: '700', color: '#0891B2' },
});
