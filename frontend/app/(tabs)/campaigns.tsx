import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  RefreshControl, ActivityIndicator, Dimensions, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { campaignsAPI } from '../../src/services/api';
import { Campaign } from '../../src/types';
import { getStatusStyle } from '../../src/constants/theme';

const { width: SW } = Dimensions.get('window');
const W = Platform.OS === 'web' && SW > 860;
const FILTERS = ['all', 'draft', 'pending', 'approved', 'active', 'completed', 'rejected'];

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
    } catch (e) {} finally { setLoading(false); setRefreshing(false); }
  }, [filter]);

  useEffect(() => { setLoading(true); fetchData(); }, [fetchData]);

  return (
    <View style={[$.ct, { paddingTop: W ? 28 : insets.top }]}>
      <View style={[$.hd, { paddingHorizontal: W ? 32 : 16 }]}>
        <View>
          <Text style={$.title}>Campaigns</Text>
          <Text style={$.sub}>{campaigns.length} campaigns</Text>
        </View>
        <TouchableOpacity style={$.addBtn} onPress={() => router.push('/campaign/create')}>
          <Ionicons name="add" size={20} color="#FFF" />
          {W && <Text style={$.addBtnT}>New Campaign</Text>}
        </TouchableOpacity>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ paddingHorizontal: W ? 28 : 12, marginBottom: 12, maxHeight: 44 }}>
        {FILTERS.map(f => (
          <TouchableOpacity key={f} style={[$.chip, filter === f && $.chipA]} onPress={() => setFilter(f)}>
            <Text style={[$.chipT, filter === f && $.chipTA]}>{f.charAt(0).toUpperCase() + f.slice(1)}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {loading ? <View style={$.ctr}><ActivityIndicator size="large" color="#6366F1" /></View> : (
        <ScrollView contentContainerStyle={{ paddingHorizontal: W ? 32 : 16, paddingBottom: 100 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchData(); }} tintColor="#6366F1" />}>
          {campaigns.length === 0 ? (
            <View style={$.empty}>
              <Ionicons name="megaphone-outline" size={48} color="#374151" />
              <Text style={$.emptyT}>No campaigns found</Text>
              <TouchableOpacity style={$.emptyBtn} onPress={() => router.push('/campaign/create')}>
                <Text style={$.emptyBtnT}>Create Your First Campaign</Text>
              </TouchableOpacity>
            </View>
          ) : (
            campaigns.map(c => {
              const st = getStatusStyle(c.status);
              return (
                <TouchableOpacity key={c.id} style={$.card} onPress={() => router.push(`/campaign/${c.id}`)}>
                  <View style={$.cardTop}>
                    <View style={{ flex: 1 }}>
                      <Text style={$.cardName} numberOfLines={1}>{c.name}</Text>
                      <View style={$.meta}><Ionicons name="tv-outline" size={13} color="#64748B" /><Text style={$.metaT} numberOfLines={1}>{c.screen?.name || 'Screen'}</Text></View>
                    </View>
                    <View style={[$.badge, { backgroundColor: st.bg }]}>
                      <Text style={[$.badgeT, { color: st.text }]}>{c.status}</Text>
                    </View>
                  </View>
                  <View style={$.cardBot}>
                    <View style={$.meta}><Ionicons name="calendar-outline" size={13} color="#64748B" /><Text style={$.metaT}>{c.schedule?.start_date} - {c.schedule?.end_date}</Text></View>
                    <Text style={$.price}>${c.pricing?.total?.toLocaleString() || '0'}</Text>
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

const $ = StyleSheet.create({
  ct: { flex: 1, backgroundColor: '#0B0F1A' },
  ctr: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  hd: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingTop: 16, paddingBottom: 12 },
  title: { fontSize: 22, fontWeight: '700', color: '#F1F5F9' },
  sub: { fontSize: 13, color: '#64748B', marginTop: 2 },
  addBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#6366F1', paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10 },
  addBtnT: { color: '#FFF', fontSize: 13, fontWeight: '600' },
  chip: { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20, backgroundColor: '#111827', borderWidth: 1, borderColor: '#1E293B', marginRight: 8 },
  chipA: { backgroundColor: '#6366F1', borderColor: '#6366F1' },
  chipT: { fontSize: 13, fontWeight: '600', color: '#64748B' },
  chipTA: { color: '#FFF' },
  card: { backgroundColor: '#111827', borderRadius: 14, padding: 16, marginBottom: 10, borderWidth: 1, borderColor: '#1E293B' },
  cardTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 },
  cardName: { fontSize: 15, fontWeight: '600', color: '#F1F5F9', marginBottom: 4 },
  meta: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  metaT: { fontSize: 12, color: '#64748B' },
  badge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  badgeT: { fontSize: 10, fontWeight: '700', textTransform: 'uppercase' },
  cardBot: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  price: { fontSize: 18, fontWeight: '700', color: '#22D3EE' },
  empty: { alignItems: 'center', paddingTop: 60 },
  emptyT: { fontSize: 16, color: '#475569', marginTop: 12, marginBottom: 16 },
  emptyBtn: { backgroundColor: '#6366F1', paddingHorizontal: 24, paddingVertical: 12, borderRadius: 12 },
  emptyBtnT: { color: '#FFF', fontSize: 14, fontWeight: '700' },
});
