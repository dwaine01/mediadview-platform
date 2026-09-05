import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { workspaceAPI } from '../../src/services/api';
import type { WorkspaceContext } from '../../src/types';

const QUICK_ACTIONS = [
  { label: 'Add Screen', desc: 'Connect a display', icon: 'tv' as const, color: '#6366F1', route: '/workspace/screens' },
  { label: 'Upload Media', desc: 'Images & videos', icon: 'cloud-upload' as const, color: '#22D3EE', route: '/workspace/content' },
  { label: 'Create Playlist', desc: 'Organise content', icon: 'list' as const, color: '#10B981', route: '/workspace/playlists' },
  { label: 'Schedule', desc: 'Set broadcast times', icon: 'calendar' as const, color: '#F59E0B', route: '/workspace/schedules' },
];

function StatCard({ label, value, sub, icon, color }: { label: string; value: string | number; sub: string; icon: any; color: string }) {
  return (
    <View style={sd.statCard}>
      <View style={sd.statHeader}>
        <Text style={sd.statLabel}>{label}</Text>
        <View style={[sd.statIconBox, { backgroundColor: color + '22' }]}>
          <Ionicons name={icon} size={14} color={color} />
        </View>
      </View>
      <Text style={sd.statValue}>{value}</Text>
      <Text style={sd.statSub}>{sub}</Text>
    </View>
  );
}

