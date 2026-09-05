import React from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, useWindowDimensions, Platform, ScrollView,
} from 'react-native';
import { useRouter, usePathname, Slot } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useAuthStore } from '../../src/store/authStore';

const WS_NAV = [
  { key: 'index', label: 'Dashboard', icon: 'grid' as const, path: '/workspace' },
  { key: 'screens', label: 'Screens', icon: 'tv' as const, path: '/workspace/screens' },
  { key: 'menus', label: 'Menus', icon: 'fast-food' as const, path: '/workspace/menus' },
  { key: 'content', label: 'Content', icon: 'images' as const, path: '/workspace/content' },
  { key: 'playlists', label: 'Playlists', icon: 'list' as const, path: '/workspace/playlists' },
  { key: 'schedules', label: 'Schedules', icon: 'calendar' as const, path: '/workspace/schedules' },
  { key: 'users', label: 'Team', icon: 'people' as const, path: '/workspace/users' },
  { key: 'billing', label: 'Billing', icon: 'card' as const, path: '/workspace/billing' },
  { key: 'settings', label: 'Settings', icon: 'settings' as const, path: '/workspace/settings' },
];

export default function WorkspaceLayout() {
  const router = useRouter();
  const pathname = usePathname();
  const insets = useSafeAreaInsets();
  const { user, logout } = useAuthStore();
  const { width: SW } = useWindowDimensions();
  const IS_WEB_WIDE = Platform.OS === 'web' && SW > 860;

  const activeKey = WS_NAV.find(n => {
    if (n.key === 'index') return pathname === '/workspace' || pathname === '/workspace/';
    return pathname.startsWith(n.path);
  })?.key || 'index';

  const handleLogout = async () => {
    await logout();
    router.replace('/(auth)/login');
  };

  if (IS_WEB_WIDE) {
  return (
    <View style={[ws.root, { flexDirection: 'row' }]}>
        {/* Sidebar */}
        <View style={[ws.sidebar, { paddingTop: insets.top + 12 }]}>
          {/* Brand */}
          <View style={ws.brand}>
            <View style={ws.brandIcon}><Text style={ws.brandIconText}>MV</Text></View>
            <View>
              <Text style={ws.brandName}>MediaView</Text>
              <Text style={ws.brandSub}>Customer Workspace</Text>
            </View>
          </View>

          {/* Nav */}
          <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false}>
            <View style={ws.navSection}>
              <Text style={ws.navSectionLabel}>WORKSPACE</Text>
              {WS_NAV.map(item => {
                const active = activeKey === item.key;
                return (
                  <TouchableOpacity
                    key={item.key}
                    style={[ws.navItem, active && ws.navItemActive]}
                    onPress={() => router.push(item.path as any)}
                    activeOpacity={0.7}
                  >
                    <Ionicons
                      name={(item.icon + (active ? '' : '-outline')) as any}
                      size={19}
                      color={active ? '#818CF8' : '#64748B'}
                    />
                    <Text style={[ws.navLabel, active && ws.navLabelActive]}>{item.label}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </ScrollView>

          {/* Footer */}
          <View style={[ws.sidebarFooter, { paddingBottom: insets.bottom + 8 }]}>
            <View style={ws.userAvatar}>
              <Text style={ws.userAvatarText}>{user?.name?.charAt(0)?.toUpperCase() || 'U'}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={ws.userName} numberOfLines={1}>{user?.name || 'Customer'}</Text>
              <Text style={ws.userEmail} numberOfLines={1}>{user?.email || ''}</Text>
            </View>
            <TouchableOpacity onPress={handleLogout} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
              <Ionicons name="log-out-outline" size={20} color="#64748B" />
            </TouchableOpacity>
          </View>
        </View>

        {/* Main */}
        <View style={ws.main}>
          <Slot />
        </View>
      </View>
    );
  }

  // Mobile: Drawer-style header + bottom nav
  return (
    <View style={[ws.root, { paddingTop: 0 }]}>
      {/* Mobile Header */}
      <View style={[ws.mobileHeader, { paddingTop: insets.top }]}>
        <View style={ws.mobileBrand}>
          <View style={ws.brandIcon}><Text style={ws.brandIconText}>MV</Text></View>
          <View>
            <Text style={ws.brandName}>MediaView</Text>
            <Text style={ws.brandSub}>Customer Workspace</Text>
          </View>
        </View>
        <TouchableOpacity onPress={handleLogout} style={ws.logoutBtn}>
          <Ionicons name="log-out-outline" size={22} color="#64748B" />
        </TouchableOpacity>
      </View>

      {/* Content */}
      <View style={{ flex: 1 }}>
        <Slot />
      </View>

      {/* Bottom Nav */}
      <View style={[ws.bottomNav, { paddingBottom: insets.bottom }]}>
        {WS_NAV.slice(0, 5).map(item => {
          const active = activeKey === item.key;
          return (
            <TouchableOpacity
              key={item.key}
              style={ws.bottomNavItem}
              onPress={() => router.push(item.path as any)}
              activeOpacity={0.7}
            >
              <Ionicons
                name={(item.icon + (active ? '' : '-outline')) as any}
                size={22}
                color={active ? '#818CF8' : '#64748B'}
              />
              <Text style={[ws.bottomNavLabel, active && { color: '#818CF8' }]}>{item.label}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

const ws = StyleSheet.create({
  root: { flex: 1, flexDirection: 'row', backgroundColor: '#0B0F1A' },

  // Sidebar (web)
  sidebar: {
    width: 240, backgroundColor: '#0F172A', borderRightWidth: 1,
    borderRightColor: '#1E293B', paddingHorizontal: 14, paddingBottom: 16,
  },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 8, paddingVertical: 14, marginBottom: 8 },
  brandIcon: { width: 36, height: 36, borderRadius: 10, backgroundColor: '#6366F1', justifyContent: 'center', alignItems: 'center' },
  brandIconText: { fontSize: 14, fontWeight: '900', color: '#FFF' },
  brandName: { fontSize: 15, fontWeight: '700', color: '#F1F5F9' },
  brandSub: { fontSize: 10, color: '#64748B', marginTop: 1 },
  navSection: { paddingTop: 4 },
  navSectionLabel: { fontSize: 10, fontWeight: '700', color: '#374151', letterSpacing: 1.5, paddingHorizontal: 12, marginBottom: 6 },
  navItem: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingVertical: 10, paddingHorizontal: 12, borderRadius: 10, marginBottom: 2,
  },
  navItemActive: { backgroundColor: 'rgba(99,102,241,0.12)' },
  navLabel: { fontSize: 14, color: '#94A3B8', fontWeight: '500' },
  navLabelActive: { color: '#818CF8', fontWeight: '600' },
  sidebarFooter: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingTop: 14, borderTopWidth: 1, borderTopColor: '#1E293B', marginTop: 8,
  },
  userAvatar: { width: 34, height: 34, borderRadius: 10, backgroundColor: '#312E81', justifyContent: 'center', alignItems: 'center' },
  userAvatarText: { fontSize: 14, fontWeight: '700', color: '#818CF8' },
  userName: { fontSize: 13, fontWeight: '600', color: '#E2E8F0' },
  userEmail: { fontSize: 11, color: '#64748B' },
  main: { flex: 1, overflow: 'hidden' },

  // Mobile
  mobileHeader: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 20, paddingBottom: 12,
    backgroundColor: '#0F172A', borderBottomWidth: 1, borderBottomColor: '#1E293B',
  },
  mobileBrand: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  logoutBtn: { padding: 8 },
  bottomNav: {
    flexDirection: 'row', backgroundColor: '#0F172A',
    borderTopWidth: 1, borderTopColor: '#1E293B',
    paddingTop: 8,
  },
  bottomNavItem: { flex: 1, alignItems: 'center', paddingVertical: 6, gap: 3 },
  bottomNavLabel: { fontSize: 10, color: '#64748B', fontWeight: '600' },
});
