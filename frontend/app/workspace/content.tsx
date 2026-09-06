import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, ActivityIndicator, TouchableOpacity,
  Image, Platform, Linking,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as ImagePicker from 'expo-image-picker';
import { useRouter } from 'expo-router';
import { workspaceAPI } from '../../src/services/api';
import EmptyState from '../../src/components/EmptyState';
import AppDialog, { type DialogState } from '../../src/components/AppDialog';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const MAX_BYTES = 12 * 1024 * 1024;

function formatSize(bytes?: number) {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1048576).toFixed(1)}MB`;
}

export default function WorkspaceContent() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [media, setMedia] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [dialog, setDialog] = useState<DialogState>(null);
  const [progress, setProgress] = useState('');

  const load = useCallback(async () => {
    try {
      setLoading(true); setError('');
      const res = await workspaceAPI.media(); setMedia(res.data);
    } catch (e: any) { setError(e.response?.data?.detail || e.message || 'No se pudo cargar'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const pickAndUpload = useCallback(async () => {
    if (uploading) return;
    // Permission is requested only after the user taps Upload
    if (Platform.OS !== 'web') {
      const current = await ImagePicker.getMediaLibraryPermissionsAsync();
      let status = current.status;
      let canAskAgain = current.canAskAgain;
      if (status !== 'granted' && canAskAgain) {
        const asked = await ImagePicker.requestMediaLibraryPermissionsAsync();
        status = asked.status; canAskAgain = asked.canAskAgain;
      }
      if (status !== 'granted') {
        setDialog({
          title: 'Permiso necesario',
          message: 'Para subir contenido necesitamos acceso a tus fotos.',
          icon: 'images-outline',
          options: canAskAgain
            ? [{ label: 'Entendido', primary: true }]
            : [{ label: 'Abrir Ajustes', primary: true, onPress: () => Linking.openSettings() },
               { label: 'Cancelar' }],
        });
        return;
      }
    }

    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      base64: true,
      quality: 0.9,
      allowsMultipleSelection: true,
      selectionLimit: 10,
    });
    if (res.canceled || !res.assets?.length) return;

    setUploading(true);
    let ok = 0; const failures: string[] = [];
    for (let i = 0; i < res.assets.length; i++) {
      const asset = res.assets[i];
      setProgress(`Subiendo ${i + 1} de ${res.assets.length}…`);
      const name = asset.fileName || `contenido-${Date.now()}.jpg`;
      if (!asset.base64) { failures.push(name); continue; }
      if (asset.fileSize && asset.fileSize > MAX_BYTES) {
        failures.push(`${name} (más de 12 MB)`); continue;
      }
      try {
        await workspaceAPI.uploadMedia({
          filename: name,
          content_type: asset.mimeType || 'image/jpeg',
          data: asset.base64,
        });
        ok++;
      } catch (e: any) {
        failures.push(`${name} — ${e.response?.data?.detail || 'error'}`);
      }
    }
    setUploading(false); setProgress('');
    await load();
    if (failures.length) {
      setDialog({
        title: ok ? 'Subida parcial' : 'No se pudo subir',
        message: `${ok} archivo(s) subidos.\n\nProblemas:\n${failures.join('\n')}`,
      });
    }
  }, [uploading, load]);

  const thumb = (m: any) => {
    if (!(m.content_type || '').startsWith('image')) return null;
    return `${API_URL}/api/player/media/${m.id}`;
  };

  return (
    <ScrollView style={sc.root} contentContainerStyle={[sc.content, { paddingBottom: insets.bottom + 24 }]}>
      <View style={sc.header}>
        <View style={{ flex: 1 }}>
          <Text style={sc.pageTitle}>Contenido / Medios</Text>
          <Text style={sc.pageSub}>{media.length} archivo{media.length !== 1 ? 's' : ''} en tu biblioteca</Text>
        </View>
        {media.length > 0 && (
          <TouchableOpacity style={sc.addBtn} onPress={pickAndUpload} disabled={uploading} activeOpacity={0.85}>
            {uploading
              ? <ActivityIndicator color="#fff" size="small" />
              : <><Ionicons name="cloud-upload-outline" size={16} color="#fff" />
                  <Text style={sc.addBtnText}>Subir Contenido</Text></>}
          </TouchableOpacity>
        )}
      </View>

      {!!progress && <Text style={sc.progress}>{progress}</Text>}
      {loading && <ActivityIndicator color="#0891B2" style={{ marginTop: 40 }} />}
      {error !== '' && !loading && <Text style={sc.error}>{error}</Text>}

      {!loading && media.length === 0 && !error && (
        <EmptyState
          icon="images-outline"
          title="Tu biblioteca está vacía"
          text="Sube fotos de tus productos, promociones o anuncios. Después las agrupas en una playlist y las envías a tus pantallas."
          primary={{
            label: uploading ? 'Subiendo…' : 'Subir Contenido',
            icon: 'cloud-upload-outline',
            onPress: pickAndUpload,
          }}
          secondary={{ label: 'O crea un menú digital', icon: 'restaurant-outline', onPress: () => router.push('/workspace/menus') }}
        />
      )}

      {media.map((m, i) => {
        const mime = (m.content_type || m.mime_type || '').split('/').pop()?.toUpperCase() || '?';
        const isImg = (m.content_type || '').startsWith('image');
        const uri = thumb(m);
        return (
          <View key={m.id || i} style={sc.card}>
            <View style={sc.cardLeft}>
              {uri ? (
                <Image source={{ uri }} style={sc.thumb} resizeMode="cover" />
              ) : (
                <View style={[sc.mimeBox, { backgroundColor: isImg ? '#CFFAFE22' : '#ECFEFF44' }]}>
                  <Ionicons name={isImg ? 'image' : 'videocam'} size={20} color={isImg ? '#0891B2' : '#06B6D4'} />
                </View>
              )}
              <View style={{ flex: 1 }}>
                <Text style={sc.fileName} numberOfLines={1}>{m.filename || m.name || 'Archivo'}</Text>
                <Text style={sc.fileMeta}>{mime}{m.size || m.size_bytes || m.file_size ? ' · ' + formatSize(m.size || m.size_bytes || m.file_size) : ''}</Text>
              </View>
            </View>
            <Text style={sc.date}>{m.created_at ? new Date(m.created_at).toLocaleDateString('es-ES', { month: 'short', day: 'numeric' }) : ''}</Text>
          </View>
        );
      })}

      {media.length > 0 && (
        <TouchableOpacity style={sc.nextStep} onPress={() => router.push('/workspace/playlists')} activeOpacity={0.8}>
          <Ionicons name="list-outline" size={16} color="#0891B2" />
          <Text style={sc.nextStepText}>Siguiente paso: crear una playlist con este contenido →</Text>
        </TouchableOpacity>
      )}

      <AppDialog state={dialog} onDismiss={() => setDialog(null)} />
    </ScrollView>
  );
}

const sc = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  content: { padding: 20, gap: 12 },
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, marginBottom: 4 },
  pageTitle: { fontSize: 22, fontWeight: '800', color: '#0F172A', marginBottom: 4 },
  pageSub: { fontSize: 13, color: '#64748B' },
  addBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#0891B2',
    paddingHorizontal: 14, paddingVertical: 11, borderRadius: 10, minHeight: 44,
  },
  addBtnText: { color: '#fff', fontSize: 13, fontWeight: '700' },
  progress: { fontSize: 12.5, color: '#0891B2', fontWeight: '600' },
  error: { color: '#DC2626', fontSize: 13, padding: 16 },
  card: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 12, padding: 14, gap: 12 },
  cardLeft: { flexDirection: 'row', alignItems: 'center', gap: 12, flex: 1 },
  mimeBox: { width: 40, height: 40, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  thumb: { width: 52, height: 40, borderRadius: 8, backgroundColor: '#E2E8F0' },
  fileName: { fontSize: 13, fontWeight: '600', color: '#0F172A' },
  fileMeta: { fontSize: 11, color: '#64748B', marginTop: 2 },
  date: { fontSize: 11, color: '#94A3B8' },
  nextStep: {
    flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: '#ECFEFF',
    borderWidth: 1, borderColor: '#CFFAFE', borderRadius: 12, padding: 14, marginTop: 4,
  },
  nextStepText: { fontSize: 12.5, color: '#0E7490', fontWeight: '600', flex: 1 },
});