export default function WorkspaceDashboard() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [ctx, setCtx] = useState<WorkspaceContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const res = await workspaceAPI.context();
      setCtx(res.data);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Failed to load workspace');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const org = ctx?.organization;
  const sub = ctx?.subscription;
  const plan = ctx?.plan_config;
  const stats = ctx?.stats || { screens: 0, users: 0, devices: 0 };
  const now = new Date();
  const hour = now.getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';

  return (
    <ScrollView style={sd.root} contentContainerStyle={[sd.content, { paddingBottom: insets.bottom + 24 }]} showsVerticalScrollIndicator={false}>
      {loading && (
        <View style={sd.center}>
          <ActivityIndicator color="#6366F1" size="large" />
          <Text style={sd.loadingText}>Loading workspace…</Text>
        </View>
      )}
      {error !== '' && !loading && (
        <View style={sd.errorBox}>
          <Ionicons name="warning" size={16} color="#F87171" />
          <Text style={sd.errorText}>{error}</Text>
          <TouchableOpacity onPress={load} style={sd.retryBtn}><Text style={sd.retryText}>Retry</Text></TouchableOpacity>
        </View>
      )}

      {!loading && ctx && (
        <>
          {/* Welcome */}
          <View style={sd.welcome}>
            <View style={{ flex: 1 }}>
              <Text style={sd.greeting}>{greeting}</Text>
              <Text style={sd.orgName}>{org?.name || 'Your Workspace'}</Text>
              {sub?.status && <Text style={sd.subStatus}>Subscription: <Text style={{ color: sub.status === 'trial' ? '#60A5FA' : '#34D399' }}>{sub.status}</Text></Text>}
            </View>
            {plan && (
              <View style={sd.planBadge}>
                <Text style={sd.planLabel}>PLAN</Text>
                <Text style={sd.planName}>{plan.display_name}</Text>
                <Text style={sd.planPrice}>{plan.monthly_price === 0 ? 'Free' : `$${plan.monthly_price}/mo`}</Text>
              </View>
            )}
          </View>

          {/* Trial banner */}
          {sub?.trial_ends_at && (
            <TouchableOpacity style={sd.trialBanner} onPress={() => router.push('/workspace/billing')} activeOpacity={0.8}>
              <Ionicons name="time-outline" size={18} color="#60A5FA" />
              <Text style={sd.trialText}>
                Free trial ends {new Date(sub.trial_ends_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
              </Text>
              <Text style={sd.trialCta}>View Billing →</Text>
            </TouchableOpacity>
          )}

          {/* Stats */}
          <View style={sd.statsGrid}>
            <StatCard label="SCREENS" value={stats.screens} sub="Display locations" icon="tv" color="#6366F1" />
            <StatCard label="PLAYERS" value={stats.devices} sub="Connected devices" icon="hardware-chip" color="#22D3EE" />
            <StatCard label="TEAM" value={stats.users} sub="Workspace users" icon="people" color="#10B981" />
            <StatCard label="PLAN SCREENS" value={plan?.screens_included ?? '—'} sub={plan?.screens_limit ? `Max ${plan.screens_limit}` : 'Unlimited add-ons'} icon="layers" color="#F59E0B" />
          </View>

          {/* Quick Actions */}
          <Text style={sd.sectionTitle}>Quick Actions</Text>
          <View style={sd.actionsGrid}>
            {QUICK_ACTIONS.map(a => (
              <TouchableOpacity key={a.label} style={sd.actionCard} onPress={() => router.push(a.route as any)} activeOpacity={0.7}>
                <View style={[sd.actionIcon, { backgroundColor: a.color + '22' }]}>
                  <Ionicons name={a.icon} size={20} color={a.color} />
                </View>
                <Text style={sd.actionLabel}>{a.label}</Text>
                <Text style={sd.actionDesc}>{a.desc}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </>
      )}
    </ScrollView>
  );
}

const sd = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0B0F1A' },
  content: { padding: 20, gap: 20 },
  center: { alignItems: 'center', paddingVertical: 60, gap: 12 },
  loadingText: { fontSize: 13, color: '#64748B' },
  errorBox: { alignItems: 'center', backgroundColor: '#1C1115', borderWidth: 1, borderColor: '#7F1D1D', borderRadius: 12, padding: 20, gap: 8 },
  errorText: { fontSize: 13, color: '#F87171', textAlign: 'center' },
  retryBtn: { paddingVertical: 8, paddingHorizontal: 20, backgroundColor: '#1F2937', borderRadius: 8, marginTop: 4 },
  retryText: { fontSize: 13, color: '#D1D5DB', fontWeight: '600' },
  // Welcome
  welcome: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, backgroundColor: '#111827', borderWidth: 1, borderColor: '#1E293B', borderRadius: 16, padding: 20 },
  greeting: { fontSize: 12, color: '#818CF8', fontWeight: '600', marginBottom: 4 },
  orgName: { fontSize: 20, fontWeight: '800', color: '#F1F5F9', marginBottom: 4 },
  subStatus: { fontSize: 12, color: '#94A3B8' },
  planBadge: { backgroundColor: '#0B0F1A', borderWidth: 1, borderColor: '#1E293B', borderRadius: 12, padding: 12, alignItems: 'center', minWidth: 90 },
  planLabel: { fontSize: 9, fontWeight: '700', color: '#64748B', letterSpacing: 1, marginBottom: 2 },
  planName: { fontSize: 16, fontWeight: '800', color: '#818CF8' },
  planPrice: { fontSize: 11, color: '#94A3B8', marginTop: 2 },
  // Trial banner
  trialBanner: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: '#1E3A5F', borderWidth: 1, borderColor: '#1E40AF', borderRadius: 12, padding: 14 },
  trialText: { flex: 1, fontSize: 13, color: '#93C5FD', fontWeight: '500' },
  trialCta: { fontSize: 12, color: '#60A5FA', fontWeight: '700' },
  // Stats
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  statCard: { flex: 1, minWidth: 140, backgroundColor: '#111827', borderWidth: 1, borderColor: '#1E293B', borderRadius: 14, padding: 16 },
  statHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 },
  statLabel: { fontSize: 10, fontWeight: '700', color: '#64748B', letterSpacing: 0.8 },
  statIconBox: { width: 28, height: 28, borderRadius: 8, justifyContent: 'center', alignItems: 'center' },
  statValue: { fontSize: 26, fontWeight: '800', color: '#F1F5F9', fontVariant: ['tabular-nums'] },
  statSub: { fontSize: 11, color: '#64748B', marginTop: 4 },
  // Actions
  sectionTitle: { fontSize: 15, fontWeight: '700', color: '#F1F5F9', marginBottom: -8 },
  actionsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  actionCard: { flex: 1, minWidth: 140, backgroundColor: '#111827', borderWidth: 1, borderColor: '#1E293B', borderRadius: 14, padding: 16, gap: 6 },
  actionIcon: { width: 40, height: 40, borderRadius: 11, justifyContent: 'center', alignItems: 'center', marginBottom: 4 },
  actionLabel: { fontSize: 13, fontWeight: '700', color: '#F1F5F9' },
  actionDesc: { fontSize: 11, color: '#64748B' },
});
