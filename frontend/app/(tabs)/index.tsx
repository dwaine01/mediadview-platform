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
const IS_WIDE = SW > 860;

export default function DashboardScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user } = useAuthStore();
  const [data, setData] = useState<any>(null);
  const [devices, setDevices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const res = await analyticsAPI.dashboard();
      setData(res.data);
      if (user?.role === 'admin') {
        try {
          const devRes = await adminAPI.analytics();
          setDevices([]);
          // Merge admin data
          setData((prev: any) => ({
            ...prev,
            total_revenue: devRes.data.total_revenue,
            total_screens: devRes.data.total_screens,
            active_screens: devRes.data.active_screens,
          }));
        } catch (e) {}
      }
    } catch (e) {
      console.log('Dashboard error:', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [user]);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading) {
    return <View style={s.loadingContainer}><ActivityIndicator size="large" color="#6366F1" /></View>;
  }

  const stats = [
    { label: 'Total Revenue', value: `$${(data?.total_revenue || data?.total_spent || 0).toLocaleString()}`, icon: 'wallet', color: '#22D3EE', bgColor: 'rgba(34,211,238,0.1)' },
    { label: 'Active Screens', value: data?.active_screens || data?.active_campaigns || 0, icon: 'tv', color: '#10B981', bgColor: 'rgba(16,185,129,0.1)' },
    { label: 'Campaigns', value: data?.total_campaigns || 0, icon: 'megaphone', color: '#818CF8', bgColor: 'rgba(129,140,248,0.1)' },
    { label: 'Pending', value: data?.pending_campaigns || 0, icon: 'time', color: '#F59E0B', bgColor: 'rgba(245,158,11,0.1)' },
  ];

  return (
    <ScrollView
      style={s.container}
      contentContainerStyle={{ paddingTop: IS_WIDE ? 28 : insets.top + 16, paddingBottom: 100, paddingHorizontal: IS_WIDE ? 32 : 16 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchData(); }} tintColor="#6366F1" />}
    >
      {/* Header */}
      <View style={s.header}>
        <View>
          <Text style={s.greeting}>Welcome back</Text>
          <Text style={s.userName}>{user?.name || 'User'}</Text>
        </View>
        <View style={s.headerActions}>
          <TouchableOpacity style={s.createBtn} onPress={() => router.push('/campaign/create')}>
            <Ionicons name="add" size={18} color="#FFF" />
            <Text style={s.createBtnText}>New Campaign</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Stats Grid */}
      <View style={s.statsGrid}>
        {stats.map((stat, i) => (
          <View key={i} style={s.statCard}>
            <View style={s.statTop}>
              <View style={[s.statIconBox, { backgroundColor: stat.bgColor }]}>
                <Ionicons name={stat.icon as any} size={20} color={stat.color} />
              </View>
              <Text style={s.statLabel}>{stat.label}</Text>
            </View>
            <Text style={[s.statValue, { color: stat.color }]}>{stat.value}</Text>
          </View>
        ))}
      </View>

      {/* Content grid */}
      <View style={IS_WIDE ? s.gridRow : undefined}>
        {/* Recent Campaigns */}
        <View style={[s.section, IS_WIDE && { flex: 1, marginRight: 16 }]}>
          <View style={s.sectionHeader}>
            <Text style={s.sectionTitle}>Recent Campaigns</Text>
            <TouchableOpacity onPress={() => router.push('/(tabs)/campaigns')}>
              <Text style={s.seeAll}>View All</Text>
            </TouchableOpacity>
          </View>
          <View style={s.card}>
            {(data?.recent_campaigns || []).length === 0 ? (
              <View style={s.emptyCard}>
                <Ionicons name="megaphone-outline" size={32} color="#374151" />
                <Text style={s.emptyText}>No campaigns yet</Text>
              </View>
            ) : (
              (data?.recent_campaigns || []).map((c: any, i: number) => {
                const st = getStatusStyle(c.status);
                return (
                  <TouchableOpacity key={c.id} style={[s.listItem, i > 0 && s.listItemBorder]} onPress={() => router.push(`/campaign/${c.id}`)}>
                    <View style={{ flex: 1 }}>
                      <Text style={s.listTitle} numberOfLines={1}>{c.name}</Text>
                      <Text style={s.listSub}>{c.screen_name || 'Screen'} | {c.schedule?.start_date}</Text>
                    </View>
                    <View style={[s.badge, { backgroundColor: st.bg }]}>
                      <Text style={[s.badgeText, { color: st.text }]}>{c.status}</Text>
                    </View>
                  </TouchableOpacity>
                );
              })
            )}
          </View>
        </View>

        {/* Quick Actions */}
        <View style={[s.section, IS_WIDE && { width: 280 }]}>
          <Text style={s.sectionTitle}>Quick Actions</Text>
          <View style={s.card}>
            {[
              { label: 'Create Campaign', icon: 'add-circle', color: '#6366F1', route: '/campaign/create' },
              { label: 'Browse Screens', icon: 'tv', color: '#22D3EE', route: '/(tabs)/screens' },
              { label: 'View Payments', icon: 'card', color: '#10B981', route: '/(tabs)/payments' },
              ...(user?.role === 'admin' ? [{ label: 'Admin Panel', icon: 'shield-checkmark', color: '#F59E0B', route: '/admin' }] : []),
            ].map((action, i) => (
              <TouchableOpacity key={i} style={[s.actionItem, i > 0 && s.listItemBorder]} onPress={() => router.push(action.route as any)}>
                <View style={[s.actionIcon, { backgroundColor: action.color + '18' }]}>
                  <Ionicons name={action.icon as any} size={18} color={action.color} />
                </View>
                <Text style={s.actionLabel}>{action.label}</Text>
                <Ionicons name="chevron-forward" size={16} color="#475569" />
              </TouchableOpacity>
            ))}
          </View>
        </View>
      </View>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0B0F1A' },
  loadingContainer: { flex: 1, backgroundColor: '#0B0F1A', justifyContent: 'center', alignItems: 'center' },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 },
  greeting: { fontSize: 13, color: '#64748B' },
  userName: { fontSize: 22, fontWeight: '700', color: '#F1F5F9', marginTop: 2 },
  headerActions: { flexDirection: 'row', gap: 8 },
  createBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: '#6366F1', paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10,
  },
  createBtnText: { color: '#FFF', fontSize: 13, fontWeight: '600' },
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 24 },
  statCard: {
    backgroundColor: '#111827', borderRadius: 14, padding: 16, minWidth: 160,
    flex: 1, flexBasis: IS_WIDE ? '22%' : '46%', borderWidth: 1, borderColor: '#1E293B',
  },
  statTop: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12 },
  statIconBox: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  statLabel: { fontSize: 12, color: '#64748B', fontWeight: '500' },
  statValue: { fontSize: 26, fontWeight: '700' },
  gridRow: { flexDirection: 'row' },
  section: { marginBottom: 20 },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  sectionTitle: { fontSize: 15, fontWeight: '600', color: '#E2E8F0', marginBottom: 10 },
  seeAll: { fontSize: 12, color: '#6366F1', fontWeight: '600' },
  card: { backgroundColor: '#111827', borderRadius: 14, borderWidth: 1, borderColor: '#1E293B', overflow: 'hidden' },
  emptyCard: { padding: 32, alignItems: 'center', gap: 8 },
  emptyText: { fontSize: 13, color: '#475569' },
  listItem: { flexDirection: 'row', alignItems: 'center', padding: 14, gap: 10 },
  listItemBorder: { borderTopWidth: 1, borderTopColor: '#1E293B' },
  listTitle: { fontSize: 14, fontWeight: '600', color: '#E2E8F0' },
  listSub: { fontSize: 11, color: '#64748B', marginTop: 2 },
  badge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  badgeText: { fontSize: 10, fontWeight: '700', textTransform: 'uppercase' },
  actionItem: { flexDirection: 'row', alignItems: 'center', padding: 12, gap: 10 },
  actionIcon: { width: 32, height: 32, borderRadius: 8, justifyContent: 'center', alignItems: 'center' },
  actionLabel: { flex: 1, fontSize: 13, fontWeight: '500', color: '#E2E8F0' },
});
