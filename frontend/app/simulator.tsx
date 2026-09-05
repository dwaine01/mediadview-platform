import React, { useEffect, useState, useRef, useCallback } from 'react';
import {
  View, Text, StyleSheet, ActivityIndicator, ScrollView, TouchableOpacity
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { playerAPI } from '../src/services/api';
import AsyncStorage from '@react-native-async-storage/async-storage';

type PlayerState = 'registering' | 'pending' | 'connected' | 'menu' | 'no_content' | 'error';

type MenuItem = {
  id: string; name: string; price: number; category?: string;
  description?: string; available: boolean;
};

type MenuData = {
  id: string; name: string; items: MenuItem[];
};

type ContentResponse = {
  status: string;
  activation_code?: string;
  device_id?: string;
  screen?: any;
  menu?: MenuData;
  message?: string;
};

const DEVICE_KEY = 'mv_player_device_id';

export default function PlayerSimulator() {
  const insets = useSafeAreaInsets();
  const [playerState, setPlayerState] = useState<PlayerState>('registering');
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const [activationCode, setActivationCode] = useState<string | null>(null);
  const [screenName, setScreenName] = useState<string | null>(null);
  const [menuData, setMenuData] = useState<MenuData | null>(null);
  const [error, setError] = useState('');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  const fetchContent = useCallback(async (dId: string) => {
    try {
      const res = await playerAPI.content(dId);
      const data: ContentResponse = res.data;
      if (data.status === 'pending') {
        setActivationCode(data.activation_code || null);
        setPlayerState('pending');
      } else if (data.status === 'menu') {
        setMenuData(data.menu || null);
        setScreenName(data.screen?.name || null);
        setPlayerState('menu');
        stopPolling();
      } else if (data.status === 'no_content') {
        setScreenName(data.screen?.name || null);
        setPlayerState('no_content');
      } else {
        setPlayerState('connected');
      }
    } catch (e: any) { setError(e.message || 'Network error'); }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        // Reuse existing device or register new one
        let dId = await AsyncStorage.getItem(DEVICE_KEY);
        if (!dId) {
          const res = await playerAPI.register({ device_name: 'MediaView Web Player' });
          dId = res.data.device_id || res.data.id;
          if (dId) await AsyncStorage.setItem(DEVICE_KEY, dId);
        }
        if (!dId) { setError('Failed to register device'); setPlayerState('error'); return; }
        setDeviceId(dId);
        await fetchContent(dId);
        // Poll for activation
        pollRef.current = setInterval(() => fetchContent(dId!), 4000);
      } catch (e: any) {
        setError(e.message || 'Failed to start player');
        setPlayerState('error');
      }
    })();
    return () => stopPolling();
  }, [fetchContent]);

  const reset = async () => {
    stopPolling();
    await AsyncStorage.removeItem(DEVICE_KEY);
    setDeviceId(null); setActivationCode(null); setMenuData(null); setScreenName(null); setError('');
    setPlayerState('registering');
    // Re-run setup
    try {
      const res = await playerAPI.register({ device_name: 'MediaView Web Player' });
      const dId = res.data.device_id || res.data.id;
      if (dId) { await AsyncStorage.setItem(DEVICE_KEY, dId); setDeviceId(dId); await fetchContent(dId); pollRef.current = setInterval(() => fetchContent(dId), 4000); }
    } catch (e: any) { setError(e.message); setPlayerState('error'); }
  };

  // Group items by category for menu display
  const grouped = (menuData?.items || []).reduce<Record<string, MenuItem[]>>((acc, item) => {
    if (!item.available) return acc;
    const cat = item.category || 'Menu';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(item);
    return acc;
  }, {});

  return (
    <View style={[ps.root, { paddingTop: insets.top }]}>
      {playerState === 'registering' && (
        <View style={ps.centered}>
          <ActivityIndicator color="#6366F1" size="large" />
          <Text style={ps.statusText}>Starting Player…</Text>
        </View>
      )}

      {playerState === 'error' && (
        <View style={ps.centered}>
          <Ionicons name="warning-outline" size={48} color="#F87171" />
          <Text style={ps.errorText}>{error}</Text>
          <TouchableOpacity style={ps.resetBtn} onPress={reset}>
            <Text style={ps.resetBtnText}>Try Again</Text>
          </TouchableOpacity>
        </View>
      )}

      {playerState === 'pending' && (
        <View style={ps.pendingScreen}>
          {/* Brand header */}
          <View style={ps.brand}>
            <View style={ps.brandDot} />
            <Text style={ps.brandText}>MediaView</Text>
          </View>

          <Text style={ps.pendingTitle}>Connect this screen</Text>
          <Text style={ps.pendingSubtitle}>Enter this code in your MediaView workspace</Text>

          {/* Big code display */}
          <View style={ps.codeBox}>
            <Text style={ps.codeText}>{activationCode || '------'}</Text>
          </View>

          <Text style={ps.pendingHint}>
            → Open your workspace at app.mediaview.com{`\n`}→ Go to Screens → Connect Screen{`\n`}→ Enter code above + screen name
          </Text>

          <View style={ps.pulseRow}>
            <ActivityIndicator color="#4B5563" size="small" />
            <Text style={ps.pulseText}>Waiting for connection…</Text>
          </View>

          <TouchableOpacity style={ps.resetLink} onPress={reset}>
            <Text style={ps.resetLinkText}>Reset device</Text>
          </TouchableOpacity>
        </View>
      )}

      {playerState === 'no_content' && (
        <View style={ps.pendingScreen}>
          <View style={ps.brand}><View style={ps.brandDotActive} /><Text style={ps.brandText}>MediaView</Text></View>
          <Ionicons name="checkmark-circle" size={56} color="#34D399" style={{ marginBottom: 16 }} />
          <Text style={ps.pendingTitle}>Screen Connected!</Text>
          <Text style={ps.pendingSubtitle}>{screenName}</Text>
          <Text style={ps.pendingHint}>No content published yet.{`\n`}Go to Menus in your workspace and publish a menu.</Text>
          <View style={ps.pulseRow}><ActivityIndicator color="#4B5563" size="small" /><Text style={ps.pulseText}>Waiting for content…</Text></View>
        </View>
      )}

      {playerState === 'menu' && menuData && (
        <ScrollView style={ps.menuRoot} contentContainerStyle={ps.menuContent}>
          {/* Screen info bar */}
          <View style={ps.screenBar}>
            <View style={ps.liveDot} />
            <Text style={ps.screenBarText}>{screenName} · MediaView</Text>
          </View>

          {/* Menu title */}
          <Text style={ps.menuTitle}>{menuData.name}</Text>

          {/* Items by category */}
          {Object.entries(grouped).map(([cat, items]) => (
            <View key={cat} style={ps.catSection}>
              <Text style={ps.catHeader}>{cat}</Text>
              {items.map(item => (
                <View key={item.id} style={ps.menuItem}>
                  <View style={ps.menuItemBody}>
                    <Text style={ps.menuItemName}>{item.name}</Text>
                    {!!item.description && <Text style={ps.menuItemDesc}>{item.description}</Text>}
                  </View>
                  <Text style={ps.menuItemPrice}>${Number(item.price).toFixed(2)}</Text>
                </View>
              ))}
            </View>
          ))}

          {Object.keys(grouped).length === 0 && (
            <View style={ps.centered}><Text style={{ color: '#64748B', textAlign: 'center' }}>No available items on this menu.</Text></View>
          )}
        </ScrollView>
      )}
    </View>
  );
}

