import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  RefreshControl, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { campaignsAPI } from '../../src/services/api';
import { Campaign } from '../../src/types';
import { getStatusStyle } from '../../src/constants/theme';

const STATUS_FILTERS = ['all', 'draft', 'pending', 'approved', 'active', 'completed', 'rejected'];

export default function CampaignsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const params = filter !== 'all' ? { status: filter } : {};
      const res = await campaignsAPI.list(params);
      setCampaigns(res.data);
    } catch (e) {
      console.log('Campaigns fetch error:', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [filter]);

  useEffect(() => { setLoading(true); fetchData(); }, [fetchData]);

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>My Campaigns</Text>
          <Text style={styles.subtitle}>{campaigns.length} campaigns</Text>
        </View>
        <TouchableOpacity style={styles.createBtn} onPress={() => router.push('/campaign/create')}>
          <Ionicons name="add" size={22} color="#FFFFFF" />
        </TouchableOpacity>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.filterRow}>
        {STATUS_FILTERS.map(s => (
          <TouchableOpacity
            key={s}
            style={[styles.filterChip, filter === s && styles.filterActive]}
            onPress={() => setFilter(s)}
          >
            <Text style={[styles.filterText, filter === s && styles.filterTextActive]}>
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {loading ? (
        <View style={styles.center}><ActivityIndicator size="large" color="#4F46E5" /></View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchData(); }} tintColor="#4F46E5" />}
        >
          {campaigns.length === 0 ? (
            <View style={styles.emptyState}>
              <Ionicons name="megaphone-outline" size={48} color="#CBD5E1" />
              <Text style={styles.emptyText}>No campaigns found</Text>
              <TouchableOpacity style={styles.emptyBtn} onPress={() => router.push('/campaign/create')}>
                <Text style={styles.emptyBtnText}>Create Your First Campaign</Text>
              </TouchableOpacity>
            </View>
          ) : (
            campaigns.map(c => {
              const st = getStatusStyle(c.status);
              return (
                <TouchableOpacity key={c.id} style={styles.card} onPress={() => router.push(`/campaign/${c.id}`)}>
                  <View style={styles.cardTop}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.cardName} numberOfLines={1}>{c.name}</Text>
                      <View style={styles.cardMeta}>
                        <Ionicons name="tv-outline" size={13} color="#64748B" />
                        <Text style={styles.metaText} numberOfLines={1}>{c.screen?.name || 'Screen'}</Text>
                      </View>
                    </View>
                    <View style={[styles.badge, { backgroundColor: st.bg }]}>
                      <Text style={[styles.badgeText, { color: st.text }]}>{c.status}</Text>
                    </View>
                  </View>
                  <View style={styles.cardBottom}>
                    <View style={styles.dateRow}>
                      <Ionicons name="calendar-outline" size={13} color="#64748B" />
                      <Text style={styles.dateText}>
                        {c.schedule?.start_date} - {c.schedule?.end_date}
                      </Text>
                    </View>
                    <Text style={styles.price}>${c.pricing?.total?.toLocaleString() || '0'}</Text>
                  </View>
                </TouchableOpacity>
              );
            })
          )}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F1F5F9' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  header: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: 20, paddingTop: 16, paddingBottom: 12,
  },
  title: { fontSize: 24, fontWeight: '700', color: '#0F172A' },
  subtitle: { fontSize: 13, color: '#64748B', marginTop: 2 },
  createBtn: {
    width: 44, height: 44, borderRadius: 12, backgroundColor: '#4F46E5',
    justifyContent: 'center', alignItems: 'center',
  },
  filterRow: { paddingHorizontal: 16, marginBottom: 12, maxHeight: 44 },
  filterChip: {
    paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20,
    backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', marginRight: 8,
  },
  filterActive: { backgroundColor: '#4F46E5', borderColor: '#4F46E5' },
  filterText: { fontSize: 13, fontWeight: '600', color: '#64748B' },
  filterTextActive: { color: '#FFFFFF' },
  scrollContent: { paddingHorizontal: 20, paddingBottom: 100 },
  card: {
    backgroundColor: '#FFFFFF', borderRadius: 16, padding: 16, marginBottom: 10,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04, shadowRadius: 6, elevation: 2,
  },
  cardTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 },
  cardName: { fontSize: 16, fontWeight: '600', color: '#0F172A', marginBottom: 4 },
  cardMeta: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  metaText: { fontSize: 13, color: '#64748B', flex: 1 },
  badge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  badgeText: { fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },
  cardBottom: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  dateRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  dateText: { fontSize: 12, color: '#64748B' },
  price: { fontSize: 18, fontWeight: '700', color: '#4F46E5' },
  emptyState: { alignItems: 'center', paddingTop: 60 },
  emptyText: { fontSize: 16, color: '#94A3B8', marginTop: 12, marginBottom: 16 },
  emptyBtn: { backgroundColor: '#4F46E5', paddingHorizontal: 24, paddingVertical: 12, borderRadius: 12 },
  emptyBtnText: { color: '#FFFFFF', fontSize: 14, fontWeight: '700' },
});
