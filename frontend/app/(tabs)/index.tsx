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
    { label: 'Total Revenue', value: `$${(data?.total_revenue || data?.total_spent || 0).toLocaleString()}`, sub: 'All time earnings', icon: 'trending-up', accent: '#22D3EE', accentBg: '#083344' },
    { label: 'Active Screens', value: `${data?.active_screens || data?.active_campaigns || 0}`, sub: 'Currently running', icon: 'radio-button-on', accent: '#34D399', accentBg: '#022C22' },
    { label: 'Campaigns', value: `${data?.total_campaigns || 0}`, sub: 'Total created', icon: 'layers', accent: '#A78BFA', accentBg: '#1E1B4B' },
    { label: 'Pending Review', value: `${data?.pending_campaigns || 0}`, sub: 'Awaiting approval', icon: 'time', accent: '#FBBF24', accentBg: '#422006' },
  ];

  return (
    <ScrollView style={s.ct} contentContainerStyle={{ paddingTop: W ? 40 : insets.top + 20, paddingBottom: 120, paddingHorizontal: W ? 44 : 18 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchData(); }} tintColor="#6366F1" />}>

      {/* Decorative orb */}
      <View style={s.orb} />

      {/* Header */}
      <View style={s.hd}>
        <View style={{ flex: 1 }}>
          <Text style={s.greeting}>WELCOME BACK</Text>
          <Text style={s.heroName}>{user?.name || 'User'}</Text>
          <Text style={s.heroSub}>Your signage network overview</Text>
        </View>
        <TouchableOpacity style={s.cta} onPress={() => router.push('/campaign/create')} activeOpacity={0.8}>
          <Ionicons name="add" size={18} color="#FFF" />
          <Text style={s.ctaT}>New Campaign</Text>
        </TouchableOpacity>
      </View>

      {/* Stats */}
      <View style={s.statsRow}>
        {stats.map((st, i) => (
          <View key={i} style={s.stat}>
            <View style={[s.statAccent, { backgroundColor: st.accent }]} />
            <View style={s.statBody}>
              <View style={s.statTop}>
                <View style={[s.statIconBox, { backgroundColor: st.accentBg }]}>
                  <Ionicons name={st.icon as any} size={18} color={st.accent} />
                </View>
                <Text style={s.statLabel}>{st.label}</Text>
              </View>
              <Text style={[s.statVal, { color: st.accent }]}>{st.value}</Text>
              <Text style={s.statSub}>{st.sub}</Text>
            </View>
          </View>
        ))}
      </View>

      {/* Two columns */}
      <View style={W ? s.cols : undefined}>
        {/* Recent */}
        <View style={[s.sec, W && { flex: 1, marginRight: 24 }]}>
          <View style={s.secHd}>
            <Text style={s.secTitle}>Recent Campaigns</Text>
            <TouchableOpacity style={s.seeAll} onPress={() => router.push('/(tabs)/campaigns')}>
              <Text style={s.seeAllT}>View All</Text>
              <Ionicons name="arrow-forward" size={14} color="#6366F1" />
            </TouchableOpacity>
          </View>
          <View style={s.card}>
            {(data?.recent_campaigns || []).length === 0 ? (
              <View style={s.emptyC}>
                <View style={s.emptyIc}><Ionicons name="megaphone-outline" size={28} color="#374151" /></View>
                <Text style={s.emptyT}>No campaigns yet</Text>
                <Text style={s.emptyS}>Create your first campaign to get started</Text>
                <TouchableOpacity style={s.emptyBtn} onPress={() => router.push('/campaign/create')}>
                  <Text style={s.emptyBtnT}>Create Campaign</Text>
                </TouchableOpacity>
              </View>
            ) : (
              (data?.recent_campaigns || []).map((c: any, i: number) => {
                const st = getStatusStyle(c.status);
                return (
                  <TouchableOpacity key={c.id} style={[s.li, i > 0 && s.liBorder]} onPress={() => router.push(`/campaign/${c.id}`)}>
                    <View style={[s.liDot, { backgroundColor: st.text }]} />
                    <View style={{ flex: 1 }}>
                      <Text style={s.liTitle} numberOfLines={1}>{c.name}</Text>
                      <Text style={s.liSub}>{c.screen_name || 'Screen'} \u2022 {c.schedule?.start_date}</Text>
                    </View>
                    <View style={[s.badge, { backgroundColor: st.bg }]}>
                      <Text style={[s.badgeT, { color: st.text }]}>{c.status}</Text>
                    </View>
                    <Ionicons name="chevron-forward" size={16} color="#1E293B" />
                  </TouchableOpacity>
                );
              })
            )}
          </View>
        </View>

        {/* Actions */}
        <View style={[s.sec, W && { width: 320 }]}>
          <Text style={s.secTitle}>Quick Actions</Text>
          <View style={{ gap: 10, marginTop: 14 }}>
            {[
              { label: 'Create Campaign', desc: 'Launch a new ad', icon: 'add-circle', color: '#6366F1', bg: '#1E1B4B', route: '/campaign/create' },
              { label: 'Browse Screens', desc: 'Explore displays', icon: 'tv', color: '#22D3EE', bg: '#083344', route: '/(tabs)/screens' },
              { label: 'Payment History', desc: 'Invoices & billing', icon: 'card', color: '#34D399', bg: '#022C22', route: '/(tabs)/payments' },
              ...(user?.role === 'admin' ? [{ label: 'Admin Panel', desc: 'Manage platform', icon: 'shield-checkmark', color: '#FBBF24', bg: '#422006', route: '/admin' }] : []),
            ].map((a, i) => (
              <TouchableOpacity key={i} style={s.actCard} onPress={() => router.push(a.route as any)} activeOpacity={0.7}>
                <View style={[s.actIc, { backgroundColor: a.bg, borderColor: a.color + '30' }]}>
                  <Ionicons name={a.icon as any} size={20} color={a.color} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.actLabel}>{a.label}</Text>
                  <Text style={s.actDesc}>{a.desc}</Text>
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
  ct: { flex: 1, backgroundColor: '#050816' },
  loadC: { flex: 1, backgroundColor: '#050816', justifyContent: 'center', alignItems: 'center' },
  orb: { position: 'absolute', top: -60, right: -40, width: 200, height: 200, borderRadius: 100, backgroundColor: 'rgba(99,102,241,0.06)' },

  hd: { flexDirection: W ? 'row' : 'column', justifyContent: 'space-between', alignItems: W ? 'flex-end' : 'flex-start', marginBottom: 36, gap: 18 },
  greeting: { fontSize: 11, fontWeight: '700', color: '#6366F1', letterSpacing: 2, marginBottom: 6 },
  heroName: { fontSize: 34, fontWeight: '800', color: '#F8FAFC', letterSpacing: -1 },
  heroSub: { fontSize: 15, color: '#475569', marginTop: 4 },
  cta: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: '#6366F1', paddingHorizontal: 22, paddingVertical: 13, borderRadius: 14,
    shadowColor: '#6366F1', shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.35, shadowRadius: 16, elevation: 8,
  },
  ctaT: { color: '#FFF', fontSize: 14, fontWeight: '700', letterSpacing: 0.3 },

  // Stats with accent left bar
  statsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 14, marginBottom: 36 },
  stat: {
    flex: 1, flexBasis: W ? '22%' : '46%', minWidth: 155,
    backgroundColor: '#0D1225', borderRadius: 18, overflow: 'hidden',
    flexDirection: 'row', borderWidth: 1, borderColor: '#111827',
  },
  statAccent: { width: 4, borderTopLeftRadius: 18, borderBottomLeftRadius: 18 },
  statBody: { flex: 1, padding: 18 },
  statTop: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 14 },
  statIconBox: { width: 34, height: 34, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  statLabel: { fontSize: 12, color: '#64748B', fontWeight: '600' },
  statVal: { fontSize: 32, fontWeight: '800', letterSpacing: -1 },
  statSub: { fontSize: 11, color: '#374151', marginTop: 4 },

  // Sections
  cols: { flexDirection: 'row' },
  sec: { marginBottom: 24 },
  secHd: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 },
  secTitle: { fontSize: 18, fontWeight: '700', color: '#E2E8F0', letterSpacing: -0.3 },
  seeAll: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  seeAllT: { fontSize: 13, color: '#6366F1', fontWeight: '600' },

  card: { backgroundColor: '#0D1225', borderRadius: 18, borderWidth: 1, borderColor: '#111827', overflow: 'hidden' },
  emptyC: { padding: 44, alignItems: 'center' },
  emptyIc: { width: 56, height: 56, borderRadius: 16, backgroundColor: '#111827', justifyContent: 'center', alignItems: 'center', marginBottom: 16 },
  emptyT: { fontSize: 16, color: '#64748B', fontWeight: '600' },
  emptyS: { fontSize: 13, color: '#374151', marginTop: 4, marginBottom: 20 },
  emptyBtn: { backgroundColor: '#6366F1', paddingHorizontal: 20, paddingVertical: 10, borderRadius: 10 },
  emptyBtnT: { color: '#FFF', fontSize: 13, fontWeight: '700' },

  li: { flexDirection: 'row', alignItems: 'center', padding: 16, gap: 12 },
  liBorder: { borderTopWidth: 1, borderTopColor: '#111827' },
  liDot: { width: 8, height: 8, borderRadius: 4 },
  liTitle: { fontSize: 14, fontWeight: '600', color: '#E2E8F0', marginBottom: 2 },
  liSub: { fontSize: 12, color: '#475569' },
  badge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  badgeT: { fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 },

  // Action cards
  actCard: {
    flexDirection: 'row', alignItems: 'center', gap: 14,
    backgroundColor: '#0D1225', borderRadius: 16, padding: 16,
    borderWidth: 1, borderColor: '#111827',
  },
  actIc: { width: 44, height: 44, borderRadius: 14, justifyContent: 'center', alignItems: 'center', borderWidth: 1 },
  actLabel: { fontSize: 14, fontWeight: '700', color: '#E2E8F0' },
  actDesc: { fontSize: 11, color: '#475569', marginTop: 1 },
});