const ps = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#020617' },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 32, gap: 16 },
  statusText: { color: '#64748B', fontSize: 14, marginTop: 8 },
  errorText: { color: '#F87171', fontSize: 14, textAlign: 'center' },
  resetBtn: { backgroundColor: '#1E293B', borderRadius: 10, paddingHorizontal: 20, paddingVertical: 10 },
  resetBtnText: { color: '#9CA3AF', fontSize: 13, fontWeight: '600' },
  pendingScreen: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 40, gap: 16 },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 24 },
  brandDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: '#6366F1' },
  brandDotActive: { width: 10, height: 10, borderRadius: 5, backgroundColor: '#34D399' },
  brandText: { fontSize: 16, fontWeight: '700', color: '#4B5563', letterSpacing: 1 },
  pendingTitle: { fontSize: 28, fontWeight: '800', color: '#F1F5F9', textAlign: 'center' },
  pendingSubtitle: { fontSize: 15, color: '#64748B', textAlign: 'center' },
  codeBox: { backgroundColor: '#0F172A', borderWidth: 2, borderColor: '#6366F1', borderRadius: 20, paddingHorizontal: 40, paddingVertical: 24, marginVertical: 8 },
  codeText: { fontSize: 52, fontWeight: '900', color: '#F1F5F9', letterSpacing: 12, fontVariant: ['tabular-nums'] },
  pendingHint: { fontSize: 13, color: '#374151', textAlign: 'center', lineHeight: 22 },
  pulseRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 },
  pulseText: { fontSize: 12, color: '#374151' },
  resetLink: { marginTop: 16 },
  resetLinkText: { fontSize: 12, color: '#374151', textDecorationLine: 'underline' },
  menuRoot: { flex: 1, backgroundColor: '#020617' },
  menuContent: { padding: 32, paddingBottom: 60 },
  screenBar: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 24 },
  liveDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#34D399' },
  screenBarText: { fontSize: 12, color: '#374151', letterSpacing: 0.5 },
  menuTitle: { fontSize: 40, fontWeight: '900', color: '#F8FAFC', marginBottom: 32 },
  catSection: { marginBottom: 28 },
  catHeader: { fontSize: 14, fontWeight: '700', color: '#6366F1', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 14, paddingBottom: 8, borderBottomWidth: 1, borderBottomColor: '#1E293B' },
  menuItem: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#0F172A' },
  menuItemBody: { flex: 1, paddingRight: 16 },
  menuItemName: { fontSize: 18, fontWeight: '700', color: '#F1F5F9' },
  menuItemDesc: { fontSize: 13, color: '#64748B', marginTop: 3 },
  menuItemPrice: { fontSize: 18, fontWeight: '800', color: '#34D399' },
});
