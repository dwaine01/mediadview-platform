import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, RefreshControl, ActivityIndicator,
  Dimensions, Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { paymentsAPI } from '../../src/services/api';
import { Payment } from '../../src/types';

const { width: SW } = Dimensions.get('window');
const W = Platform.OS === 'web' && SW > 860;

export default function PaymentsScreen() {
  const insets = useSafeAreaInsets();
  const [payments, setPayments] = useState<Payment[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async () => {
    try { const res = await paymentsAPI.list(); setPayments(res.data); }
    catch {} finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);
  const fmtDate = (d?: string) => d ? new Date(d).toLocaleDateString() : '';

  return (
    <View style={[$.ct, { paddingTop: W ? 28 : insets.top }]}>
      <View style={{ paddingHorizontal: W ? 32 : 16, paddingTop: 16, paddingBottom: 12 }}>
        <Text style={$.title}>Payment History</Text>
        <Text style={$.sub}>{payments.length} transactions</Text>
      </View>

      {loading ? <View style={$.ctr}><ActivityIndicator size="large" color="#6366F1" /></View> : (
        <ScrollView contentContainerStyle={{ paddingHorizontal: W ? 32 : 16, paddingBottom: 100 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchData(); }} tintColor="#6366F1" />}>
          {payments.length === 0 ? (
            <View style={$.empty}><Ionicons name="card-outline" size={48} color="#374151" /><Text style={$.emptyT}>No payments yet</Text><Text style={$.emptyS}>Payments appear after campaign checkout</Text></View>
          ) : (
            payments.map(p => (
              <View key={p.id} style={$.card}>
                <View style={$.row}>
                  <View style={$.invRow}><Ionicons name="receipt-outline" size={15} color="#6366F1" /><Text style={$.invNum}>{p.invoice_number}</Text></View>
                  <View style={[$.badge, { backgroundColor: p.status === 'completed' ? 'rgba(16,185,129,0.15)' : 'rgba(245,158,11,0.15)' }]}>
                    <Text style={[$.badgeT, { color: p.status === 'completed' ? '#34D399' : '#FBBF24' }]}>{p.status}</Text>
                  </View>
                </View>
                <Text style={$.campName}>{p.campaign_name || 'Campaign'}</Text>
                <Text style={$.scrName}>{p.screen_name || 'Screen'}</Text>
                <View style={$.row}>
                  <View style={$.invRow}><Ionicons name="card" size={14} color="#64748B" /><Text style={$.metaT}>****{p.card_last4}</Text></View>
                  <Text style={$.amount}>${p.amount?.toLocaleString()}</Text>
                </View>
                <Text style={$.dateT}>{fmtDate(p.created_at)}</Text>
              </View>
            ))
          )}
        </ScrollView>
      )}
    </View>
  );
}

const $ = StyleSheet.create({
  ct: { flex: 1, backgroundColor: '#0B0F1A' },
  ctr: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  title: { fontSize: 22, fontWeight: '700', color: '#F1F5F9' },
  sub: { fontSize: 13, color: '#64748B', marginTop: 2 },
  card: { backgroundColor: '#111827', borderRadius: 14, padding: 16, marginBottom: 10, borderWidth: 1, borderColor: '#1E293B' },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  invRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  invNum: { fontSize: 13, fontWeight: '600', color: '#818CF8' },
  badge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  badgeT: { fontSize: 10, fontWeight: '700', textTransform: 'uppercase' },
  campName: { fontSize: 15, fontWeight: '600', color: '#F1F5F9', marginBottom: 2 },
  scrName: { fontSize: 13, color: '#64748B', marginBottom: 10 },
  metaT: { fontSize: 13, color: '#64748B' },
  amount: { fontSize: 22, fontWeight: '700', color: '#22D3EE' },
  dateT: { fontSize: 12, color: '#475569', marginTop: 4 },
  empty: { alignItems: 'center', paddingTop: 60 },
  emptyT: { fontSize: 16, color: '#475569', marginTop: 12 },
  emptyS: { fontSize: 13, color: '#374151', marginTop: 4 },
});
