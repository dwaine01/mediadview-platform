import React, { useEffect, useState, useRef } from 'react';
import {
  View, Text, StyleSheet, Dimensions, TouchableOpacity,
} from 'react-native';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { devicesAPI } from '../../src/services/api';

const { width: SW } = Dimensions.get('window');

export default function PlayerActivateScreen() {
  const router = useRouter();
  const [code, setCode] = useState('------');
  const [deviceId, setDeviceId] = useState('');
  const [checking, setChecking] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    loadCode();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const loadCode = async () => {
    const id = await AsyncStorage.getItem('player_device_id');
    const savedCode = await AsyncStorage.getItem('player_activation_code');
    if (id) setDeviceId(id);
    if (savedCode) setCode(savedCode);

    // Start polling for activation
    if (id) {
      pollRef.current = setInterval(() => checkActivation(id), 5000);
    }
  };

  const checkActivation = async (id: string) => {
    try {
      setChecking(true);
      const res = await devicesAPI.check(id);
      if (res.data.status === 'active' && res.data.screen_id) {
        if (pollRef.current) clearInterval(pollRef.current);
        await AsyncStorage.setItem('player_screen_id', res.data.screen_id);
        router.replace('/player/display');
      }
    } catch (e) {
      // Server unreachable
    } finally {
      setChecking(false);
    }
  };

  const codeChars = code.split('');

  return (
    <View style={styles.container}>
      <View style={styles.topBar}>
        <View style={styles.logoRow}>
          <View style={styles.miniLogo}>
            <Text style={styles.miniLogoText}>TV</Text>
          </View>
          <Text style={styles.brandName}>MediaView Player</Text>
        </View>
        <View style={styles.statusDot}>
          <View style={[styles.dot, checking && styles.dotActive]} />
          <Text style={styles.statusText}>{checking ? 'Checking...' : 'Waiting for activation'}</Text>
        </View>
      </View>

      <View style={styles.center}>
        <Text style={styles.title}>Activation Code</Text>
        <Text style={styles.subtitle}>Enter this code in the MediaView Admin Panel to activate this screen</Text>

        <View style={styles.codeContainer}>
          {codeChars.map((char, i) => (
            <View key={i} style={styles.codeBox}>
              <Text style={styles.codeChar}>{char}</Text>
            </View>
          ))}
        </View>

        <View style={styles.divider} />

        <Text style={styles.instructions}>Steps to activate:</Text>
        <View style={styles.stepRow}>
          <View style={styles.stepNum}><Text style={styles.stepNumText}>1</Text></View>
          <Text style={styles.stepText}>Open MediaView Admin Panel on your computer</Text>
        </View>
        <View style={styles.stepRow}>
          <View style={styles.stepNum}><Text style={styles.stepNumText}>2</Text></View>
          <Text style={styles.stepText}>Go to Admin → Devices tab</Text>
        </View>
        <View style={styles.stepRow}>
          <View style={styles.stepNum}><Text style={styles.stepNumText}>3</Text></View>
          <Text style={styles.stepText}>Click "Activate Device" and enter the code above</Text>
        </View>
        <View style={styles.stepRow}>
          <View style={styles.stepNum}><Text style={styles.stepNumText}>4</Text></View>
          <Text style={styles.stepText}>Select the screen to assign and confirm</Text>
        </View>
      </View>

      <View style={styles.footer}>
        <Text style={styles.footerText}>Device ID: {deviceId.substring(0, 8)}...</Text>
        <TouchableOpacity onPress={() => router.push('/player/info')}>
          <Text style={styles.infoLink}>Technical Info</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0F0F1A' },
  topBar: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: 40, paddingTop: 40, paddingBottom: 20,
  },
  logoRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  miniLogo: {
    width: 40, height: 40, borderRadius: 10, backgroundColor: '#4F46E5',
    justifyContent: 'center', alignItems: 'center',
  },
  miniLogoText: { fontSize: 14, fontWeight: '800', color: '#FFF' },
  brandName: { fontSize: 18, fontWeight: '700', color: '#FFFFFF' },
  statusDot: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  dot: { width: 10, height: 10, borderRadius: 5, backgroundColor: '#F59E0B' },
  dotActive: { backgroundColor: '#10B981' },
  statusText: { fontSize: 14, color: '#94A3B8' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 40 },
  title: { fontSize: 32, fontWeight: '700', color: '#FFFFFF', marginBottom: 8 },
  subtitle: { fontSize: 16, color: '#94A3B8', textAlign: 'center', marginBottom: 32, maxWidth: 500 },
  codeContainer: { flexDirection: 'row', gap: 12, marginBottom: 40 },
  codeBox: {
    width: SW > 800 ? 80 : 50, height: SW > 800 ? 100 : 65, borderRadius: 16,
    backgroundColor: '#1E1B4B', borderWidth: 2, borderColor: '#4F46E5',
    justifyContent: 'center', alignItems: 'center',
  },
  codeChar: { fontSize: SW > 800 ? 48 : 32, fontWeight: '800', color: '#818CF8' },
  divider: { width: 200, height: 1, backgroundColor: '#1E293B', marginBottom: 32 },
  instructions: { fontSize: 16, fontWeight: '600', color: '#64748B', marginBottom: 16 },
  stepRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 12, maxWidth: 500 },
  stepNum: {
    width: 28, height: 28, borderRadius: 14, backgroundColor: '#1E293B',
    justifyContent: 'center', alignItems: 'center',
  },
  stepNumText: { fontSize: 13, fontWeight: '700', color: '#818CF8' },
  stepText: { fontSize: 14, color: '#94A3B8', flex: 1 },
  footer: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: 40, paddingBottom: 30,
  },
  footerText: { fontSize: 12, color: '#334155' },
  infoLink: { fontSize: 13, color: '#4F46E5', fontWeight: '600' },
});
