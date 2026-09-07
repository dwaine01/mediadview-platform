import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, useWindowDimensions, Platform, ScrollView, Image,
} from 'react-native';
import { useRouter, usePathname, Slot } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useAuthStore } from '../../src/store/authStore';
import { workspaceAPI } from '../../src/services/api';

const MEDIA = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const WS_NAV = [
  { key: 'index', label: 'Panel', icon: 'grid' as const, path: '/workspace' },
  { key: 'promo', label: 'Promo', icon: 'megaphone' as const, path: '/workspace/promo' },
  { key: 'screens', label: 'Pantallas', icon: 'tv' as const, path: '/workspace/screens' },
  { key: 'menus', label: 'Menús', icon: 'fast-food' as const, path: '/workspace/menus' },
  { key: 'content', label: 'Contenido', icon: 'images' as const, path: '/workspace/content' },
  { key: 'playlists', label: 'Playlists', icon: 'list' as const, path: '/workspace/playlists' },
  { key: 'schedules', label: 'Horarios', icon: 'calendar' as const, path: '/workspace/schedules' },
  { key: 'activity', label: 'Actividad', icon: 'time' as const, path: '/workspace/activity' },
  { key: 'reports', label: 'Reportes', icon: 'stats-chart' as const, path: '/workspace/reports' },
  { key: 'users', label: 'Equipo', icon: 'people' as const, path: '/workspace/users', ownerOnly: true },
  { key: 'billing', label: 'Facturación', icon: 'card' as const, path: '/workspace/billing', ownerOnly: true },
  { key: 'settings', label: 'Ajustes', icon: 'settings' as const, path: '/workspace/settings' },
];

