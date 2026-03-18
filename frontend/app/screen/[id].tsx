import React, { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, ActivityIndicator, TouchableOpacity,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { screensAPI } from '../../src/services/api';
import { Screen } from '../../src/types';
import { CITY_COLORS } from '../../src/constants/theme';

export default function ScreenDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [screen, setScreen] = useState<Screen | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (id) {
      screensAPI.get(id).then(res => {
        setScreen(res.data);
        setLoading(false);
      }).catch(() => setLoading(false));
    }
  }, [id]);

  if (loading) {
    return <View style={[styles.center, { paddingTop: insets.top }]}><ActivityIndicator size="large" color="#4F46E5" /></View>;
  }

  if (!screen) {
    return (
      <View style={[styles.center, { paddingTop: insets.top }]}>
        <Text style={styles.errorText}>Screen not found</Text>
      </View>
    );
  }

  const color = CITY_COLORS[screen.location?.city] || '#4F46E5';

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color="#0F172A" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Screen Details</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <View style={[styles.hero, { backgroundColor: color }]}>
          <Ionicons name="tv" size={56} color="rgba(255,255,255,0.2)" />
          <View style={styles.heroOverlay}>
            <Text style={styles.heroName}>{screen.name}</Text>
            <View style={styles.locationRow}>
              <Ionicons name="location" size={14} color="rgba(255,255,255,0.8)" />
              <Text style={styles.locationText}>{screen.location?.address}</Text>
            </View>
          </View>
        </View>

        <Text style={styles.description}>{screen.description}</Text>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Pricing</Text>
          <View style={styles.pricingGrid}>
            <View style={styles.priceItem}>
              <Text style={styles.priceAmount}>${screen.pricing?.per_hour}</Text>
              <Text style={styles.priceLabel}>Per Hour</Text>
            </View>
            <View style={styles.priceItem}>
              <Text style={styles.priceAmount}>${screen.pricing?.per_day?.toLocaleString()}</Text>
              <Text style={styles.priceLabel}>Per Day</Text>
            </View>
            <View style={styles.priceItem}>
              <Text style={styles.priceAmount}>${screen.pricing?.per_slot}</Text>
              <Text style={styles.priceLabel}>Per Slot</Text>
            </View>
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Specifications</Text>
          <View style={styles.specRow}>
            <Ionicons name="resize" size={16} color="#64748B" />
            <Text style={styles.specLabel}>Size:</Text>
            <Text style={styles.specValue}>{screen.specs?.size}</Text>
          </View>
          <View style={styles.specRow}>
            <Ionicons name="hardware-chip" size={16} color="#64748B" />
            <Text style={styles.specLabel}>Type:</Text>
            <Text style={styles.specValue}>{screen.specs?.type}</Text>
          </View>
          <View style={styles.specRow}>
            <Ionicons name="desktop" size={16} color="#64748B" />
            <Text style={styles.specLabel}>Resolution:</Text>
            <Text style={styles.specValue}>{screen.specs?.resolution}</Text>
          </View>
          <View style={styles.specRow}>
            <Ionicons name="phone-landscape" size={16} color="#64748B" />
            <Text style={styles.specLabel}>Orientation:</Text>
            <Text style={styles.specValue}>{screen.specs?.orientation}</Text>
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Location</Text>
          <Text style={styles.locationFull}>{screen.location?.address}</Text>
          <Text style={styles.locationCity}>{screen.location?.city}, {screen.location?.state} - {screen.location?.country}</Text>
          {screen.location?.lat && screen.location?.lng && (
            <Text style={styles.coords}>Lat: {screen.location.lat}, Lng: {screen.location.lng}</Text>
          )}
        </View>

        <TouchableOpacity
          style={styles.createBtn}
          onPress={() => router.push('/campaign/create')}
        >
          <Ionicons name="megaphone" size={20} color="#FFFFFF" />
          <Text style={styles.createBtnText}>Create Campaign for This Screen</Text>
        </TouchableOpacity>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F1F5F9' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#F1F5F9' },
  errorText: { fontSize: 16, color: '#64748B' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingVertical: 12,
  },
  backBtn: { width: 40, height: 40, borderRadius: 10, backgroundColor: '#FFFFFF', justifyContent: 'center', alignItems: 'center' },
  headerTitle: { fontSize: 18, fontWeight: '700', color: '#0F172A' },
  content: { paddingHorizontal: 20, paddingBottom: 40 },
  hero: {
    height: 160, borderRadius: 20, justifyContent: 'center', alignItems: 'center',
    marginBottom: 16, overflow: 'hidden',
  },
  heroOverlay: { position: 'absolute', bottom: 0, left: 0, right: 0, padding: 16 },
  heroName: { fontSize: 20, fontWeight: '700', color: '#FFFFFF' },
  locationRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 4 },
  locationText: { fontSize: 13, color: 'rgba(255,255,255,0.8)' },
  description: { fontSize: 14, color: '#64748B', lineHeight: 20, marginBottom: 16 },
  card: {
    backgroundColor: '#FFFFFF', borderRadius: 16, padding: 16, marginBottom: 12,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.04, shadowRadius: 6, elevation: 2,
  },
  cardTitle: { fontSize: 13, fontWeight: '600', color: '#64748B', textTransform: 'uppercase', marginBottom: 12 },
  pricingGrid: { flexDirection: 'row', justifyContent: 'space-around' },
  priceItem: { alignItems: 'center' },
  priceAmount: { fontSize: 22, fontWeight: '700', color: '#4F46E5' },
  priceLabel: { fontSize: 12, color: '#64748B', marginTop: 2 },
  specRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  specLabel: { fontSize: 14, color: '#64748B', width: 90 },
  specValue: { fontSize: 14, fontWeight: '600', color: '#0F172A' },
  locationFull: { fontSize: 15, fontWeight: '500', color: '#0F172A' },
  locationCity: { fontSize: 14, color: '#64748B', marginTop: 4 },
  coords: { fontSize: 12, color: '#94A3B8', marginTop: 4 },
  createBtn: {
    flexDirection: 'row', backgroundColor: '#4F46E5', borderRadius: 14,
    paddingVertical: 16, alignItems: 'center', justifyContent: 'center', gap: 8, marginTop: 8,
  },
  createBtnText: { color: '#FFFFFF', fontSize: 15, fontWeight: '700' },
});
