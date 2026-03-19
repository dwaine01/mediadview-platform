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
    } catch (e: any) { Alert.alert('Error', e.response?.data?.detail || 'Failed'); }
    finally { setSaving(false); }
  };

  const handleLogout = () => {
    Alert.alert('Sign Out', 'Are you sure you want to sign out?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Sign Out', onPress: async () => { await logout(); router.replace('/(auth)/login'); }},
    ]);
  };

  const initials = (user?.name || 'U').split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase();

  return (
    <ScrollView style={$.ct} contentContainerStyle={{ paddingTop: W ? 36 : insets.top + 20, paddingBottom: 100, paddingHorizontal: W ? 40 : 20 }}>
      <Text style={$.pageTitle}>Settings</Text>

      {/* Premium Avatar Section */}
      <View style={$.avatarSection}>
        <View style={$.avatarOuter}>
          <View style={$.avatarRing}>
            <View style={$.avatar}>
              <Text style={$.avatarText}>{initials}</Text>
            </View>
          </View>
          <View style={[$.onlineDot, { backgroundColor: '#10B981' }]} />
        </View>
        <Text style={$.userName}>{user?.name}</Text>
        <Text style={$.userEmail}>{user?.email}</Text>
        <View style={$.roleChip}>
          <View style={[$.roleDot, { backgroundColor: user?.role === 'admin' ? '#818CF8' : '#10B981' }]} />
          <Text style={[$.roleText, { color: user?.role === 'admin' ? '#818CF8' : '#34D399' }]}>
            {user?.role === 'admin' ? 'Administrator' : 'Customer'}
          </Text>
        </View>
      </View>

      {/* Account Info */}
      <View style={$.section}>
        <View style={$.secHd}>
          <View>
            <Text style={$.secTitle}>Account Information</Text>
            <Text style={$.secSub}>Manage your personal details</Text>
          </View>
          <TouchableOpacity style={$.editBtn} onPress={() => setEditing(!editing)}>
            <Ionicons name={editing ? 'close' : 'create-outline'} size={16} color="#818CF8" />
            <Text style={$.editBtnT}>{editing ? 'Cancel' : 'Edit'}</Text>
          </TouchableOpacity>
        </View>
        <View style={$.card}>
          {[
            { label: 'Full Name', value: user?.name, editable: true, val: name, set: setName },
            { label: 'Email Address', value: user?.email, editable: false },
            { label: 'Company', value: user?.company_name || 'Not set', editable: true, val: company, set: setCompany },
            { label: 'Role', value: user?.role === 'admin' ? 'Administrator' : 'Customer', editable: false },
          ].map((field, i) => (
            <View key={i}>
              {i > 0 && <View style={$.divider} />}
              <View style={$.infoRow}>
                <Text style={$.infoLabel}>{field.label}</Text>
                {editing && field.editable && field.set ? (
                  <TextInput style={$.editInput} value={field.val} onChangeText={field.set} placeholderTextColor="#475569" />
                ) : (
                  <Text style={$.infoVal}>{field.value}</Text>
                )}
              </View>
            </View>
          ))}
        </View>
        {editing && (
          <TouchableOpacity style={$.saveBtn} onPress={handleSave} disabled={saving}>
            {saving ? <ActivityIndicator color="#FFF" /> : <><Ionicons name="checkmark" size={18} color="#FFF" /><Text style={$.saveBtnT}>Save Changes</Text></>}
          </TouchableOpacity>
        )}
      </View>

      {/* Admin Panel Link */}
      {user?.role === 'admin' && (
        <TouchableOpacity style={$.adminCard} onPress={() => router.push('/admin')}>
          <View style={$.adminIcon}>
            <Ionicons name="shield-checkmark" size={22} color="#818CF8" />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={$.adminTitle}>Admin Panel</Text>
            <Text style={$.adminSub}>Manage users, screens, campaigns & devices</Text>
          </View>
          <View style={$.adminArrow}>
            <Ionicons name="arrow-forward" size={16} color="#818CF8" />
          </View>
        </TouchableOpacity>
      )}

      {/* Sign Out - Subtle outline style */}
      <TouchableOpacity style={$.logoutBtn} onPress={handleLogout}>
        <Ionicons name="log-out-outline" size={18} color="#94A3B8" />
        <Text style={$.logoutT}>Sign Out</Text>
      </TouchableOpacity>

      <Text style={$.version}>MediaView Platform v1.0.0</Text>
    </ScrollView>
  );
}

