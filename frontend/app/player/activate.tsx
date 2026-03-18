import React, { useEffect, useState, useRef } from 'react';
import { View, Text, StyleSheet, Dimensions, TouchableOpacity } from 'react-native';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { devicesAPI } from '../../src/services/api';

const { width: SW } = Dimensions.get('window');
const isLargeScreen = SW > 700;

export default function PlayerActivate() {
  const router = useRouter();
  const [code, setCode] = useState('------');
  const [deviceId, setDeviceId] = useState('');
  const [pollCount, setPollCount] = useState(0);
  const [serverOk, setServerOk] = useState(true);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    init();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const init = async () => {
    const id = await AsyncStorage.getItem('mv_device_id') || '';
    const savedCode = await AsyncStorage.getItem('mv_activation_code') || '';
    setDeviceId(id);
    setCode(savedCode);
    if (id) {
      pollRef.current = setInterval(() => poll(id), 5000);
    }
  };

  const poll = async (id: string) => {
    setPollCount(c => c + 1);
    try {
      const res = await devicesAPI.check(id);
      setServerOk(true);
      if (res.data.status === 'active' && res.data.screen_id) {
        if (pollRef.current) clearInterval(pollRef.current);
        await AsyncStorage.setItem('mv_screen_id', res.data.screen_id);
        router.replace('/player/display');
      }
    } catch (e) {
      setServerOk(false);
    }
  };

  return (
    <View style={styles.container}>
      {/* Top Bar */}
      <View style={styles.topBar}>
        <View style={styles.brandRow}>
          <View style={styles.miniLogo}><Text style={styles.miniLogoT}>MV</Text></View>
          <Text style={styles.brandName}>MediaView Player</Text>
        </View>
        <View style={styles.statusRow}>
          <View style={[styles.statusDot, { backgroundColor: serverOk ? '#F59E0B' : '#EF4444' }]} />
          <Text style={styles.statusLabel}>
            {serverOk ? 'Waiting for activation' : 'Server unreachable'}
          </Text>
          <Text style={styles.pollText}>Polling #{pollCount}</Text>
        </View>
      </View>

      {/* Center Content */}
      <View style={styles.center}>
        <Text style={styles.title}>Activation Code</Text>
        <Text style={styles.subtitle}>
          Enter this code in the MediaView Admin Panel{"\n"}to link this device to a screen
        </Text>

        <View style={styles.codeRow}>
          {code.split('').map((ch, i) => (
            <View key={i} style={styles.codeBox}>
              <Text style={styles.codeChar}>{ch}</Text>
            </View>
          ))}
        </View>

        <View style={styles.divider} />

        <Text style={styles.stepsTitle}>How to activate:</Text>
        {[
          'Open MediaView Admin Panel on your computer or phone',
          'Go to Admin Panel \u2192 Devices tab',
          'Click "Activate Device" and enter the code shown above',
          'Select the screen to assign and confirm',
        ].map((step, i) => (
          <View key={i} style={styles.stepRow}>
            <View style={styles.stepBadge}><Text style={styles.stepNum}>{i + 1}</Text></View>
            <Text style={styles.stepText}>{step}</Text>
          </View>
        ))}
      </View>

      {/* Footer */}
      <View style={styles.footer}>
        <Text style={styles.footerId}>Device: {deviceId.substring(0, 12)}...</Text>
        <TouchableOpacity onPress={() => router.push('/player/info')} style={styles.infoBtn}>
          <Text style={styles.infoBtnText}>Technical Info</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const BOX = isLargeScreen ? 80 : 52;
const FONT = isLargeScreen ? 44 : 28;

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#09090F' },
  topBar: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: isLargeScreen ? 48 : 20, paddingTop: isLargeScreen ? 36 : 20, paddingBottom: 16,
  },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  miniLogo: {
    width: 36, height: 36, borderRadius: 8, backgroundColor: '#4F46E5',
    justifyContent: 'center', alignItems: 'center',
  },
  miniLogoT: { fontSize: 13, fontWeight: '900', color: '#FFF' },
  brandName: { fontSize: 16, fontWeight: '700', color: '#E2E8F0' },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  statusLabel: { fontSize: 13, color: '#94A3B8' },
  pollText: { fontSize: 11, color: '#475569', marginLeft: 8 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 24 },
  title: { fontSize: isLargeScreen ? 36 : 26, fontWeight: '700', color: '#FFFFFF', marginBottom: 8 },
  subtitle: {
    fontSize: isLargeScreen ? 16 : 13, color: '#94A3B8', textAlign: 'center',
    marginBottom: 32, maxWidth: 520, lineHeight: 22,
  },
  codeRow: { flexDirection: 'row', gap: isLargeScreen ? 14 : 8 },
  codeBox: {
    width: BOX, height: BOX * 1.2, borderRadius: 14,
    backgroundColor: '#1E1B4B', borderWidth: 2, borderColor: '#4338CA',
    justifyContent: 'center', alignItems: 'center',
  },
  codeChar: { fontSize: FONT, fontWeight: '800', color: '#A5B4FC' },
  divider: { width: 160, height: 1, backgroundColor: '#1E293B', marginVertical: 28 },
  stepsTitle: { fontSize: 15, fontWeight: '600', color: '#64748B', marginBottom: 14 },
  stepRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 10,
    maxWidth: 500, width: '100%',
  },
  stepBadge: {
    width: 26, height: 26, borderRadius: 13, backgroundColor: '#1E293B',
    justifyContent: 'center', alignItems: 'center',
  },
  stepNum: { fontSize: 12, fontWeight: '700', color: '#818CF8' },
  stepText: { fontSize: 14, color: '#94A3B8', flex: 1 },
  footer: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: isLargeScreen ? 48 : 20, paddingBottom: isLargeScreen ? 28 : 16,
  },
  footerId: { fontSize: 11, color: '#334155' },
  infoBtn: { backgroundColor: '#1E293B', paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8 },
  infoBtnText: { fontSize: 13, fontWeight: '600', color: '#818CF8' },
});
