import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, RefreshControl, ActivityIndicator,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { paymentsAPI } from '../../src/services/api';
import { Payment } from '../../src/types';

export default function PaymentsScreen() {
  const insets = useSafeAreaInsets();
  const [payments, setPayments] = useState<Payment[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const res = await paymentsAPI.list();
      setPayments(res.data);
    } catch (e) {
      console.log('Payments fetch error:', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const formatDate = (d?: string) => d ? new Date(d).toLocaleDateString() : '';

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <Text style={styles.title}>Payment History</Text>
        <Text style={styles.subtitle}>{payments.length} transactions</Text>
      </View>

      {loading ? (
        <View style={styles.center}><ActivityIndicator size="large" color="#4F46E5" /></View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchData(); }} tintColor="#4F46E5" />}
        >
          {payments.length === 0 ? (
            <View style={styles.emptyState}>
              <Ionicons name="card-outline" size={48} color="#CBD5E1" />
              <Text style={styles.emptyText}>No payments yet</Text>
              <Text style={styles.emptySubtext}>Payments will appear here after campaign checkout</Text>
            </View>
          ) : (
            payments.map(p => (
              <View key={p.id} style={styles.card}>
                <View style={styles.cardHeader}>
                  <View style={styles.invoiceRow}>
                    <Ionicons name="receipt-outline" size={16} color="#4F46E5" />
                    <Text style={styles.invoiceNum}>{p.invoice_number}</Text>
                  </View>
                  <View style={[styles.statusBadge, { backgroundColor: p.status === 'completed' ? '#D1FAE5' : '#FEF3C7' }]}>
                    <Text style={[styles.statusText, { color: p.status === 'completed' ? '#065F46' : '#92400E' }]}>
                      {p.status}
                    </Text>
                  </View>
                </View>

                <Text style={styles.campaignName}>{p.campaign_name || 'Campaign'}</Text>
                <Text style={styles.screenName}>{p.screen_name || 'Screen'}</Text>

                <View style={styles.cardFooter}>
                  <View style={styles.methodRow}>
                    <Ionicons name="card" size={14} color="#64748B" />
                    <Text style={styles.methodText}>****{p.card_last4}</Text>
                  </View>
                  <Text style={styles.amount}>${p.amount?.toLocaleString()}</Text>
                </View>

                <Text style={styles.dateText}>{formatDate(p.created_at)}</Text>
              </View>
            ))
          )}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F1F5F9' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  header: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: 12 },
  title: { fontSize: 24, fontWeight: '700', color: '#0F172A' },
  subtitle: { fontSize: 13, color: '#64748B', marginTop: 2 },
  scrollContent: { paddingHorizontal: 20, paddingBottom: 100 },
  card: {
    backgroundColor: '#FFFFFF', borderRadius: 16, padding: 16, marginBottom: 10,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04, shadowRadius: 6, elevation: 2,
  },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  invoiceRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  invoiceNum: { fontSize: 13, fontWeight: '600', color: '#4F46E5' },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  statusText: { fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },
  campaignName: { fontSize: 15, fontWeight: '600', color: '#0F172A', marginBottom: 2 },
  screenName: { fontSize: 13, color: '#64748B', marginBottom: 10 },
  cardFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  methodRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  methodText: { fontSize: 13, color: '#64748B' },
  amount: { fontSize: 20, fontWeight: '700', color: '#0F172A' },
  dateText: { fontSize: 12, color: '#94A3B8', marginTop: 8 },
  emptyState: { alignItems: 'center', paddingTop: 60 },
  emptyText: { fontSize: 16, color: '#94A3B8', marginTop: 12 },
  emptySubtext: { fontSize: 13, color: '#CBD5E1', marginTop: 4, textAlign: 'center' },
});
