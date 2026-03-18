import React, { useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Dimensions, ScrollView, Platform,
} from 'react-native';
import { Tabs, useRouter, usePathname } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuthStore } from '../../src/store/authStore';

const { width: SW } = Dimensions.get('window');
const IS_WEB_WIDE = Platform.OS === 'web' && SW > 860;

const NAV_ITEMS = [
  { key: 'index', label: 'Dashboard', icon: 'grid' },
  { key: 'screens', label: 'Screens', icon: 'tv' },
  { key: 'campaigns', label: 'Campaigns', icon: 'megaphone' },
  { key: 'payments', label: 'Payments', icon: 'card' },
  { key: 'profile', label: 'Settings', icon: 'settings' },
];

export default function TabLayout() {
  const router = useRouter();
  const pathname = usePathname();
  const insets = useSafeAreaInsets();
  const { user } = useAuthStore();

  // Determine active tab from pathname
  const activeTab = NAV_ITEMS.find(n => {
    if (n.key === 'index') return pathname === '/' || pathname === '/(tabs)' || pathname === '/(tabs)/';
    return pathname.includes(n.key);
  })?.key || 'index';

  if (IS_WEB_WIDE) {
    // Desktop: Sidebar layout
    return (
      <View style={s.root}>
        <View style={[s.sidebar, { paddingTop: insets.top + 12 }]}>
          {/* Brand */}
          <View style={s.brand}>
            <View style={s.brandIcon}><Text style={s.brandIconText}>MV</Text></View>
            <View>
              <Text style={s.brandName}>MediaView</Text>
              <Text style={s.brandSub}>Digital Signage</Text>
            </View>
          </View>

          {/* Nav Items */}
          <View style={s.navList}>
            {NAV_ITEMS.map(item => {
              const active = activeTab === item.key;
              return (
                <TouchableOpacity
                  key={item.key}
                  style={[s.navItem, active && s.navItemActive]}
                  onPress={() => router.push(item.key === 'index' ? '/(tabs)' : `/(tabs)/${item.key}`)}
                >
                  <Ionicons name={(item.icon + (active ? '' : '-outline')) as any} size={20} color={active ? '#818CF8' : '#64748B'} />
                  <Text style={[s.navLabel, active && s.navLabelActive]}>{item.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          {/* Admin shortcut */}
          {user?.role === 'admin' && (
            <TouchableOpacity style={s.adminNav} onPress={() => router.push('/admin')}>
              <Ionicons name="shield-checkmark" size={18} color="#22D3EE" />
              <Text style={s.adminNavText}>Admin Panel</Text>
            </TouchableOpacity>
          )}

          {/* Devices link */}
          <TouchableOpacity style={s.adminNav} onPress={() => router.push('/admin')}>
            <Ionicons name="hardware-chip-outline" size={18} color="#64748B" />
            <Text style={[s.adminNavText, { color: '#64748B' }]}>Devices</Text>
          </TouchableOpacity>

          {/* User info */}
          <View style={s.sidebarFooter}>
            <View style={s.userAvatar}>
              <Text style={s.userAvatarText}>{user?.name?.charAt(0) || 'U'}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={s.userName} numberOfLines={1}>{user?.name}</Text>
              <Text style={s.userEmail} numberOfLines={1}>{user?.email}</Text>
            </View>
          </View>
        </View>

        {/* Main content */}
        <View style={s.mainContent}>
          <Tabs screenOptions={{ headerShown: false, tabBarStyle: { display: 'none' } }}>
            <Tabs.Screen name="index" />
            <Tabs.Screen name="screens" />
            <Tabs.Screen name="campaigns" />
            <Tabs.Screen name="payments" />
            <Tabs.Screen name="profile" />
          </Tabs>
        </View>
      </View>
    );
  }

  // Mobile: Bottom tabs (dark themed)
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: '#818CF8',
        tabBarInactiveTintColor: '#64748B',
        tabBarStyle: {
          backgroundColor: '#0F172A',
          borderTopColor: '#1E293B',
          borderTopWidth: 1,
          paddingBottom: Platform.OS === 'ios' ? 20 : 8,
          paddingTop: 8,
          height: Platform.OS === 'ios' ? 85 : 65,
        },
        tabBarLabelStyle: { fontSize: 11, fontWeight: '600' },
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Dashboard', tabBarIcon: ({ color }) => <Ionicons name="grid" size={22} color={color} /> }} />
      <Tabs.Screen name="screens" options={{ title: 'Screens', tabBarIcon: ({ color }) => <Ionicons name="tv" size={22} color={color} /> }} />
      <Tabs.Screen name="campaigns" options={{ title: 'Campaigns', tabBarIcon: ({ color }) => <Ionicons name="megaphone" size={22} color={color} /> }} />
      <Tabs.Screen name="payments" options={{ title: 'Payments', tabBarIcon: ({ color }) => <Ionicons name="card" size={22} color={color} /> }} />
      <Tabs.Screen name="profile" options={{ title: 'Settings', tabBarIcon: ({ color }) => <Ionicons name="settings" size={22} color={color} /> }} />
    </Tabs>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, flexDirection: 'row', backgroundColor: '#0B0F1A' },
  sidebar: {
    width: 240, backgroundColor: '#0F172A', borderRightWidth: 1,
    borderRightColor: '#1E293B', paddingHorizontal: 14, paddingBottom: 16,
    justifyContent: 'flex-start',
  },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 8, paddingVertical: 16, marginBottom: 8 },
  brandIcon: { width: 36, height: 36, borderRadius: 10, backgroundColor: '#6366F1', justifyContent: 'center', alignItems: 'center' },
  brandIconText: { fontSize: 14, fontWeight: '900', color: '#FFF' },
  brandName: { fontSize: 16, fontWeight: '700', color: '#F1F5F9' },
  brandSub: { fontSize: 10, color: '#64748B', marginTop: 1 },
  navList: { flex: 1 },
  navItem: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingVertical: 10, paddingHorizontal: 12, borderRadius: 10, marginBottom: 2,
  },
  navItemActive: { backgroundColor: 'rgba(99,102,241,0.12)' },
  navLabel: { fontSize: 14, color: '#94A3B8', fontWeight: '500' },
  navLabelActive: { color: '#818CF8', fontWeight: '600' },
  adminNav: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingVertical: 10, paddingHorizontal: 12, borderRadius: 10,
    marginBottom: 2, borderTopWidth: 1, borderTopColor: '#1E293B', marginTop: 4, paddingTop: 14,
  },
  adminNavText: { fontSize: 13, color: '#22D3EE', fontWeight: '600' },
  sidebarFooter: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingTop: 14, borderTopWidth: 1, borderTopColor: '#1E293B', marginTop: 8,
  },
  userAvatar: {
    width: 34, height: 34, borderRadius: 10, backgroundColor: '#1E293B',
    justifyContent: 'center', alignItems: 'center',
  },
  userAvatarText: { fontSize: 14, fontWeight: '700', color: '#818CF8' },
  userName: { fontSize: 13, fontWeight: '600', color: '#E2E8F0' },
  userEmail: { fontSize: 11, color: '#64748B' },
  mainContent: { flex: 1, backgroundColor: '#0B0F1A' },
});
