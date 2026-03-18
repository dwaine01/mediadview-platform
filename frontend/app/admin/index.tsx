import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  ActivityIndicator, Alert, RefreshControl, TextInput,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { adminAPI, screensAPI, adminDevicesAPI } from '../../src/services/api';
import { getStatusStyle } from '../../src/constants/theme';

const TABS = ['Dashboard', 'Users', 'Screens', 'Campaigns', 'Devices'];

export default function AdminPanel() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [tab, setTab] = useState(0);
  const [analytics, setAnalytics] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [screens, setScreens] = useState<any[]>([]);
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [devices, setDevices] = useState<any[]>([]);
  const [activateCode, setActivateCode] = useState('');
  const [activateScreenId, setActivateScreenId] = useState('');
  const [activating, setActivating] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [analyticsRes, usersRes, allScreensRes, campaignsRes] = await Promise.all([
        adminAPI.analytics(),
        adminAPI.listUsers(),
        screensAPI.list({ status: '' }),
        adminAPI.listCampaigns(),
      ]);
      setAnalytics(analyticsRes.data);
      setUsers(usersRes.data);
      setScreens(allScreensRes.data);
      setCampaigns(campaignsRes.data);
    } catch (e) {
      console.log('Admin fetch error:', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const fetchAllScreens = useCallback(async () => {
    try {
      const res = await screensAPI.list({ status: '' });
      setScreens(res.data);
    } catch (e) {
      console.log('Screens fetch error:', e);
    }
  }, []);

  const fetchAllCampaigns = useCallback(async () => {
    try {
      const res = await adminAPI.listCampaigns();
      setCampaigns(res.data);
    } catch (e) {
      console.log('Campaigns fetch error:', e);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);
  useEffect(() => {
    if (tab === 2) fetchAllScreens();
    if (tab === 3) fetchAllCampaigns();
    if (tab === 4) fetchDevices();
  }, [tab]);

  const fetchDevices = async () => {
    try {
      const res = await adminDevicesAPI.list();
      setDevices(res.data);
    } catch (e) {
      console.log('Devices fetch error:', e);
    }
  };

  const handleActivateDevice = async () => {
    if (!activateCode.trim() || !activateScreenId) {
      Alert.alert('Error', 'Enter activation code and select a screen');
      return;
    }
    setActivating(true);
    try {
      const res = await adminDevicesAPI.activate({
        activation_code: activateCode.trim().toUpperCase(),
        screen_id: activateScreenId,
      });
      Alert.alert('Success', `Device activated for ${res.data.screen_name}`);
      setActivateCode('');
      setActivateScreenId('');
      fetchDevices();
    } catch (e: any) {
      Alert.alert('Error', e.response?.data?.detail || 'Activation failed');
    } finally {
      setActivating(false);
    }
  };

  const removeDevice = async (id: string) => {
    Alert.alert('Remove Device', 'This will unlink and remove the device.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Remove', style: 'destructive', onPress: async () => {
        try {
          await adminDevicesAPI.remove(id);
          fetchDevices();
        } catch (e: any) {
          Alert.alert('Error', e.response?.data?.detail || 'Failed');
        }
      }},
    ]);
  };

  const toggleUser = async (userId: string, active: boolean) => {
    try {
      await adminAPI.updateUser(userId, !active);
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, active: !active } : u));
    } catch (e: any) {
      Alert.alert('Error', e.response?.data?.detail || 'Failed to update user');
    }
  };

  const approveCampaign = async (id: string) => {
    try {
      await adminAPI.approveCampaign(id);
      Alert.alert('Success', 'Campaign approved');
      fetchAllCampaigns();
    } catch (e: any) {
      Alert.alert('Error', e.response?.data?.detail || 'Failed to approve');
    }
  };

  const rejectCampaign = async (id: string) => {
    Alert.alert('Reject Campaign', 'Are you sure?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Reject', style: 'destructive', onPress: async () => {
        try {
          await adminAPI.rejectCampaign(id, 'Rejected by admin');
          Alert.alert('Done', 'Campaign rejected');
          fetchAllCampaigns();
        } catch (e: any) {
          Alert.alert('Error', e.response?.data?.detail || 'Failed');
        }
      }},
    ]);
  };

  if (loading) {
    return <View style={[styles.center, { paddingTop: insets.top }]}><ActivityIndicator size="large" color="#4F46E5" /></View>;
  }

  const renderDashboard = () => {
    const stats = [
      { label: 'Users', value: analytics?.total_users || 0, icon: 'people', color: '#4F46E5' },
      { label: 'Screens', value: analytics?.total_screens || 0, icon: 'tv', color: '#0EA5E9' },
      { label: 'Campaigns', value: analytics?.total_campaigns || 0, icon: 'megaphone', color: '#10B981' },
      { label: 'Revenue', value: `$${(analytics?.total_revenue || 0).toLocaleString()}`, icon: 'wallet', color: '#F59E0B' },
      { label: 'Active', value: analytics?.active_campaigns || 0, icon: 'play-circle', color: '#10B981' },
      { label: 'Pending', value: analytics?.pending_campaigns || 0, icon: 'time', color: '#EF4444' },
    ];
    return (
      <ScrollView contentContainerStyle={styles.scrollPad}>
        <View style={styles.statsGrid}>
          {stats.map((s, i) => (
            <View key={i} style={styles.statCard}>
              <View style={[styles.statIcon, { backgroundColor: s.color + '15' }]}>
                <Ionicons name={s.icon as any} size={18} color={s.color} />
              </View>
              <Text style={styles.statValue}>{s.value}</Text>
              <Text style={styles.statLabel}>{s.label}</Text>
            </View>
          ))}
        </View>
      </ScrollView>
    );
  };

  const renderUsers = () => (
    <ScrollView contentContainerStyle={styles.scrollPad}>
      {users.map(u => (
        <View key={u.id} style={styles.listCard}>
          <View style={styles.listCardLeft}>
            <View style={[styles.avatarSmall, { backgroundColor: u.role === 'admin' ? '#EEF2FF' : '#F0FDF4' }]}>
              <Text style={[styles.avatarSmallText, { color: u.role === 'admin' ? '#4F46E5' : '#16A34A' }]}>
                {u.name?.charAt(0)?.toUpperCase()}
              </Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.listName}>{u.name}</Text>
              <Text style={styles.listSub}>{u.email}</Text>
              <Text style={styles.listRole}>{u.role}</Text>
            </View>
          </View>
          {u.role !== 'admin' && (
            <TouchableOpacity
              style={[styles.toggleBtn, { backgroundColor: u.active ? '#D1FAE5' : '#FEE2E2' }]}
              onPress={() => toggleUser(u.id, u.active)}
            >
              <Text style={[styles.toggleText, { color: u.active ? '#065F46' : '#991B1B' }]}>
                {u.active ? 'Active' : 'Disabled'}
              </Text>
            </TouchableOpacity>
          )}
        </View>
      ))}
    </ScrollView>
  );

  const renderScreens = () => (
    <ScrollView contentContainerStyle={styles.scrollPad}>
      {screens.map(s => (
        <View key={s.id} style={styles.listCard}>
          <View style={{ flex: 1 }}>
            <Text style={styles.listName}>{s.name}</Text>
            <Text style={styles.listSub}>{s.location?.city}, {s.location?.state}</Text>
            <Text style={styles.listRole}>${s.pricing?.per_hour}/hr | {s.specs?.size}</Text>
          </View>
          <View style={[styles.statusDot, { backgroundColor: s.status === 'active' ? '#10B981' : '#94A3B8' }]} />
        </View>
      ))}
    </ScrollView>
  );

  const renderCampaigns = () => (
    <ScrollView
      contentContainerStyle={styles.scrollPad}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchAllCampaigns().then(() => setRefreshing(false)); }} />}
    >
      {campaigns.length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons name="checkmark-circle-outline" size={48} color="#CBD5E1" />
          <Text style={styles.emptyText}>No campaigns to review</Text>
        </View>
      ) : (
        campaigns.map(c => {
          const st = getStatusStyle(c.status);
          return (
            <View key={c.id} style={styles.listCard}>
              <View style={{ flex: 1 }}>
                <View style={styles.campaignRow}>
                  <Text style={styles.listName} numberOfLines={1}>{c.name}</Text>
                  <View style={[styles.badge, { backgroundColor: st.bg }]}>
                    <Text style={[styles.badgeText, { color: st.text }]}>{c.status}</Text>
                  </View>
                </View>
                <Text style={styles.listSub}>
                  {c.user?.name || 'User'} | {c.screen?.name || 'Screen'}
                </Text>
                <Text style={styles.listRole}>
                  {c.schedule?.start_date} - {c.schedule?.end_date} | ${c.pricing?.total?.toLocaleString()}
                </Text>
                {c.status === 'pending' && (
                  <View style={styles.actionRow}>
                    <TouchableOpacity style={styles.approveBtn} onPress={() => approveCampaign(c.id)}>
                      <Ionicons name="checkmark" size={16} color="#FFFFFF" />
                      <Text style={styles.approveBtnText}>Approve</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={styles.rejectBtn} onPress={() => rejectCampaign(c.id)}>
                      <Ionicons name="close" size={16} color="#EF4444" />
                      <Text style={styles.rejectBtnText}>Reject</Text>
                    </TouchableOpacity>
                  </View>
                )}
              </View>
            </View>
          );
        })
      )}
    </ScrollView>
  );

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color="#0F172A" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Admin Panel</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabBar}>
        {TABS.map((t, i) => (
          <TouchableOpacity
            key={t}
            style={[styles.tabItem, tab === i && styles.tabItemActive]}
            onPress={() => setTab(i)}
          >
            <Text style={[styles.tabText, tab === i && styles.tabTextActive]}>{t}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {tab === 0 && renderDashboard()}
      {tab === 1 && renderUsers()}
      {tab === 2 && renderScreens()}
      {tab === 3 && renderCampaigns()}
      {tab === 4 && (
        <ScrollView contentContainerStyle={styles.scrollPad}>
          {/* Activation Form */}
          <View style={[styles.listCard, { flexDirection: 'column', alignItems: 'stretch' }]}>
            <Text style={[styles.listName, { marginBottom: 12 }]}>Activate New Device</Text>
            <TextInput
              style={styles.activateInput}
              placeholder="Enter 6-digit activation code"
              placeholderTextColor="#94A3B8"
              value={activateCode}
              onChangeText={setActivateCode}
              autoCapitalize="characters"
              maxLength={6}
            />
            <Text style={[styles.listSub, { marginTop: 8, marginBottom: 4 }]}>Assign to Screen:</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 12, maxHeight: 40 }}>
              {screens.map(s => (
                <TouchableOpacity
                  key={s.id}
                  style={[styles.screenChip, activateScreenId === s.id && styles.screenChipActive]}
                  onPress={() => setActivateScreenId(s.id)}
                >
                  <Text style={[styles.screenChipText, activateScreenId === s.id && styles.screenChipTextActive]}
                    numberOfLines={1}>{s.name}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
            <TouchableOpacity
              style={[styles.approveBtn, { alignSelf: 'flex-start' }]}
              onPress={handleActivateDevice}
              disabled={activating}
            >
              <Ionicons name="link" size={16} color="#FFFFFF" />
              <Text style={styles.approveBtnText}>{activating ? 'Activating...' : 'Activate Device'}</Text>
            </TouchableOpacity>
          </View>

          {/* Device List */}
          <Text style={[styles.listName, { marginBottom: 8, marginTop: 16 }]}>
            Registered Devices ({devices.length})
          </Text>
          {devices.length === 0 ? (
            <View style={styles.emptyState}>
              <Ionicons name="phone-portrait-outline" size={48} color="#CBD5E1" />
              <Text style={styles.emptyText}>No devices registered</Text>
              <Text style={[styles.listSub, { textAlign: 'center', marginTop: 4 }]}>
                Install MediaView Player on a TV and it will appear here
              </Text>
            </View>
          ) : (
            devices.map(d => {
              const isOnline = d.last_heartbeat &&
                (new Date().getTime() - new Date(d.last_heartbeat).getTime()) < 120000;
              return (
                <View key={d.id} style={styles.listCard}>
                  <View style={{ flex: 1 }}>
                    <View style={styles.campaignRow}>
                      <Text style={styles.listName}>{d.device_name || 'Player'}</Text>
                      <View style={[styles.badge, {
                        backgroundColor: d.status === 'active' ? '#D1FAE5' :
                          d.status === 'pending' ? '#FEF3C7' : '#FEE2E2'
                      }]}>
                        <Text style={[styles.badgeText, {
                          color: d.status === 'active' ? '#065F46' :
                            d.status === 'pending' ? '#92400E' : '#991B1B'
                        }]}>{d.status}</Text>
                      </View>
                    </View>
                    <Text style={styles.listSub}>
                      Code: {d.activation_code} | Screen: {d.screen_name || 'Not assigned'}
                    </Text>
                    <Text style={styles.listRole}>
                      {d.device_info?.model || 'Unknown'} | Last seen: {
                        d.last_heartbeat ? new Date(d.last_heartbeat).toLocaleString() : 'Never'
                      }
                    </Text>
                    <View style={[styles.actionRow, { marginTop: 8 }]}>
                      <View style={[styles.statusDot, { backgroundColor: isOnline ? '#10B981' : '#94A3B8', width: 8, height: 8, borderRadius: 4 }]} />
                      <Text style={[styles.listRole, { marginTop: 0 }]}>{isOnline ? 'Online' : 'Offline'}</Text>
                      <TouchableOpacity
                        style={[styles.rejectBtn, { marginLeft: 'auto' }]}
                        onPress={() => removeDevice(d.id)}
                      >
                        <Ionicons name="trash" size={14} color="#EF4444" />
                        <Text style={styles.rejectBtnText}>Remove</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                </View>
              );
            })
          )}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F1F5F9' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#F1F5F9' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingVertical: 12,
  },
  backBtn: { width: 40, height: 40, borderRadius: 10, backgroundColor: '#FFFFFF', justifyContent: 'center', alignItems: 'center' },
  headerTitle: { fontSize: 18, fontWeight: '700', color: '#0F172A' },
  tabBar: { paddingHorizontal: 16, marginBottom: 8, maxHeight: 44 },
  tabItem: {
    paddingHorizontal: 18, paddingVertical: 10, borderRadius: 10,
    backgroundColor: '#FFFFFF', marginRight: 8,
    borderWidth: 1, borderColor: '#E2E8F0',
  },
  tabItemActive: { backgroundColor: '#4F46E5', borderColor: '#4F46E5' },
  tabText: { fontSize: 14, fontWeight: '600', color: '#64748B' },
  tabTextActive: { color: '#FFFFFF' },
  scrollPad: { paddingHorizontal: 20, paddingBottom: 40 },
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 8 },
  statCard: {
    width: '48%', backgroundColor: '#FFFFFF', borderRadius: 14, padding: 14,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.04, shadowRadius: 4, elevation: 1,
    flexGrow: 1, flexBasis: '46%',
  },
  statIcon: { width: 32, height: 32, borderRadius: 8, justifyContent: 'center', alignItems: 'center', marginBottom: 8 },
  statValue: { fontSize: 20, fontWeight: '700', color: '#0F172A' },
  statLabel: { fontSize: 12, color: '#64748B', marginTop: 2 },
  listCard: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: '#FFFFFF',
    borderRadius: 14, padding: 14, marginBottom: 8,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.03, shadowRadius: 4, elevation: 1,
  },
  listCardLeft: { flexDirection: 'row', alignItems: 'center', flex: 1, gap: 12 },
  avatarSmall: { width: 38, height: 38, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  avatarSmallText: { fontSize: 16, fontWeight: '700' },
  listName: { fontSize: 15, fontWeight: '600', color: '#0F172A' },
  listSub: { fontSize: 12, color: '#64748B', marginTop: 2 },
  listRole: { fontSize: 11, color: '#94A3B8', marginTop: 2 },
  toggleBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8 },
  toggleText: { fontSize: 12, fontWeight: '700' },
  statusDot: { width: 10, height: 10, borderRadius: 5 },
  campaignRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  badgeText: { fontSize: 10, fontWeight: '700', textTransform: 'uppercase' },
  actionRow: { flexDirection: 'row', gap: 8, marginTop: 10 },
  approveBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: '#10B981', paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
  },
  approveBtnText: { color: '#FFFFFF', fontSize: 13, fontWeight: '600' },
  rejectBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: '#FEE2E2', paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
  },
  rejectBtnText: { color: '#EF4444', fontSize: 13, fontWeight: '600' },
  emptyState: { alignItems: 'center', paddingTop: 60 },
  emptyText: { fontSize: 16, color: '#94A3B8', marginTop: 12 },
  activateInput: {
    backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#E2E8F0',
    borderRadius: 10, paddingHorizontal: 14, paddingVertical: 12,
    fontSize: 20, fontWeight: '700', color: '#0F172A', letterSpacing: 4, textAlign: 'center',
  },
  screenChip: {
    paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8,
    backgroundColor: '#F1F5F9', borderWidth: 1, borderColor: '#E2E8F0', marginRight: 6,
  },
  screenChipActive: { backgroundColor: '#4F46E5', borderColor: '#4F46E5' },
  screenChipText: { fontSize: 12, fontWeight: '600', color: '#64748B' },
  screenChipTextActive: { color: '#FFFFFF' },
});
