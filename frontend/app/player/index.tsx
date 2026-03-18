import React, { useEffect, useState, useRef, useCallback } from 'react';
import {
  View, Text, StyleSheet, ActivityIndicator, Image,
  Dimensions, AppState, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { devicesAPI } from '../../src/services/api';

const { width: SW, height: SH } = Dimensions.get('window');

export default function PlayerSplashScreen() {
  const router = useRouter();
  const [status, setStatus] = useState('Initializing...');

  useEffect(() => {
    initDevice();
  }, []);

  const initDevice = async () => {
    try {
      setStatus('Checking device registration...');
      const deviceId = await AsyncStorage.getItem('player_device_id');

      if (deviceId) {
        // Already registered, check activation
        setStatus('Checking activation...');
        try {
          const res = await devicesAPI.check(deviceId);
          if (res.data.status === 'active' && res.data.screen_id) {
            setStatus('Device active! Starting player...');
            setTimeout(() => router.replace('/player/display'), 1500);
            return;
          }
        } catch (e) {
          // Server unreachable, check if we have cached data
          const cachedPlaylist = await AsyncStorage.getItem('player_cached_playlist');
          if (cachedPlaylist) {
            setStatus('Offline mode - using cached content...');
            setTimeout(() => router.replace('/player/display'), 1500);
            return;
          }
        }
        // Not activated yet, go to activation screen
        setStatus('Waiting for activation...');
        setTimeout(() => router.replace('/player/activate'), 2000);
      } else {
        // First launch - register device
        setStatus('Registering device...');
        try {
          const res = await devicesAPI.register({
            device_name: `MediaView Player`,
            device_model: Platform.OS,
            os_version: Platform.Version?.toString() || 'unknown',
            app_version: '1.0.0',
            resolution: `${SW}x${SH}`,
          });
          await AsyncStorage.setItem('player_device_id', res.data.device_id);
          await AsyncStorage.setItem('player_activation_code', res.data.activation_code);
          setStatus('Device registered! Showing activation code...');
          setTimeout(() => router.replace('/player/activate'), 1500);
        } catch (e: any) {
          setStatus('Cannot connect to server. Check network and restart.');
        }
      }
    } catch (e) {
      setStatus('Error initializing device');
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.logoBox}>
        <View style={styles.logoIcon}>
          <Text style={styles.logoIconText}>TV</Text>
        </View>
      </View>
      <Text style={styles.appName}>MediaView</Text>
      <Text style={styles.appSub}>Digital Signage Player</Text>
      <ActivityIndicator size="large" color="#818CF8" style={styles.spinner} />
      <Text style={styles.status}>{status}</Text>
      <Text style={styles.version}>v1.0.0</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1, backgroundColor: '#0F0F1A', justifyContent: 'center', alignItems: 'center',
  },
  logoBox: { marginBottom: 24 },
  logoIcon: {
    width: 100, height: 100, borderRadius: 24, backgroundColor: '#4F46E5',
    justifyContent: 'center', alignItems: 'center',
  },
  logoIconText: { fontSize: 36, fontWeight: '800', color: '#FFFFFF' },
  appName: { fontSize: 42, fontWeight: '800', color: '#FFFFFF', letterSpacing: -1 },
  appSub: { fontSize: 18, color: '#818CF8', marginTop: 4 },
  spinner: { marginTop: 40 },
  status: { fontSize: 16, color: '#64748B', marginTop: 20, textAlign: 'center', paddingHorizontal: 40 },
  version: { position: 'absolute', bottom: 30, fontSize: 12, color: '#334155' },
});
