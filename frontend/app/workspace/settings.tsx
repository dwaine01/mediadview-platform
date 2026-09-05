import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, ScrollView, StyleSheet, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { workspaceAPI } from '../../src/services/api';
import { useAuthStore } from '../../src/store/authStore';
import type { WorkspaceContext } from '../../src/types';

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={st.row}>
      <Text style={st.rowLabel}>{label}</Text>
      <Text style={st.rowValue}>{value || '—'}</Text>
    </View>
  );
}

export default function WorkspaceSettings() {
  const insets = useSafeAreaInsets();
  const { user } = useAuthStore();
  const [ctx, setCtx] = useState<WorkspaceContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try { setLoading(true); setError(''); const res = await workspaceAPI.context(); setCtx(res.data); }
    catch (e: any) { setError(e.response?.data?.detail || e.message || 'Failed to load'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const org = ctx?.organization;
  const fmtDate = (d?: string) => d ? new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—';

  return (
    <ScrollView style={st.root} contentContainerStyle={[st.content, { paddingBottom: insets.bottom + 24 }]}>
      <Text style={st.title}>Settings</Text>
      {loading && <ActivityIndicator color="#6366F1" style={{ marginTop: 40 }} />}
      {error !== '' && !loading && <Text style={st.error}>{error}</Text>}

      {!loading && (
        <>
          {/* Organization */}
          {org && (
            <View style={st.section}>
              <Text style={st.sectionTitle}>Organization</Text>
              <InfoRow label="Name" value={org.name} />
              <InfoRow label="Slug" value={org.slug} />
              <InfoRow label="Status" value={org.status} />
              <InfoRow label="Created" value={fmtDate(org.created_at)} />
            </View>
          )}

          {/* Profile */}
          <View style={st.section}>
            <Text style={st.sectionTitle}>Your Profile</Text>
            <InfoRow label="Name" value={user?.name || ''} />
            <InfoRow label="Email" value={user?.email || ''} />
            <InfoRow label="Role" value={(user?.rbac_role || user?.role || '').replace(/_/g, ' ')} />
          </View>

          <View style={st.contactNote}>
            <Ionicons name="information-circle-outline" size={16} color="#64748B" />
            <Text style={st.contactText}>
              To update organization details or change your password, contact{' '}
              <Text style={{ color: '#818CF8' }}>support@mediadview.com</Text>
            </Text>
          </View>
        </>
      )}
    </ScrollView>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0B0F1A' }, content: { padding: 20, gap: 16 },
  title: { fontSize: 22, fontWeight: '800', color: '#F1F5F9', marginBottom: 4 },
  error: { color: '#F87171', fontSize: 13, padding: 16 },
  section: { backgroundColor: '#111827', borderWidth: 1, borderColor: '#1E293B', borderRadius: 14, padding: 16 },
  sectionTitle: { fontSize: 13, fontWeight: '700', color: '#94A3B8', marginBottom: 12, letterSpacing: 0.5 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#1A2234' },
  rowLabel: { fontSize: 13, color: '#64748B', fontWeight: '500' }, rowValue: { fontSize: 13, color: '#D1D5DB', fontWeight: '600' },
  contactNote: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, backgroundColor: '#111827', borderWidth: 1, borderColor: '#1E293B', borderRadius: 12, padding: 14 },
  contactText: { fontSize: 13, color: '#64748B', flex: 1, lineHeight: 18 },
});
