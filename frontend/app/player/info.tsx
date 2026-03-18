import React, { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Alert, Dimensions, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { devicesAPI } from '../../src/services/api';
import * as Device from 'expo-device';
import * as Network from 'expo-network';

const { width: SW, height: SH } = Dimensions.get('window');
const isLargeScreen = SW > 700;

export default function PlayerInfo() {
  const router = useRouter();
  const [info, setInfo] = useState<any>({});
  const [netInfo, setNetInfo] = useState<any>({});
  const [serverStatus, setServerStatus] = useState<any>(null);
  const [cachedCount, setCachedCount] = useState(0);
  const [serverError, setServerError] = useState<string | null>(null);

  useEffect(() => { load(); }, []);

  const load = async () => {
    const deviceId = await AsyncStorage.getItem('mv_device_id') || '';
    const code = await AsyncStorage.getItem('mv_activation_code') || '';
    const screenId = await AsyncStorage.getItem('mv_screen_id') || '';

    setInfo({ deviceId, code, screenId });

    // Cached media count
    try {
      const c = await AsyncStorage.getItem('mv_cached_playlist');
      if (c) setCachedCount(JSON.parse(c).length);
    } catch (e) {}

    // Network info
    try {
      const ip = await Network.getIpAddressAsync();
      const state = await Network.getNetworkStateAsync();
      setNetInfo({ ip, type: state.type, isConnected: state.isConnected });
    } catch (e) {
      setNetInfo({ ip: 'Unknown', type: 'Unknown', isConnected: false });
    }

    // Server status
    if (deviceId) {
      try {
        const res = await devicesAPI.check(deviceId);
        setServerStatus(res.data);
        setServerError(null);
      } catch (e: any) {
        setServerError(e.message || 'Cannot reach server');
      }
    }
  };

  const handleReset = () => {
    Alert.alert(
      'Reset Device',
      'This will unlink the device and clear all cached data. The device will need to be re-activated.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Reset', style: 'destructive', onPress: async () => {
          await AsyncStorage.multiRemove(['mv_device_id', 'mv_activation_code', 'mv_screen_id', 'mv_cached_playlist']);
          router.replace('/player');
        }},
      ]
    );
  };

  const rows = [
    { section: 'DEVICE' },
    { label: 'Device ID', value: info.deviceId || 'N/A' },
    { label: 'Activation Code', value: info.code || 'N/A', highlight: true },
    { label: 'Device Model', value: Device.modelName || 'Unknown' },
    { label: 'OS', value: `${Platform.OS} ${Device.osVersion || Platform.Version}` },
    { label: 'Screen Resolution', value: `${Math.round(SW)}x${Math.round(SH)}` },
    { label: 'App Version', value: 'v1.0.0' },
    { section: 'NETWORK' },
    { label: 'IP Address', value: netInfo.ip || 'Loading...' },
    { label: 'Network Type', value: netInfo.type || 'Unknown' },
    { label: 'Connected', value: netInfo.isConnected ? 'Yes' : 'No', color: netInfo.isConnected ? '#10B981' : '#EF4444' },
    { section: 'SERVER' },
    { label: 'Server Status', value: serverError || 'Connected', color: serverError ? '#EF4444' : '#10B981' },
    { label: 'Device Status', value: serverStatus?.status || 'Unknown', color: serverStatus?.status === 'active' ? '#10B981' : '#F59E0B' },
    { label: 'Screen Name', value: serverStatus?.screen_name || 'Not assigned' },
    { label: 'Screen ID', value: info.screenId || serverStatus?.screen_id || 'N/A' },
    { label: 'Activated At', value: serverStatus?.activated_at || 'N/A' },
    { section: 'CACHE' },
    { label: 'Cached Media Items', value: `${cachedCount}` },
  ];

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backText}>{"< Back"}</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Device Information</Text>
        <TouchableOpacity onPress={load} style={styles.refreshBtn}>
          <Text style={styles.refreshText}>Refresh</Text>
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {rows.map((row, i) => {
          if ('section' in row && row.section) {
            return (
              <Text key={i} style={styles.sectionTitle}>{row.section}</Text>
            );
          }
          return (
            <View key={i} style={styles.row}>
              <Text style={styles.label}>{row.label}</Text>
              <Text style={[
                styles.value,
                row.highlight && styles.valueHighlight,
                row.color ? { color: row.color } : {},
              ]} selectable>{row.value}</Text>
            </View>
          );
        })}

        <View style={styles.actionSection}>
          <TouchableOpacity style={styles.resetBtn} onPress={handleReset}>
            <Text style={styles.resetText}>Reset Device (Unlink & Clear Cache)</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#09090F' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: isLargeScreen ? 40 : 20, paddingTop: isLargeScreen ? 36 : 20, paddingBottom: 16,
  },
  backBtn: { backgroundColor: '#1E293B', paddingHorizontal: 16, paddingVertical: 10, borderRadius: 8 },
  backText: { fontSize: 14, fontWeight: '600', color: '#E2E8F0' },
  title: { fontSize: 18, fontWeight: '700', color: '#E2E8F0' },
  refreshBtn: { backgroundColor: '#1E293B', paddingHorizontal: 16, paddingVertical: 10, borderRadius: 8 },
  refreshText: { fontSize: 14, fontWeight: '600', color: '#818CF8' },
  content: { paddingHorizontal: isLargeScreen ? 40 : 20, paddingBottom: 40 },
  sectionTitle: {
    fontSize: 11, fontWeight: '700', color: '#6366F1', letterSpacing: 1.5,
    marginTop: 20, marginBottom: 8, paddingBottom: 6, borderBottomWidth: 1, borderBottomColor: '#1E293B',
  },
  row: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#111827',
  },
  label: { fontSize: 14, color: '#64748B', fontWeight: '500' },
  value: { fontSize: 14, color: '#E2E8F0', fontWeight: '600', maxWidth: '55%', textAlign: 'right' },
  valueHighlight: { color: '#A5B4FC', fontSize: 16, fontWeight: '800', letterSpacing: 2 },
  actionSection: { marginTop: 32 },
  resetBtn: {
    backgroundColor: '#1C1917', borderRadius: 12, paddingVertical: 16,
    alignItems: 'center', borderWidth: 1, borderColor: '#7F1D1D',
  },
  resetText: { fontSize: 15, fontWeight: '600', color: '#EF4444' },
});
