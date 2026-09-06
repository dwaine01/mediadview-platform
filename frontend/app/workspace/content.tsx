import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, ScrollView, StyleSheet, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { workspaceAPI } from '../../src/services/api';

function formatSize(bytes?: number) {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1048576).toFixed(1)}MB`;
}

export default function WorkspaceContent() {
  const insets = useSafeAreaInsets();
  const [media, setMedia] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try { setLoading(true); setError('');
      const res = await workspaceAPI.media(); setMedia(res.data);
    } catch (e: any) { setError(e.response?.data?.detail || e.message || 'Failed to load'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <ScrollView style={sc.root} contentContainerStyle={[sc.content, { paddingBottom: insets.bottom + 24 }]}>
      <Text style={sc.pageTitle}>Contenido / Medios</Text>
      <Text style={sc.pageSub}>{media.length} archivo{media.length !== 1 ? 's' : ''} en tu biblioteca</Text>

      {loading && <ActivityIndicator color="#0891B2" style={{ marginTop: 40 }} />}
      {error !== '' && !loading && <Text style={sc.error}>{error}</Text>}

      {!loading && media.length === 0 && !error && (
        <View style={sc.empty}>
          <Ionicons name="images-outline" size={40} color="#CBD5E1" />
          <Text style={sc.emptyTitle}>Tu biblioteca de medios está vacía</Text>
          <Text style={sc.emptyText}>Sube imágenes o videos para empezar a crear playlists y programar contenido.</Text>
        </View>
      )}

      {media.map((m, i) => {
        const mime = (m.content_type || m.mime_type || '').split('/').pop()?.toUpperCase() || '?';
        const isImg = (m.content_type || '').startsWith('image');
        return (
          <View key={m.id || i} style={sc.card}>
            <View style={sc.cardLeft}>
              <View style={[sc.mimeBox, { backgroundColor: isImg ? '#CFFAFE22' : '#ECFEFF44' }]}>
                <Ionicons name={isImg ? 'image' : 'videocam'} size={20} color={isImg ? '#0891B2' : '#06B6D4'} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={sc.fileName} numberOfLines={1}>{m.filename || m.name || 'File'}</Text>
                <Text style={sc.fileMeta}>{mime}{m.size_bytes || m.file_size ? ' · ' + formatSize(m.size_bytes || m.file_size) : ''}</Text>
              </View>
            </View>
            <Text style={sc.date}>{m.created_at ? new Date(m.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : ''}</Text>
          </View>
        );
      })}
    </ScrollView>
  );
}

const sc = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  content: { padding: 20, gap: 12 },
  pageTitle: { fontSize: 22, fontWeight: '800', color: '#0F172A', marginBottom: 4 },
  pageSub: { fontSize: 13, color: '#64748B', marginBottom: 8 },
  error: { color: '#DC2626', fontSize: 13, padding: 16 },
  empty: { alignItems: 'center', paddingVertical: 60, gap: 12 },
  emptyTitle: { fontSize: 16, fontWeight: '700', color: '#64748B' },
  emptyText: { fontSize: 13, color: '#64748B', textAlign: 'center', maxWidth: 280 },
  card: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 12, padding: 14, gap: 12 },
  cardLeft: { flexDirection: 'row', alignItems: 'center', gap: 12, flex: 1 },
  mimeBox: { width: 40, height: 40, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  fileName: { fontSize: 13, fontWeight: '600', color: '#0F172A' },
  fileMeta: { fontSize: 11, color: '#64748B', marginTop: 2 },
  date: { fontSize: 11, color: '#94A3B8' },
});
