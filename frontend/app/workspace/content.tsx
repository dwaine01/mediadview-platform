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
      <Text style={sc.pageTitle}>Content / Media</Text>
      <Text style={sc.pageSub}>{media.length} file{media.length !== 1 ? 's' : ''} in your media library</Text>

      {loading && <ActivityIndicator color="#6366F1" style={{ marginTop: 40 }} />}
      {error !== '' && !loading && <Text style={sc.error}>{error}</Text>}

      {!loading && media.length === 0 && !error && (
        <View style={sc.empty}>
          <Ionicons name="images-outline" size={40} color="#374151" />
          <Text style={sc.emptyTitle}>Media library is empty</Text>
          <Text style={sc.emptyText}>Upload images or videos to start creating playlists and content schedules.</Text>
        </View>
      )}

      {media.map((m, i) => {
        const mime = (m.content_type || m.mime_type || '').split('/').pop()?.toUpperCase() || '?';
        const isImg = (m.content_type || '').startsWith('image');
        return (
          <View key={m.id || i} style={sc.card}>
            <View style={sc.cardLeft}>
              <View style={[sc.mimeBox, { backgroundColor: isImg ? '#312E8122' : '#1E3A5F44' }]}>
                <Ionicons name={isImg ? 'image' : 'videocam'} size={20} color={isImg ? '#818CF8' : '#22D3EE'} />
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
  root: { flex: 1, backgroundColor: '#0B0F1A' },
  content: { padding: 20, gap: 12 },
  pageTitle: { fontSize: 22, fontWeight: '800', color: '#F1F5F9', marginBottom: 4 },
  pageSub: { fontSize: 13, color: '#64748B', marginBottom: 8 },
  error: { color: '#F87171', fontSize: 13, padding: 16 },
  empty: { alignItems: 'center', paddingVertical: 60, gap: 12 },
  emptyTitle: { fontSize: 16, fontWeight: '700', color: '#9CA3AF' },
  emptyText: { fontSize: 13, color: '#64748B', textAlign: 'center', maxWidth: 280 },
  card: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#111827', borderWidth: 1, borderColor: '#1E293B', borderRadius: 12, padding: 14, gap: 12 },
  cardLeft: { flexDirection: 'row', alignItems: 'center', gap: 12, flex: 1 },
  mimeBox: { width: 40, height: 40, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  fileName: { fontSize: 13, fontWeight: '600', color: '#F1F5F9' },
  fileMeta: { fontSize: 11, color: '#64748B', marginTop: 2 },
  date: { fontSize: 11, color: '#4B5563' },
});
