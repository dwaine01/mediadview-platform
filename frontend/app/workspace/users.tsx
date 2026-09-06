import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, ScrollView, StyleSheet, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { workspaceAPI } from '../../src/services/api';
import type { WorkspaceUser } from '../../src/types';

export default function WorkspaceUsers() {
  const insets = useSafeAreaInsets();
  const [users, setUsers] = useState<WorkspaceUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try { setLoading(true); setError(''); const res = await workspaceAPI.users(); setUsers(res.data); }
    catch (e: any) { setError(e.response?.data?.detail || e.message || 'Failed to load'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);
  const fmtDate = (d?: string) => d ? new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '';

  return (
    <ScrollView style={su.root} contentContainerStyle={[su.content, { paddingBottom: insets.bottom + 24 }]}>
      <Text style={su.title}>Equipo</Text>
      <Text style={su.sub}>{users.length} miembro{users.length !== 1 ? 's' : ''} del equipo</Text>
      {loading && <ActivityIndicator color="#0891B2" style={{ marginTop: 40 }} />}
      {error !== '' && !loading && <Text style={su.error}>{error}</Text>}
      {!loading && users.length === 0 && !error && (
        <View style={su.empty}><Ionicons name="people-outline" size={40} color="#CBD5E1" />
          <Text style={su.emptyTitle}>Todavía no hay miembros del equipo</Text><Text style={su.emptyText}>Invita a tu equipo a colaborar en tu workspace.</Text>
        </View>
      )}
      {users.map((u, i) => {
        const initial = (u.name || u.email || 'U')[0].toUpperCase();
        return (
          <View key={u.id || i} style={su.card}>
            <View style={su.avatar}><Text style={su.avatarText}>{initial}</Text></View>
            <View style={{ flex: 1 }}>
              <Text style={su.name}>{u.name || '—'}</Text>
              <Text style={su.email}>{u.email}</Text>
            </View>
            <View>
              <View style={su.roleBadge}><Text style={su.roleText}>{(u.rbac_role || u.role || '').replace(/_/g, ' ')}</Text></View>
              <Text style={su.joinedDate}>{fmtDate(u.created_at)}</Text>
            </View>
          </View>
        );
      })}
    </ScrollView>
  );
}

const su = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' }, content: { padding: 20, gap: 12 },
  title: { fontSize: 22, fontWeight: '800', color: '#0F172A', marginBottom: 4 }, sub: { fontSize: 13, color: '#64748B', marginBottom: 8 },
  error: { color: '#DC2626', fontSize: 13, padding: 16 },
  empty: { alignItems: 'center', paddingVertical: 60, gap: 12 },
  emptyTitle: { fontSize: 16, fontWeight: '700', color: '#64748B' }, emptyText: { fontSize: 13, color: '#64748B', textAlign: 'center', maxWidth: 280 },
  card: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 12, padding: 14 },
  avatar: { width: 40, height: 40, borderRadius: 12, backgroundColor: '#CFFAFE', justifyContent: 'center', alignItems: 'center' },
  avatarText: { fontSize: 16, fontWeight: '700', color: '#0891B2' },
  name: { fontSize: 14, fontWeight: '600', color: '#0F172A' }, email: { fontSize: 11, color: '#64748B', marginTop: 2 },
  roleBadge: { backgroundColor: '#F1F5F9', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 12, alignSelf: 'flex-end' },
  roleText: { fontSize: 10, color: '#64748B', fontWeight: '600' },
  joinedDate: { fontSize: 10, color: '#94A3B8', textAlign: 'right', marginTop: 3 },
});
