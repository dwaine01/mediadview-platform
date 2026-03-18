import React, { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
} from 'react-native';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { devicesAPI } from '../../src/services/api';

export default function PlayerInfoScreen() {
  const router = useRouter();
  const [deviceId, setDeviceId] = useState('');
  const [code, setCode] = useState('');
  const [deviceStatus, setDeviceStatus] = useState<any>(null);
  const [cachedCount, setCachedCount] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { loadInfo(); }, []);

  const loadInfo = async () => {
    const id = await AsyncStorage.getItem('player_device_id') || '';
    const savedCode = await AsyncStorage.getItem('player_activation_code') || '';
    setDeviceId(id);
    setCode(savedCode);

    // Check cached playlist
    try {
      const cached = await AsyncStorage.getItem('player_cached_playlist');
      if (cached) setCachedCount(JSON.parse(cached).length);
    } catch (e) {}

    // Fetch status from server
    if (id) {
      try {
        const res = await devicesAPI.check(id);
        setDeviceStatus(res.data);
      } catch (e: any) {
        setError('Cannot connect to server');
      }
    }
  };

  const handleReset = async () => {
    await AsyncStorage.removeItem('player_device_id');
    await AsyncStorage.removeItem('player_activation_code');
    await AsyncStorage.removeItem('player_screen_id');
    await AsyncStorage.removeItem('player_cached_playlist');
    router.replace('/player');
  };

  const rows = [
    { label: 'Device ID', value: deviceId },
    { label: 'Activation Code', value: code },
    { label: 'Status', value: deviceStatus?.status || 'Unknown' },
    { label: 'Screen ID', value: deviceStatus?.screen_id || 'Not assigned' },
    { label: 'Screen Name', value: deviceStatus?.screen_name || 'N/A' },
    { label: 'Resolution', value: deviceStatus?.screen_resolution || 'N/A' },
    { label: 'Activated At', value: deviceStatus?.activated_at || 'N/A' },
    { label: 'Cached Media', value: `${cachedCount} items` },
    { label: 'Server Connection', value: error || 'Connected' },
    { label: 'App Version', value: 'v1.0.0' },
  ];

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backText}>Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Device Information</Text>
        <View style={{ width: 60 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {rows.map((row, i) => (
          <View key={i} style={styles.row}>
            <Text style={styles.label}>{row.label}</Text>
            <Text style={[
              styles.value,
              row.label === 'Status' && row.value === 'active' && styles.valueGreen,
              row.label === 'Status' && row.value === 'pending' && styles.valueYellow,
              row.label === 'Server Connection' && row.value !== 'Connected' && styles.valueRed,
            ]} selectable>{row.value}</Text>
          </View>
        ))}

        <View style={styles.divider} />

        <TouchableOpacity style={styles.refreshBtn} onPress={loadInfo}>
          <Text style={styles.refreshText}>Refresh Status</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.resetBtn} onPress={handleReset}>
          <Text style={styles.resetText}>Reset Device (Unlink)</Text>
        </TouchableOpacity>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0F0F1A' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 30, paddingTop: 40, paddingBottom: 20,
  },
  backBtn: { paddingVertical: 8, paddingHorizontal: 16, backgroundColor: '#1E293B', borderRadius: 8 },
  backText: { fontSize: 14, fontWeight: '600', color: '#FFFFFF' },
  title: { fontSize: 20, fontWeight: '700', color: '#FFFFFF' },
  content: { paddingHorizontal: 30, paddingBottom: 40 },
  row: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: '#1E293B',
  },
  label: { fontSize: 14, color: '#64748B', fontWeight: '500' },
  value: { fontSize: 14, color: '#FFFFFF', fontWeight: '600', maxWidth: '60%', textAlign: 'right' },
  valueGreen: { color: '#10B981' },
  valueYellow: { color: '#F59E0B' },
  valueRed: { color: '#EF4444' },
  divider: { height: 1, backgroundColor: '#1E293B', marginVertical: 24 },
  refreshBtn: {
    backgroundColor: '#1E293B', borderRadius: 12, paddingVertical: 14,
    alignItems: 'center', marginBottom: 12,
  },
  refreshText: { fontSize: 15, fontWeight: '600', color: '#818CF8' },
  resetBtn: {
    backgroundColor: '#1C1917', borderRadius: 12, paddingVertical: 14,
    alignItems: 'center', borderWidth: 1, borderColor: '#7F1D1D',
  },
  resetText: { fontSize: 15, fontWeight: '600', color: '#EF4444' },
});