const $ = StyleSheet.create({
  ct: { flex: 1, backgroundColor: '#0B0F1A' },
  pageTitle: { fontSize: 28, fontWeight: '800', color: '#F1F5F9', letterSpacing: -0.5, marginBottom: 32 },

  // Premium Avatar
  avatarSection: { alignItems: 'center', marginBottom: 36 },
  avatarOuter: { position: 'relative', marginBottom: 16 },
  avatarRing: {
    width: 88, height: 88, borderRadius: 44,
    borderWidth: 2, borderColor: '#6366F1',
    padding: 3, shadowColor: '#6366F1', shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.4, shadowRadius: 16, elevation: 8,
  },
  avatar: {
    width: '100%', height: '100%', borderRadius: 40,
    backgroundColor: '#1E1B4B', justifyContent: 'center', alignItems: 'center',
  },
  avatarText: { fontSize: 28, fontWeight: '800', color: '#A5B4FC' },
  onlineDot: {
    position: 'absolute', bottom: 4, right: 4,
    width: 16, height: 16, borderRadius: 8,
    borderWidth: 3, borderColor: '#0B0F1A',
  },
  userName: { fontSize: 22, fontWeight: '700', color: '#F1F5F9' },
  userEmail: { fontSize: 14, color: '#64748B', marginTop: 2 },
  roleChip: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: 'rgba(99,102,241,0.1)', paddingHorizontal: 14, paddingVertical: 6,
    borderRadius: 20, marginTop: 10, borderWidth: 1, borderColor: 'rgba(99,102,241,0.2)',
  },
  roleDot: { width: 6, height: 6, borderRadius: 3 },
  roleText: { fontSize: 12, fontWeight: '600' },

  // Section
  section: { marginBottom: 28 },
  secHd: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 },
  secTitle: { fontSize: 18, fontWeight: '700', color: '#F1F5F9', letterSpacing: -0.3 },
  secSub: { fontSize: 12, color: '#475569', marginTop: 2 },
  editBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: 'rgba(99,102,241,0.1)', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8 },
  editBtnT: { fontSize: 12, fontWeight: '600', color: '#818CF8' },

  // Card
  card: { backgroundColor: '#111827', borderRadius: 16, borderWidth: 1, borderColor: '#1E293B', overflow: 'hidden' },
  infoRow: { paddingHorizontal: 18, paddingVertical: 16 },
  infoLabel: { fontSize: 11, color: '#64748B', fontWeight: '500', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 },
  infoVal: { fontSize: 15, fontWeight: '500', color: '#F1F5F9' },
  divider: { height: 1, backgroundColor: '#1E293B', marginHorizontal: 18 },
  editInput: { fontSize: 15, fontWeight: '500', color: '#F1F5F9', backgroundColor: '#1F2937', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, borderWidth: 1, borderColor: '#374151' },
  saveBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: '#6366F1', borderRadius: 12, paddingVertical: 14, marginTop: 14,
    shadowColor: '#6366F1', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.3, shadowRadius: 12, elevation: 6,
  },
  saveBtnT: { color: '#FFF', fontSize: 15, fontWeight: '700' },

  // Admin
  adminCard: {
    flexDirection: 'row', alignItems: 'center', gap: 14,
    backgroundColor: '#111827', borderRadius: 16, padding: 18,
    marginBottom: 28, borderWidth: 1, borderColor: 'rgba(99,102,241,0.2)',
  },
  adminIcon: {
    width: 48, height: 48, borderRadius: 14,
    backgroundColor: 'rgba(99,102,241,0.1)', justifyContent: 'center', alignItems: 'center',
    borderWidth: 1, borderColor: 'rgba(99,102,241,0.2)',
  },
  adminTitle: { fontSize: 16, fontWeight: '700', color: '#F1F5F9' },
  adminSub: { fontSize: 12, color: '#64748B', marginTop: 2 },
  adminArrow: {
    width: 32, height: 32, borderRadius: 8,
    backgroundColor: 'rgba(99,102,241,0.1)', justifyContent: 'center', alignItems: 'center',
  },

  // Logout - subtle
  logoutBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: 14, borderRadius: 12, gap: 8,
    borderWidth: 1, borderColor: '#1E293B', marginBottom: 16,
  },
  logoutT: { fontSize: 14, fontWeight: '500', color: '#94A3B8' },
  version: { fontSize: 12, color: '#1E293B', textAlign: 'center', marginTop: 8 },
});
