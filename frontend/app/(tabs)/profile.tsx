import React, { useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  TextInput, Alert, ActivityIndicator, Dimensions, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useAuthStore } from '../../src/store/authStore';
import { authAPI } from '../../src/services/api';

const { width: SW } = Dimensions.get('window');
const W = Platform.OS === 'web' && SW > 860;

export default function ProfileScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user, logout, setUser } = useAuthStore();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(user?.name || '');
  const [company, setCompany] = useState(user?.company_name || '');
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await authAPI.updateProfile({ name: name.trim(), company_name: company.trim() });
      setUser({ ...user!, name: name.trim(), company_name: company.trim() });
      setEditing(false);
      Alert.alert('Success', 'Profile updated');
    } catch (e: any) {
      Alert.alert('Error', e.response?.data?.detail || 'Failed');
    } finally { setSaving(false); }
  };

  const handleLogout = () => {
    Alert.alert('Logout', 'Sign out of MediaView?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Sign Out', style: 'destructive', onPress: async () => { await logout(); router.replace('/(auth)/login'); }},
    ]);
  };

  return (
    <ScrollView style={$.ct} contentContainerStyle={{ paddingTop: W ? 28 : insets.top + 16, paddingBottom: 100, paddingHorizontal: W ? 32 : 20 }}>
      <Text style={$.title}>Settings</Text>

      <View style={$.avatarSec}>
        <View style={$.avatar}><Text style={$.avatarT}>{user?.name?.charAt(0)?.toUpperCase() || 'U'}</Text></View>
        <Text style={$.avatarName}>{user?.name}</Text>
        <Text style={$.avatarEmail}>{user?.email}</Text>
        <View style={[$.roleBadge, { backgroundColor: user?.role === 'admin' ? 'rgba(99,102,241,0.15)' : 'rgba(16,185,129,0.15)' }]}>
          <Text style={[$.roleT, { color: user?.role === 'admin' ? '#818CF8' : '#34D399' }]}>{user?.role?.toUpperCase()}</Text>
        </View>
      </View>

      <View style={$.section}>
        <View style={$.secHd}>
          <Text style={$.secTitle}>Account Information</Text>
          <TouchableOpacity onPress={() => setEditing(!editing)}>
            <Ionicons name={editing ? 'close' : 'create-outline'} size={20} color="#818CF8" />
          </TouchableOpacity>
        </View>
        <View style={$.card}>
          <View style={$.infoRow}>
            <Text style={$.infoLabel}>Full Name</Text>
            {editing ? <TextInput style={$.editInput} value={name} onChangeText={setName} placeholderTextColor="#475569" /> : <Text style={$.infoVal}>{user?.name}</Text>}
          </View>
          <View style={$.divider} />
          <View style={$.infoRow}>
            <Text style={$.infoLabel}>Email</Text>
            <Text style={$.infoVal}>{user?.email}</Text>
          </View>
          <View style={$.divider} />
          <View style={$.infoRow}>
            <Text style={$.infoLabel}>Company</Text>
            {editing ? <TextInput style={$.editInput} value={company} onChangeText={setCompany} placeholder="Company" placeholderTextColor="#475569" /> : <Text style={$.infoVal}>{user?.company_name || 'Not set'}</Text>}
          </View>
        </View>
        {editing && (
          <TouchableOpacity style={$.saveBtn} onPress={handleSave} disabled={saving}>
            {saving ? <ActivityIndicator color="#FFF" /> : <Text style={$.saveBtnT}>Save Changes</Text>}
          </TouchableOpacity>
        )}
      </View>

      {user?.role === 'admin' && (
        <TouchableOpacity style={$.adminCard} onPress={() => router.push('/admin')}>
          <View style={$.adminInner}>
            <View style={$.adminIcon}><Ionicons name="shield-checkmark" size={22} color="#818CF8" /></View>
            <View style={{ flex: 1 }}><Text style={$.adminTitle}>Admin Panel</Text><Text style={$.adminSub}>Manage users, screens, campaigns, devices</Text></View>
            <Ionicons name="chevron-forward" size={20} color="#475569" />
          </View>
        </TouchableOpacity>
      )}

      <TouchableOpacity style={$.logoutBtn} onPress={handleLogout}>
        <Ionicons name="log-out-outline" size={20} color="#EF4444" />
        <Text style={$.logoutT}>Sign Out</Text>
      </TouchableOpacity>

      <Text style={$.version}>MediaView v1.0.0</Text>
    </ScrollView>
  );
}

const $ = StyleSheet.create({
  ct: { flex: 1, backgroundColor: '#0B0F1A' },
  title: { fontSize: 22, fontWeight: '700', color: '#F1F5F9', marginBottom: 24 },
  avatarSec: { alignItems: 'center', marginBottom: 28 },
  avatar: { width: 72, height: 72, borderRadius: 36, backgroundColor: '#1E293B', justifyContent: 'center', alignItems: 'center', marginBottom: 12, borderWidth: 2, borderColor: '#6366F1' },
  avatarT: { fontSize: 28, fontWeight: '700', color: '#818CF8' },
  avatarName: { fontSize: 20, fontWeight: '700', color: '#F1F5F9' },
  avatarEmail: { fontSize: 14, color: '#64748B', marginTop: 2 },
  roleBadge: { paddingHorizontal: 12, paddingVertical: 4, borderRadius: 8, marginTop: 8 },
  roleT: { fontSize: 11, fontWeight: '700' },
  section: { marginBottom: 24 },
  secHd: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  secTitle: { fontSize: 15, fontWeight: '600', color: '#E2E8F0' },
  card: { backgroundColor: '#111827', borderRadius: 14, borderWidth: 1, borderColor: '#1E293B', overflow: 'hidden' },
  infoRow: { paddingHorizontal: 16, paddingVertical: 14 },
  infoLabel: { fontSize: 12, color: '#64748B', marginBottom: 4 },
  infoVal: { fontSize: 15, fontWeight: '500', color: '#F1F5F9' },
  divider: { height: 1, backgroundColor: '#1E293B', marginHorizontal: 16 },
  editInput: { fontSize: 15, fontWeight: '500', color: '#F1F5F9', backgroundColor: '#1F2937', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8, borderWidth: 1, borderColor: '#374151' },
  saveBtn: { backgroundColor: '#6366F1', borderRadius: 12, paddingVertical: 14, alignItems: 'center', marginTop: 12 },
  saveBtnT: { color: '#FFF', fontSize: 15, fontWeight: '700' },
  adminCard: { backgroundColor: '#111827', borderRadius: 14, padding: 16, marginBottom: 24, borderWidth: 1, borderColor: '#1E293B' },
  adminInner: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  adminIcon: { width: 44, height: 44, borderRadius: 12, backgroundColor: 'rgba(99,102,241,0.12)', justifyContent: 'center', alignItems: 'center' },
  adminTitle: { fontSize: 16, fontWeight: '600', color: '#F1F5F9' },
  adminSub: { fontSize: 13, color: '#64748B', marginTop: 2 },
  logoutBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(239,68,68,0.1)', borderRadius: 14, paddingVertical: 14, gap: 8, borderWidth: 1, borderColor: 'rgba(239,68,68,0.2)', marginBottom: 16 },
  logoutT: { fontSize: 15, fontWeight: '600', color: '#EF4444' },
  version: { fontSize: 12, color: '#374151', textAlign: 'center', marginTop: 8 },
});
