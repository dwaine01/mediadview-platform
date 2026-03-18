import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  RefreshControl, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useAuthStore } from '../../src/store/authStore';
import { analyticsAPI } from '../../src/services/api';
import { getStatusStyle } from '../../src/constants/theme';

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
    } catch (e) {
      console.log('Dashboard fetch error:', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const onRefresh = () => { setRefreshing(true); fetchData(); };

  if (loading) {
    return (
      <View style={[styles.center, { paddingTop: insets.top }]}>
        <ActivityIndicator size="large" color="#4F46E5" />
      </View>
    );
  }

  const stats = [
    { label: 'Total Campaigns', value: data?.total_campaigns || 0, icon: 'megaphone', color: '#4F46E5' },
    { label: 'Active', value: data?.active_campaigns || 0, icon: 'play-circle', color: '#10B981' },
    { label: 'Pending', value: data?.pending_campaigns || 0, icon: 'time', color: '#F59E0B' },
    { label: 'Total Spent', value: `$${(data?.total_spent || 0).toLocaleString()}`, icon: 'wallet', color: '#0EA5E9' },
  ];

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={{ paddingTop: insets.top + 16, paddingBottom: 100 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#4F46E5" />}
    >
      <View style={styles.header}>
        <View>
          <Text style={styles.greeting}>Welcome back,</Text>
          <Text style={styles.userName}>{user?.name || 'User'}</Text>
        </View>
        {user?.role === 'admin' && (
          <TouchableOpacity style={styles.adminBtn} onPress={() => router.push('/admin')}>
            <Ionicons name="shield-checkmark" size={18} color="#FFFFFF" />
            <Text style={styles.adminBtnText}>Admin</Text>
          </TouchableOpacity>
        )}
      </View>

      <View style={styles.statsGrid}>
        {stats.map((stat, i) => (
          <View key={i} style={styles.statCard}>
            <View style={[styles.statIcon, { backgroundColor: stat.color + '15' }]}>
              <Ionicons name={stat.icon as any} size={20} color={stat.color} />
            </View>
            <Text style={styles.statValue}>{stat.value}</Text>
            <Text style={styles.statLabel}>{stat.label}</Text>
          </View>
        ))}
      </View>

      <View style={styles.actions}>
        <TouchableOpacity style={styles.actionPrimary} onPress={() => router.push('/campaign/create')}>
          <Ionicons name="add-circle" size={22} color="#FFFFFF" />
          <Text style={styles.actionPrimaryText}>Create Campaign</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.actionSecondary} onPress={() => router.push('/(tabs)/screens')}>
          <Ionicons name="tv" size={22} color="#4F46E5" />
          <Text style={styles.actionSecondaryText}>Browse Screens</Text>
        </TouchableOpacity>
      </View>

      <Text style={styles.sectionTitle}>Recent Campaigns</Text>
      {(data?.recent_campaigns || []).length === 0 ? (
        <View style={styles.emptyCard}>
          <Ionicons name="megaphone-outline" size={40} color="#CBD5E1" />
          <Text style={styles.emptyText}>No campaigns yet</Text>
          <Text style={styles.emptySubtext}>Create your first campaign to get started</Text>
        </View>
      ) : (
        (data?.recent_campaigns || []).map((c: any) => {
          const st = getStatusStyle(c.status);
          return (
            <TouchableOpacity key={c.id} style={styles.campaignCard} onPress={() => router.push(`/campaign/${c.id}`)}>
              <View style={styles.campaignHeader}>
                <Text style={styles.campaignName} numberOfLines={1}>{c.name}</Text>
                <View style={[styles.badge, { backgroundColor: st.bg }]}>
                  <Text style={[styles.badgeText, { color: st.text }]}>{c.status}</Text>
                </View>
              </View>
              <View style={styles.campaignMeta}>
                <Ionicons name="tv-outline" size={14} color="#64748B" />
                <Text style={styles.metaText}>{c.screen_name || 'Screen'}</Text>
                <Ionicons name="calendar-outline" size={14} color="#64748B" style={{ marginLeft: 12 }} />
                <Text style={styles.metaText}>{c.schedule?.start_date || ''}</Text>
              </View>
              <Text style={styles.campaignPrice}>${c.pricing?.total?.toLocaleString() || '0'}</Text>
            </TouchableOpacity>
          );
        })
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F1F5F9' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#F1F5F9' },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 20, marginBottom: 24 },
  greeting: { fontSize: 14, color: '#64748B' },
  userName: { fontSize: 24, fontWeight: '700', color: '#0F172A', marginTop: 2 },
  adminBtn: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: '#4F46E5',
    paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, gap: 6,
  },
  adminBtnText: { color: '#FFFFFF', fontSize: 13, fontWeight: '600' },
  statsGrid: {
    flexDirection: 'row', flexWrap: 'wrap', paddingHorizontal: 14, gap: 8,
    marginBottom: 24,
  },
  statCard: {
    width: '48%', backgroundColor: '#FFFFFF', borderRadius: 16, padding: 16,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04, shadowRadius: 6, elevation: 2, flexGrow: 1, flexBasis: '46%',
  },
  statIcon: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center', marginBottom: 10 },
  statValue: { fontSize: 22, fontWeight: '700', color: '#0F172A' },
  statLabel: { fontSize: 12, color: '#64748B', marginTop: 2 },
  actions: { flexDirection: 'row', paddingHorizontal: 20, gap: 12, marginBottom: 28 },
  actionPrimary: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    backgroundColor: '#4F46E5', borderRadius: 14, paddingVertical: 14, gap: 8,
  },
  actionPrimaryText: { color: '#FFFFFF', fontSize: 14, fontWeight: '700' },
  actionSecondary: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    backgroundColor: '#EEF2FF', borderRadius: 14, paddingVertical: 14, gap: 8,
  },
  actionSecondaryText: { color: '#4F46E5', fontSize: 14, fontWeight: '700' },
  sectionTitle: { fontSize: 18, fontWeight: '700', color: '#0F172A', paddingHorizontal: 20, marginBottom: 12 },
  emptyCard: {
    backgroundColor: '#FFFFFF', borderRadius: 16, padding: 32, marginHorizontal: 20,
    alignItems: 'center', shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04, shadowRadius: 6, elevation: 2,
  },
  emptyText: { fontSize: 16, fontWeight: '600', color: '#64748B', marginTop: 12 },
  emptySubtext: { fontSize: 13, color: '#94A3B8', marginTop: 4, textAlign: 'center' },
  campaignCard: {
    backgroundColor: '#FFFFFF', borderRadius: 16, padding: 16, marginHorizontal: 20,
    marginBottom: 10, shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04, shadowRadius: 6, elevation: 2,
  },
  campaignHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  campaignName: { fontSize: 16, fontWeight: '600', color: '#0F172A', flex: 1, marginRight: 8 },
  badge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  badgeText: { fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },
  campaignMeta: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  metaText: { fontSize: 13, color: '#64748B' },
  campaignPrice: { fontSize: 18, fontWeight: '700', color: '#4F46E5', marginTop: 8 },
});