export default function WorkspaceLayout() {
  const router = useRouter();
  const pathname = usePathname();
  const insets = useSafeAreaInsets();
  const { user, logout, token } = useAuthStore();
  const { width: SW } = useWindowDimensions();
  const IS_WEB_WIDE = Platform.OS === 'web' && SW > 860;

  // Auth guard: redirect to login as soon as the persisted store is hydrated.
  // `isInitialized` is read from the store so this re-runs when hydration lands,
  // not only when the token reference changes.
  const isInitialized = useAuthStore(st => st.isInitialized);

  // The customer's own branding in the corner of their panel.
  const [orgLogo, setOrgLogo] = useState<string | null>(null);
  const [orgName, setOrgName] = useState<string>('');
  useEffect(() => {
    if (!token) { setOrgLogo(null); setOrgName(''); return; }
    workspaceAPI.context()
      .then(res => {
        const org = res.data?.organization;
        setOrgName(org?.name || '');
        const url = org?.logo_url;
        setOrgLogo(url ? (url.startsWith('http') ? url : `${MEDIA}${url}`) : null);
      })
      .catch((e) => {
        setOrgLogo(null);
        // 428: member still using the temporary password created by the owner
        if (e?.response?.status === 428) router.replace('/account/change-password');
      });
  }, [token, router]);
  useEffect(() => {
    if (isInitialized && !token) {
      router.replace('/account/login');
    }
  }, [isInitialized, token, router]);

  const isOwner = user?.rbac_role === 'SELF_SERVICE_OWNER';
  const NAV = WS_NAV.filter(n => isOwner || !n.ownerOnly);

  const activeKey = NAV.find(n => {
    if (n.key === 'index') return pathname === '/workspace' || pathname === '/workspace/';
    return pathname.startsWith(n.path);
  })?.key || 'index';

  const handleLogout = async () => {
    await logout();
    router.replace('/account/login');
  };

  if (IS_WEB_WIDE) {
  return (
    <View style={[ws.root, { flexDirection: 'row' }]}>
        {/* Sidebar */}
        <View style={[ws.sidebar, { paddingTop: insets.top + 12 }]}>
          {/* Brand */}
          <View style={ws.brand}>
            {orgLogo
              ? <View style={ws.brandLogoBox}><Image source={{ uri: orgLogo }} style={ws.brandLogo} resizeMode="contain" /></View>
              : <View style={ws.brandIcon}><Text style={ws.brandIconText}>MV</Text></View>}
            <View style={{ flex: 1 }}>
              <Text style={ws.brandName} numberOfLines={1}>{orgName || 'MediaView'}</Text>
              <Text style={ws.brandSub}>Panel del Cliente</Text>
            </View>
          </View>

          {/* Nav */}
          <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false}>
            <View style={ws.navSection}>
              <Text style={ws.navSectionLabel}>MI NEGOCIO</Text>
              {NAV.map(item => {
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
                      color={active ? '#0891B2' : '#64748B'}
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
          {orgLogo
            ? <View style={ws.brandLogoBox}><Image source={{ uri: orgLogo }} style={ws.brandLogo} resizeMode="contain" /></View>
            : <View style={ws.brandIcon}><Text style={ws.brandIconText}>MV</Text></View>}
          <View>
            <Text style={ws.brandName} numberOfLines={1}>{orgName || 'MediaView'}</Text>
            <Text style={ws.brandSub}>Panel del Cliente</Text>
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
        {NAV.slice(0, 5).map(item => {
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
                color={active ? '#0891B2' : '#64748B'}
              />
              <Text style={[ws.bottomNavLabel, active && { color: '#0891B2' }]}>{item.label}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

const ws = StyleSheet.create({
  root: { flex: 1, flexDirection: 'column', backgroundColor: '#F8FAFC' },

  // Sidebar (web)
  sidebar: {
    width: 240, backgroundColor: '#FFFFFF', borderRightWidth: 1,
    borderRightColor: '#E2E8F0', paddingHorizontal: 14, paddingBottom: 16,
  },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 8, paddingVertical: 14, marginBottom: 8 },
  brandIcon: { width: 36, height: 36, borderRadius: 10, backgroundColor: '#0891B2', justifyContent: 'center', alignItems: 'center' },
  brandLogoBox: {
    width: 36, height: 36, borderRadius: 10, backgroundColor: '#FFFFFF',
    borderWidth: 1, borderColor: '#E2E8F0', justifyContent: 'center', alignItems: 'center',
    overflow: 'hidden', padding: 3,
  },
  brandLogo: { width: '100%', height: '100%' },
  brandIconText: { fontSize: 14, fontWeight: '900', color: '#FFF' },
  brandName: { fontSize: 15, fontWeight: '700', color: '#0F172A' },
  brandSub: { fontSize: 10, color: '#64748B', marginTop: 1 },
  navSection: { paddingTop: 4 },
  navSectionLabel: { fontSize: 10, fontWeight: '800', color: '#94A3B8', letterSpacing: 1.5, paddingHorizontal: 12, marginBottom: 6 },
  navItem: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingVertical: 10, paddingHorizontal: 12, borderRadius: 10, marginBottom: 2,
  },
  navItemActive: { backgroundColor: 'rgba(6,182,212,0.10)' },
  navLabel: { fontSize: 14, color: '#64748B', fontWeight: '500' },
  navLabelActive: { color: '#0891B2', fontWeight: '600' },
  sidebarFooter: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingTop: 14, borderTopWidth: 1, borderTopColor: '#E2E8F0', marginTop: 8,
  },
  userAvatar: { width: 34, height: 34, borderRadius: 10, backgroundColor: '#CFFAFE', justifyContent: 'center', alignItems: 'center' },
  userAvatarText: { fontSize: 14, fontWeight: '700', color: '#0891B2' },
  userName: { fontSize: 13, fontWeight: '600', color: '#1E293B' },
  userEmail: { fontSize: 11, color: '#64748B' },
  main: { flex: 1, overflow: 'hidden' },

  // Mobile
  mobileHeader: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 20, paddingBottom: 12,
    backgroundColor: '#FFFFFF', borderBottomWidth: 1, borderBottomColor: '#E2E8F0',
  },
  mobileBrand: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  logoutBtn: { padding: 8 },
  bottomNav: {
    flexDirection: 'row', backgroundColor: '#FFFFFF',
    borderTopWidth: 1, borderTopColor: '#E2E8F0',
    paddingTop: 8,
  },
  bottomNavItem: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingVertical: 8, gap: 3, minHeight: 48 },
  bottomNavLabel: { fontSize: 10, color: '#64748B', fontWeight: '600' },
});
