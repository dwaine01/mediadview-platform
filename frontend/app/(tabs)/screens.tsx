import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  RefreshControl, ActivityIndicator, TextInput,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { screensAPI } from '../../src/services/api';
import { Screen } from '../../src/types';
import { CITY_COLORS } from '../../src/constants/theme';

export default function ScreensScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [screens, setScreens] = useState<Screen[]>([]);
  const [cities, setCities] = useState<string[]>([]);
  const [selectedCity, setSelectedCity] = useState<string>('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [screensRes, citiesRes] = await Promise.all([
        screensAPI.list(selectedCity ? { city: selectedCity } : {}),
        screensAPI.getCities(),
      ]);
      setScreens(screensRes.data);
      setCities(citiesRes.data);
    } catch (e) {
      console.log('Screens fetch error:', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [selectedCity]);

  useEffect(() => { setLoading(true); fetchData(); }, [fetchData]);

  const filtered = screens.filter(s =>
    s.name.toLowerCase().includes(search.toLowerCase()) ||
    s.location?.city?.toLowerCase().includes(search.toLowerCase())
  );

  const getCityColor = (city: string) => CITY_COLORS[city] || '#4F46E5';

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.headerSection}>
        <Text style={styles.title}>Screen Marketplace</Text>
        <Text style={styles.subtitle}>{screens.length} screens available</Text>

        <View style={styles.searchWrapper}>
          <Ionicons name="search" size={18} color="#94A3B8" />
          <TextInput
            style={styles.searchInput}
            placeholder="Search screens..."
            placeholderTextColor="#94A3B8"
            value={search}
            onChangeText={setSearch}
          />
          {search ? (
            <TouchableOpacity onPress={() => setSearch('')}>
              <Ionicons name="close-circle" size={18} color="#94A3B8" />
            </TouchableOpacity>
          ) : null}
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.cityFilter}>
          <TouchableOpacity
            style={[styles.cityChip, !selectedCity && styles.cityChipActive]}
            onPress={() => setSelectedCity('')}
          >
            <Text style={[styles.cityChipText, !selectedCity && styles.cityChipTextActive]}>All Cities</Text>
          </TouchableOpacity>
          {cities.map(city => (
            <TouchableOpacity
              key={city}
              style={[styles.cityChip, selectedCity === city && styles.cityChipActive]}
              onPress={() => setSelectedCity(selectedCity === city ? '' : city)}
            >
              <Text style={[styles.cityChipText, selectedCity === city && styles.cityChipTextActive]}>{city}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color="#4F46E5" />
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchData(); }} tintColor="#4F46E5" />}
        >
          {filtered.length === 0 ? (
            <View style={styles.emptyState}>
              <Ionicons name="tv-outline" size={48} color="#CBD5E1" />
              <Text style={styles.emptyText}>No screens found</Text>
            </View>
          ) : (
            filtered.map(screen => (
              <TouchableOpacity
                key={screen.id}
                style={styles.screenCard}
                onPress={() => router.push(`/screen/${screen.id}`)}
                activeOpacity={0.8}
              >
                <View style={[styles.screenImage, { backgroundColor: getCityColor(screen.location?.city) }]}>
                  <Ionicons name="tv" size={36} color="rgba(255,255,255,0.3)" style={styles.screenBgIcon} />
                  <View style={styles.screenOverlay}>
                    <View style={styles.screenBadge}>
                      <Ionicons name="location" size={12} color="#FFFFFF" />
                      <Text style={styles.screenBadgeText}>{screen.location?.city}, {screen.location?.state}</Text>
                    </View>
                  </View>
                </View>
                <View style={styles.screenInfo}>
                  <Text style={styles.screenName} numberOfLines={1}>{screen.name}</Text>
                  <Text style={styles.screenAddress} numberOfLines={1}>{screen.location?.address}</Text>
                  <View style={styles.screenFooter}>
                    <View style={styles.screenSpec}>
                      <Ionicons name="resize" size={14} color="#64748B" />
                      <Text style={styles.specText}>{screen.specs?.size}</Text>
                    </View>
                    <Text style={styles.screenPrice}>
                      ${screen.pricing?.per_hour}<Text style={styles.priceUnit}>/hr</Text>
                    </Text>
                  </View>
                </View>
              </TouchableOpacity>
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
  headerSection: { paddingHorizontal: 20, paddingTop: 16 },
  title: { fontSize: 24, fontWeight: '700', color: '#0F172A' },
  subtitle: { fontSize: 13, color: '#64748B', marginTop: 2, marginBottom: 16 },
  searchWrapper: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: '#FFFFFF',
    borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10,
    borderWidth: 1, borderColor: '#E2E8F0', gap: 8,
  },
  searchInput: { flex: 1, fontSize: 15, color: '#0F172A' },
  cityFilter: { marginTop: 12, marginBottom: 12 },
  cityChip: {
    paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20,
    backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', marginRight: 8,
  },
  cityChipActive: { backgroundColor: '#4F46E5', borderColor: '#4F46E5' },
  cityChipText: { fontSize: 13, fontWeight: '600', color: '#64748B' },
  cityChipTextActive: { color: '#FFFFFF' },
  scrollContent: { paddingHorizontal: 20, paddingBottom: 100 },
  screenCard: {
    backgroundColor: '#FFFFFF', borderRadius: 16, marginBottom: 14, overflow: 'hidden',
    shadowColor: '#000', shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06, shadowRadius: 8, elevation: 3,
  },
  screenImage: {
    height: 120, justifyContent: 'flex-end', padding: 14,
  },
  screenBgIcon: { position: 'absolute', right: 16, top: 16 },
  screenOverlay: { flexDirection: 'row' },
  screenBadge: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.3)',
    paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, gap: 4,
  },
  screenBadgeText: { color: '#FFFFFF', fontSize: 12, fontWeight: '600' },
  screenInfo: { padding: 14 },
  screenName: { fontSize: 16, fontWeight: '700', color: '#0F172A', marginBottom: 2 },
  screenAddress: { fontSize: 13, color: '#64748B', marginBottom: 10 },
  screenFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  screenSpec: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  specText: { fontSize: 12, color: '#64748B' },
  screenPrice: { fontSize: 18, fontWeight: '700', color: '#4F46E5' },
  priceUnit: { fontSize: 12, fontWeight: '500', color: '#64748B' },
  emptyState: { alignItems: 'center', paddingTop: 60 },
  emptyText: { fontSize: 16, color: '#94A3B8', marginTop: 12 },
});
