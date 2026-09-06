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

export default function WorkspaceAjustes() {
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
      <Text style={st.title}>Ajustes</Text>
      {loading && <ActivityIndicator color="#0891B2" style={{ marginTop: 40 }} />}
      {error !== '' && !loading && <Text style={st.error}>{error}</Text>}

      {!loading && (
        <>
          {/* Organización */}
          {org && (
            <View style={st.section}>
              <Text style={st.sectionTitle}>Organización</Text>
              <InfoRow label="Nombre" value={org.name} />
              <InfoRow label="Identificador" value={org.slug} />
              <InfoRow label="Estado" value={org.status} />
              <InfoRow label="Creado" value={fmtDate(org.created_at)} />
            </View>
          )}

          {/* Profile */}
          <View style={st.section}>
            <Text style={st.sectionTitle}>Tu Perfil</Text>
            <InfoRow label="Nombre" value={user?.name || ''} />
            <InfoRow label="Correo" value={user?.email || ''} />
            <InfoRow label="Rol" value={(user?.rbac_role || user?.role || '').replace(/_/g, ' ')} />
          </View>

          <View style={st.contactNote}>
            <Ionicons name="information-circle-outline" size={16} color="#64748B" />
            <Text style={st.contactText}>
              Para actualizar los datos de tu organización o cambiar tu contraseña, escribe a{' '}
              <Text style={{ color: '#0891B2' }}>support@mediadview.com</Text>
            </Text>
          </View>
        </>
      )}
    </ScrollView>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' }, content: { padding: 20, gap: 16 },
  title: { fontSize: 22, fontWeight: '800', color: '#0F172A', marginBottom: 4 },
  error: { color: '#DC2626', fontSize: 13, padding: 16 },
  section: { backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 14, padding: 16 },
  sectionTitle: { fontSize: 13, fontWeight: '700', color: '#64748B', marginBottom: 12, letterSpacing: 0.5 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#F1F5F9' },
  rowLabel: { fontSize: 13, color: '#64748B', fontWeight: '500' }, rowValue: { fontSize: 13, color: '#334155', fontWeight: '600' },
  contactNote: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 12, padding: 14 },
  contactText: { fontSize: 13, color: '#64748B', flex: 1, lineHeight: 18 },
});
