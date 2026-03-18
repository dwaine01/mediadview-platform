import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  RefreshControl, ActivityIndicator, TextInput, Dimensions, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { screensAPI } from '../../src/services/api';
import { Screen } from '../../src/types';
import { CITY_COLORS } from '../../src/constants/theme';

const { width: SW } = Dimensions.get('window');
const W = Platform.OS === 'web' && SW > 860;

export default function ScreensScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [screens, setScreens] = useState<Screen[]>([]);
  const [cities, setCities] = useState<string[]>([]);
  const [selectedCity, setSelectedCity] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [sr, cr] = await Promise.all([
        screensAPI.list(selectedCity ? { city: selectedCity } : {}),
        screensAPI.getCities(),
      ]);
      setScreens(sr.data);
      setCities(cr.data);
    } catch (e) {} finally { setLoading(false); setRefreshing(false); }
  }, [selectedCity]);

  useEffect(() => { setLoading(true); fetchData(); }, [fetchData]);

  const filtered = screens.filter(s =>
    s.name.toLowerCase().includes(search.toLowerCase()) ||
    s.location?.city?.toLowerCase().includes(search.toLowerCase())
  );
  const getC = (city: string) => CITY_COLORS[city] || '#6366F1';

  return (
    <View style={[$.ct, { paddingTop: W ? 28 : insets.top }]}>
      <View style={[$.hd, { paddingHorizontal: W ? 32 : 16 }]}>
        <View>
          <Text style={$.title}>Screen Marketplace</Text>
          <Text style={$.sub}>{screens.length} screens available</Text>
        </View>
      </View>

      <View style={{ paddingHorizontal: W ? 32 : 16 }}>
        <View style={$.search}>
          <Ionicons name="search" size={18} color="#64748B" />
          <TextInput style={$.searchInput} placeholder="Search screens..." placeholderTextColor="#475569" value={search} onChangeText={setSearch} />
          {search ? <TouchableOpacity onPress={() => setSearch('')}><Ionicons name="close-circle" size={18} color="#475569" /></TouchableOpacity> : null}
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 16, maxHeight: 40 }}>
          <TouchableOpacity style={[$.chip, !selectedCity && $.chipA]} onPress={() => setSelectedCity('')}>
            <Text style={[$.chipT, !selectedCity && $.chipTA]}>All Cities</Text>
          </TouchableOpacity>
          {cities.map(c => (
            <TouchableOpacity key={c} style={[$.chip, selectedCity === c && $.chipA]} onPress={() => setSelectedCity(selectedCity === c ? '' : c)}>
              <Text style={[$.chipT, selectedCity === c && $.chipTA]}>{c}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>

      {loading ? <View style={$.ctr}><ActivityIndicator size="large" color="#6366F1" /></View> : (
        <ScrollView contentContainerStyle={{ paddingHorizontal: W ? 32 : 16, paddingBottom: 100 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchData(); }} tintColor="#6366F1" />}>
          {filtered.length === 0 ? (
            <View style={$.empty}><Ionicons name="tv-outline" size={48} color="#374151" /><Text style={$.emptyT}>No screens found</Text></View>
          ) : (
            <View style={W ? $.grid : undefined}>
              {filtered.map(sc => (
                <TouchableOpacity key={sc.id} style={[$.card, W && { width: '31%' }]} onPress={() => router.push(`/screen/${sc.id}`)} activeOpacity={0.7}>
                  <View style={[$.cardImg, { backgroundColor: getC(sc.location?.city) }]}>
                    <Ionicons name="tv" size={32} color="rgba(255,255,255,0.2)" style={{ position: 'absolute', right: 14, top: 14 }} />
                    <View style={$.locBadge}>
                      <Ionicons name="location" size={11} color="#FFF" />
                      <Text style={$.locT}>{sc.location?.city}, {sc.location?.state}</Text>
                    </View>
                  </View>
                  <View style={$.cardBody}>
                    <Text style={$.cardName} numberOfLines={1}>{sc.name}</Text>
                    <Text style={$.cardAddr} numberOfLines={1}>{sc.location?.address}</Text>
                    <View style={$.cardFoot}>
                      <View style={$.spec}><Ionicons name="resize" size={13} color="#64748B" /><Text style={$.specT}>{sc.specs?.size}</Text></View>
                      <Text style={$.price}>${sc.pricing?.per_hour}<Text style={$.priceU}>/hr</Text></Text>
                    </View>
                  </View>
                </TouchableOpacity>
              ))}
            </View>
          )}
        </ScrollView>
      )}
    </View>
  );
}

const $ = StyleSheet.create({
  ct: { flex: 1, backgroundColor: '#0B0F1A' },
  ctr: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  hd: { paddingTop: 16, paddingBottom: 12 },
  title: { fontSize: 22, fontWeight: '700', color: '#F1F5F9' },
  sub: { fontSize: 13, color: '#64748B', marginTop: 2 },
  search: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: '#111827',
    borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10,
    borderWidth: 1, borderColor: '#1E293B', gap: 8, marginBottom: 12,
  },
  searchInput: { flex: 1, fontSize: 15, color: '#F1F5F9' },
  chip: { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20, backgroundColor: '#111827', borderWidth: 1, borderColor: '#1E293B', marginRight: 8 },
  chipA: { backgroundColor: '#6366F1', borderColor: '#6366F1' },
  chipT: { fontSize: 13, fontWeight: '600', color: '#64748B' },
  chipTA: { color: '#FFF' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 16 },
  card: { backgroundColor: '#111827', borderRadius: 16, marginBottom: 14, overflow: 'hidden', borderWidth: 1, borderColor: '#1E293B' },
  cardImg: { height: 110, justifyContent: 'flex-end', padding: 12 },
  locBadge: { flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.4)', paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, gap: 4, alignSelf: 'flex-start' },
  locT: { color: '#FFF', fontSize: 12, fontWeight: '600' },
  cardBody: { padding: 14 },
  cardName: { fontSize: 16, fontWeight: '700', color: '#F1F5F9', marginBottom: 2 },
  cardAddr: { fontSize: 13, color: '#64748B', marginBottom: 10 },
  cardFoot: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  spec: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  specT: { fontSize: 12, color: '#64748B' },
  price: { fontSize: 18, fontWeight: '700', color: '#22D3EE' },
  priceU: { fontSize: 12, fontWeight: '500', color: '#64748B' },
  empty: { alignItems: 'center', paddingTop: 60 },
  emptyT: { fontSize: 16, color: '#475569', marginTop: 12 },
});
