import React, { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, ActivityIndicator, TouchableOpacity,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { campaignsAPI } from '../../src/services/api';
import { Campaign } from '../../src/types';
import { getStatusStyle } from '../../src/constants/theme';

export default function CampaignDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (id) {
      campaignsAPI.get(id).then(res => {
        setCampaign(res.data);
        setLoading(false);
      }).catch(() => setLoading(false));
    }
  }, [id]);

  if (loading) {
    return <View style={[styles.center, { paddingTop: insets.top }]}><ActivityIndicator size="large" color="#4F46E5" /></View>;
  }

  if (!campaign) {
    return (
      <View style={[styles.center, { paddingTop: insets.top }]}>
        <Text style={styles.errorText}>Campaign not found</Text>
        <TouchableOpacity onPress={() => router.back()}>
          <Text style={styles.linkText}>Go Back</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const st = getStatusStyle(campaign.status);

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color="#0F172A" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Campaign Details</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.titleRow}>
          <Text style={styles.name}>{campaign.name}</Text>
          <View style={[styles.badge, { backgroundColor: st.bg }]}>
            <Text style={[styles.badgeText, { color: st.text }]}>{campaign.status}</Text>
          </View>
        </View>

        {campaign.admin_notes && (
          <View style={styles.notesCard}>
            <Ionicons name="chatbubble-outline" size={16} color="#92400E" />
            <Text style={styles.notesText}>{campaign.admin_notes}</Text>
          </View>
        )}

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Screen</Text>
          <Text style={styles.cardValue}>{campaign.screen?.name || 'N/A'}</Text>
          <Text style={styles.cardSub}>
            {campaign.screen?.location?.city}, {campaign.screen?.location?.state}
          </Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Schedule</Text>
          <View style={styles.infoRow}>
            <Ionicons name="calendar" size={16} color="#64748B" />
            <Text style={styles.infoText}>{campaign.schedule?.start_date} - {campaign.schedule?.end_date}</Text>
          </View>
          <View style={styles.infoRow}>
            <Ionicons name="time" size={16} color="#64748B" />
            <Text style={styles.infoText}>{campaign.schedule?.start_time} - {campaign.schedule?.end_time}</Text>
          </View>
          <View style={styles.infoRow}>
            <Ionicons name="timer" size={16} color="#64748B" />
            <Text style={styles.infoText}>{campaign.schedule?.slot_duration}s slots, every {campaign.schedule?.frequency} min</Text>
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Pricing</Text>
          <View style={styles.priceRow}>
            <Text style={styles.priceLabel}>Subtotal</Text>
            <Text style={styles.priceValue}>${campaign.pricing?.subtotal?.toLocaleString()}</Text>
          </View>
          <View style={styles.priceRow}>
            <Text style={styles.priceLabel}>Tax</Text>
            <Text style={styles.priceValue}>${campaign.pricing?.tax?.toLocaleString()}</Text>
          </View>
          <View style={styles.divider} />
          <View style={styles.priceRow}>
            <Text style={styles.totalLabel}>Total</Text>
            <Text style={styles.totalValue}>${campaign.pricing?.total?.toLocaleString()}</Text>
          </View>
        </View>

        {campaign.media && campaign.media.length > 0 && (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Media ({campaign.media.length})</Text>
            {campaign.media.map(m => (
              <View key={m.id} style={styles.mediaRow}>
                <Ionicons name={m.type === 'image' ? 'image' : 'videocam'} size={18} color="#4F46E5" />
                <View style={{ flex: 1 }}>
                  <Text style={styles.mediaName}>{m.filename}</Text>
                  <Text style={styles.mediaSub}>{m.content_type} - {(m.size / 1024).toFixed(1)} KB</Text>
                </View>
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F1F5F9' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#F1F5F9' },
  errorText: { fontSize: 16, color: '#64748B', marginBottom: 12 },
  linkText: { fontSize: 14, color: '#4F46E5', fontWeight: '600' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingVertical: 12,
  },
  backBtn: { width: 40, height: 40, borderRadius: 10, backgroundColor: '#FFFFFF', justifyContent: 'center', alignItems: 'center' },
  headerTitle: { fontSize: 18, fontWeight: '700', color: '#0F172A' },
  content: { paddingHorizontal: 20, paddingBottom: 40 },
  titleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  name: { fontSize: 22, fontWeight: '700', color: '#0F172A', flex: 1, marginRight: 12 },
  badge: { paddingHorizontal: 12, paddingVertical: 5, borderRadius: 8 },
  badgeText: { fontSize: 12, fontWeight: '700', textTransform: 'uppercase' },
  notesCard: {
    flexDirection: 'row', gap: 8, backgroundColor: '#FEF3C7',
    padding: 14, borderRadius: 12, marginBottom: 16,
  },
  notesText: { flex: 1, fontSize: 13, color: '#92400E' },
  card: {
    backgroundColor: '#FFFFFF', borderRadius: 16, padding: 16, marginBottom: 12,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.04, shadowRadius: 6, elevation: 2,
  },
  cardTitle: { fontSize: 13, fontWeight: '600', color: '#64748B', textTransform: 'uppercase', marginBottom: 10 },
  cardValue: { fontSize: 16, fontWeight: '600', color: '#0F172A' },
  cardSub: { fontSize: 13, color: '#64748B', marginTop: 2 },
  infoRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  infoText: { fontSize: 14, color: '#0F172A' },
  priceRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  priceLabel: { fontSize: 14, color: '#64748B' },
  priceValue: { fontSize: 14, fontWeight: '500', color: '#0F172A' },
  divider: { height: 1, backgroundColor: '#E2E8F0', marginVertical: 8 },
  totalLabel: { fontSize: 16, fontWeight: '700', color: '#0F172A' },
  totalValue: { fontSize: 20, fontWeight: '700', color: '#4F46E5' },
  mediaRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    padding: 10, backgroundColor: '#F8FAFC', borderRadius: 10, marginBottom: 6,
  },
  mediaName: { fontSize: 14, fontWeight: '500', color: '#0F172A' },
  mediaSub: { fontSize: 12, color: '#94A3B8' },
});
