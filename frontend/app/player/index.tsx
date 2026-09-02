import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ActivityIndicator, Platform, Dimensions } from 'react-native';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { devicesAPI } from '../../src/services/api';
import * as Device from 'expo-device';

const { width: SW, height: SH } = Dimensions.get('window');

export default function PlayerSplash() {
  const router = useRouter();
  const [status, setStatus] = useState('Initializing MediaView Player...');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // boot runs once on mount — checks device registration and routes accordingly
    boot();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const boot = async () => {
    try {
      // Check if already registered
      const deviceId = await AsyncStorage.getItem('mv_device_id');

      if (deviceId) {
        setStatus('Checking activation status...');
        try {
          const res = await devicesAPI.check(deviceId);
          if (res.data.status === 'active' && res.data.screen_id) {
            await AsyncStorage.setItem('mv_screen_id', res.data.screen_id);
            setStatus('Device active. Loading player...');
            setTimeout(() => router.replace('/player/display'), 1200);
            return;
          }
          setStatus('Awaiting activation...');
          setTimeout(() => router.replace('/player/activate'), 1500);
        } catch {
          // Offline - check for cached content
          const cached = await AsyncStorage.getItem('mv_cached_playlist');
          if (cached && JSON.parse(cached).length > 0) {
            setStatus('Offline mode - loading cached content...');
            setTimeout(() => router.replace('/player/display'), 1200);
            return;
          }
          setStatus('Awaiting activation...');
          setTimeout(() => router.replace('/player/activate'), 2000);
        }
      } else {
        // First launch - register
        setStatus('Registering device...');
        try {
          const deviceName = Device.modelName || `MediaView Player`;
          const res = await devicesAPI.register({
            device_name: deviceName,
            device_model: Device.modelName || Platform.OS,
            os_version: Device.osVersion || Platform.Version?.toString() || 'unknown',
            app_version: '1.0.0',
            resolution: `${Math.round(SW)}x${Math.round(SH)}`,
            platform: Platform.OS === 'android' ? 'android_tv' : Platform.OS,
          });
          await AsyncStorage.setItem('mv_device_id', res.data.device_id);
          await AsyncStorage.setItem('mv_activation_code', res.data.activation_code);
          setStatus('Registration complete.');
          setTimeout(() => router.replace('/player/activate'), 1200);
        } catch {
          setError('Cannot connect to MediaView server.\nCheck network connection and restart the app.');
          // Retry after 10 seconds
          setTimeout(() => boot(), 10000);
        }
      }
    } catch {
      setError('Initialization error. Restarting...');
      setTimeout(() => boot(), 5000);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.logoBox}>
        <View style={styles.logoOuter}>
          <View style={styles.logoInner}>
            <Text style={styles.logoText}>MV</Text>
          </View>
        </View>
      </View>
      <Text style={styles.appName}>MediaView</Text>
      <Text style={styles.appSub}>Digital Signage Player</Text>

      {error ? (
        <View style={styles.errorBox}>
          <Text style={styles.errorIcon}>!</Text>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      ) : (
        <>
          <ActivityIndicator size="large" color="#818CF8" style={{ marginTop: 48 }} />
          <Text style={styles.statusText}>{status}</Text>
        </>
      )}

      <View style={styles.footer}>
        <Text style={styles.footerText}>MediaView Player v1.0.0</Text>
        <Text style={styles.footerText}>{Platform.OS} | {Math.round(SW)}x{Math.round(SH)}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#09090F', justifyContent: 'center', alignItems: 'center' },
  logoBox: { marginBottom: 28 },
  logoOuter: {
    width: 110, height: 110, borderRadius: 28, backgroundColor: '#1E1B4B',
    justifyContent: 'center', alignItems: 'center',
    borderWidth: 2, borderColor: '#312E81',
  },
  logoInner: {
    width: 80, height: 80, borderRadius: 20, backgroundColor: '#4F46E5',
    justifyContent: 'center', alignItems: 'center',
  },
  logoText: { fontSize: 32, fontWeight: '900', color: '#FFFFFF', letterSpacing: -1 },
  appName: { fontSize: 48, fontWeight: '800', color: '#FFFFFF', letterSpacing: -1.5 },
  appSub: { fontSize: 18, color: '#6366F1', marginTop: 4, fontWeight: '500' },
  statusText: { fontSize: 16, color: '#64748B', marginTop: 20, textAlign: 'center', maxWidth: 400 },
  errorBox: {
    marginTop: 40, backgroundColor: '#1C1917', borderWidth: 1, borderColor: '#7F1D1D',
    borderRadius: 16, padding: 20, maxWidth: 450, alignItems: 'center',
  },
  errorIcon: {
    fontSize: 24, fontWeight: '800', color: '#EF4444', backgroundColor: '#450A0A',
    width: 40, height: 40, borderRadius: 20, textAlign: 'center', lineHeight: 40, marginBottom: 12,
  },
  errorText: { fontSize: 15, color: '#FECACA', textAlign: 'center', lineHeight: 22 },
  footer: {
    position: 'absolute', bottom: 24, left: 0, right: 0,
    flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: 32,
  },
  footerText: { fontSize: 12, color: '#334155' },
});
