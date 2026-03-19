import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  RefreshControl, ActivityIndicator, Dimensions, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useAuthStore } from '../../src/store/authStore';
import { analyticsAPI, adminAPI } from '../../src/services/api';
import { getStatusStyle } from '../../src/constants/theme';

const { width: SW } = Dimensions.get('window');
const W = Platform.OS === 'web' && SW > 860;

export default function DashboardScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user } = useAuthStore();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const res = await analyticsAPI.dashboard();
      setData(res.data);
      if (user?.role === 'admin') {
        try {
          const adm = await adminAPI.analytics();
          setData((p: any) => ({ ...p, total_revenue: adm.data.total_revenue, total_screens: adm.data.total_screens, active_screens: adm.data.active_screens }));
        } catch (e) {}
      }
    } catch (e) {} finally { setLoading(false); setRefreshing(false); }
  }, [user]);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading) return <View style={s.loadC}><ActivityIndicator size="large" color="#6366F1" /></View>;

  const stats = [
    { label: 'Total Revenue', value: `$${(data?.total_revenue || data?.total_spent || 0).toLocaleString()}`, icon: 'trending-up', color: '#22D3EE', glow: 'rgba(34,211,238,0.08)', border: 'rgba(34,211,238,0.25)' },
    { label: 'Active Screens', value: data?.active_screens || data?.active_campaigns || 0, icon: 'radio-button-on', color: '#10B981', glow: 'rgba(16,185,129,0.08)', border: 'rgba(16,185,129,0.25)' },
    { label: 'Total Campaigns', value: data?.total_campaigns || 0, icon: 'layers', color: '#818CF8', glow: 'rgba(129,140,248,0.08)', border: 'rgba(129,140,248,0.25)' },
    { label: 'Pending Review', value: data?.pending_campaigns || 0, icon: 'hourglass', color: '#FBBF24', glow: 'rgba(251,191,36,0.08)', border: 'rgba(251,191,36,0.25)' },
  ];

  return (
    <ScrollView style={s.ct} contentContainerStyle={{ paddingTop: W ? 36 : insets.top + 20, paddingBottom: 120, paddingHorizontal: W ? 40 : 18 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchData(); }} tintColor="#6366F1" />}>

      {/* Hero Header */}
      <View style={s.hero}>
        <View style={s.heroLeft}>
          <Text style={s.heroGreeting}>Welcome back</Text>
          <Text style={s.heroName}>{user?.name || 'User'}</Text>
          <Text style={s.heroSub}>Here's what's happening with your signage network today.</Text>
        </View>
        <TouchableOpacity style={s.heroBtn} onPress={() => router.push('/campaign/create')}>
          <Ionicons name="add" size={18} color="#FFF" />
          <Text style={s.heroBtnT}>New Campaign</Text>
        </TouchableOpacity>
      </View>

      {/* Stats Grid - Premium Cards with glow border */}
      <View style={s.statsGrid}>
        {stats.map((st, i) => (
          <View key={i} style={[s.statCard, { backgroundColor: st.glow, borderColor: st.border }]}>
            <View style={s.statHeader}>
              <View style={[s.statDot, { backgroundColor: st.color }]} />
              <Text style={s.statLabel}>{st.label}</Text>
            </View>
            <Text style={[s.statValue, { color: st.color }]}>{st.value}</Text>
          </View>
        ))}
      </View>

      {/* Two-column layout */}
      <View style={W ? s.gridRow : undefined}>
        {/* Recent Campaigns */}
        <View style={[s.section, W && { flex: 1, marginRight: 20 }]}>
          <View style={s.secHeader}>
            <View>
              <Text style={s.secTitle}>Recent Campaigns</Text>
              <Text style={s.secSub}>Latest activity in your account</Text>
            </View>
            <TouchableOpacity style={s.seeAllBtn} onPress={() => router.push('/(tabs)/campaigns')}>
              <Text style={s.seeAllT}>View All</Text>
              <Ionicons name="arrow-forward" size={14} color="#818CF8" />
            </TouchableOpacity>
          </View>
          <View style={s.card}>
            {(data?.recent_campaigns || []).length === 0 ? (
              <View style={s.emptyCard}>
                <View style={s.emptyIcon}><Ionicons name="megaphone-outline" size={28} color="#475569" /></View>
                <Text style={s.emptyT}>No campaigns yet</Text>
                <Text style={s.emptySub}>Create your first campaign to get started</Text>
              </View>
            ) : (
              (data?.recent_campaigns || []).map((c: any, i: number) => {
                const st = getStatusStyle(c.status);
                return (
                  <TouchableOpacity key={c.id} style={[s.listItem, i > 0 && s.listBorder]} onPress={() => router.push(`/campaign/${c.id}`)}>
                    <View style={[s.campDot, { backgroundColor: st.text }]} />
                    <View style={{ flex: 1 }}>
                      <Text style={s.listTitle} numberOfLines={1}>{c.name}</Text>
                      <Text style={s.listSub}>{c.screen_name || 'Screen'} \u2022 {c.schedule?.start_date}</Text>
                    </View>
                    <View style={[s.badge, { backgroundColor: st.bg }]}>
                      <Text style={[s.badgeT, { color: st.text }]}>{c.status}</Text>
                    </View>
                  </TouchableOpacity>
                );
              })
            )}
          </View>
        </View>

        {/* Quick Actions */}
        <View style={[s.section, W && { width: 300 }]}>
          <View style={s.secHeader}>
            <View><Text style={s.secTitle}>Quick Actions</Text><Text style={s.secSub}>Navigate to key features</Text></View>
          </View>
          <View style={s.card}>
            {[
              { label: 'Create Campaign', desc: 'Launch a new ad campaign', icon: 'add-circle', color: '#6366F1', route: '/campaign/create' },
              { label: 'Browse Screens', desc: 'Explore available displays', icon: 'tv', color: '#22D3EE', route: '/(tabs)/screens' },
              { label: 'Payment History', desc: 'View invoices & billing', icon: 'card', color: '#10B981', route: '/(tabs)/payments' },
              ...(user?.role === 'admin' ? [{ label: 'Admin Panel', desc: 'Manage the entire platform', icon: 'shield-checkmark', color: '#FBBF24', route: '/admin' }] : []),
            ].map((a, i) => (
              <TouchableOpacity key={i} style={[s.actionItem, i > 0 && s.listBorder]} onPress={() => router.push(a.route as any)}>
                <View style={[s.actionIcon, { backgroundColor: a.color + '15', borderColor: a.color + '30' }]}>
                  <Ionicons name={a.icon as any} size={18} color={a.color} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.actionLabel}>{a.label}</Text>
                  <Text style={s.actionDesc}>{a.desc}</Text>
                </View>
                <Ionicons name="chevron-forward" size={16} color="#374151" />
              </TouchableOpacity>
            ))}
          </View>
        </View>
      </View>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  ct: { flex: 1, backgroundColor: '#0B0F1A' },
  loadC: { flex: 1, backgroundColor: '#0B0F1A', justifyContent: 'center', alignItems: 'center' },

  // Hero
  hero: { flexDirection: W ? 'row' : 'column', justifyContent: 'space-between', alignItems: W ? 'flex-end' : 'flex-start', marginBottom: 32, gap: 16 },
  heroLeft: { flex: 1 },
  heroGreeting: { fontSize: 14, color: '#64748B', fontWeight: '500', letterSpacing: 0.5, textTransform: 'uppercase', marginBottom: 4 },
  heroName: { fontSize: 32, fontWeight: '800', color: '#F1F5F9', letterSpacing: -0.5, marginBottom: 6 },
  heroSub: { fontSize: 15, color: '#64748B', lineHeight: 22, maxWidth: 500 },
  heroBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: '#6366F1', paddingHorizontal: 20, paddingVertical: 12, borderRadius: 12, shadowColor: '#6366F1', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.3, shadowRadius: 12, elevation: 6 },
  heroBtnT: { color: '#FFF', fontSize: 14, fontWeight: '700' },

  // Stats
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 14, marginBottom: 32 },
  statCard: {
    flex: 1, flexBasis: W ? '22%' : '46%', minWidth: 160,
    borderRadius: 16, padding: 20, borderWidth: 1,
  },
  statHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 },
  statDot: { width: 8, height: 8, borderRadius: 4 },
  statLabel: { fontSize: 13, color: '#94A3B8', fontWeight: '500' },
  statValue: { fontSize: 30, fontWeight: '800', letterSpacing: -1 },

  // Sections
  gridRow: { flexDirection: 'row' },
  section: { marginBottom: 24 },
  secHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 },
  secTitle: { fontSize: 18, fontWeight: '700', color: '#F1F5F9', letterSpacing: -0.3 },
  secSub: { fontSize: 12, color: '#475569', marginTop: 2 },
  seeAllBtn: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  seeAllT: { fontSize: 13, color: '#818CF8', fontWeight: '600' },

  // Card
  card: { backgroundColor: '#111827', borderRadius: 16, borderWidth: 1, borderColor: '#1E293B', overflow: 'hidden' },
  emptyCard: { padding: 40, alignItems: 'center' },
  emptyIcon: { width: 56, height: 56, borderRadius: 16, backgroundColor: '#1F2937', justifyContent: 'center', alignItems: 'center', marginBottom: 14 },
  emptyT: { fontSize: 15, color: '#64748B', fontWeight: '600' },
  emptySub: { fontSize: 13, color: '#475569', marginTop: 4 },

  // List
  listItem: { flexDirection: 'row', alignItems: 'center', padding: 16, gap: 12 },
  listBorder: { borderTopWidth: 1, borderTopColor: '#1E293B' },
  campDot: { width: 6, height: 6, borderRadius: 3 },
  listTitle: { fontSize: 14, fontWeight: '600', color: '#E2E8F0', marginBottom: 2 },
  listSub: { fontSize: 12, color: '#64748B' },
  badge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  badgeT: { fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 },

  // Actions
  actionItem: { flexDirection: 'row', alignItems: 'center', padding: 14, gap: 12 },
  actionIcon: { width: 40, height: 40, borderRadius: 12, justifyContent: 'center', alignItems: 'center', borderWidth: 1 },
  actionLabel: { fontSize: 14, fontWeight: '600', color: '#E2E8F0' },
  actionDesc: { fontSize: 11, color: '#475569', marginTop: 1 },
});
