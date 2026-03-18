import React, { useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  TextInput, Alert, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useAuthStore } from '../../src/store/authStore';
import { authAPI } from '../../src/services/api';

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
      Alert.alert('Error', e.response?.data?.detail || 'Failed to update profile');
    } finally {
      setSaving(false);
    }
  };

  const handleLogout = () => {
    Alert.alert('Logout', 'Are you sure you want to sign out?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Sign Out', style: 'destructive', onPress: async () => {
        await logout();
        router.replace('/(auth)/login');
      }},
    ]);
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ paddingTop: insets.top + 16, paddingBottom: 100 }}>
      <Text style={styles.title}>Profile</Text>

      <View style={styles.avatarSection}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>{user?.name?.charAt(0)?.toUpperCase() || 'U'}</Text>
        </View>
        <Text style={styles.avatarName}>{user?.name}</Text>
        <Text style={styles.avatarEmail}>{user?.email}</Text>
        <View style={[styles.roleBadge, { backgroundColor: user?.role === 'admin' ? '#EEF2FF' : '#F0FDF4' }]}>
          <Text style={[styles.roleText, { color: user?.role === 'admin' ? '#4F46E5' : '#16A34A' }]}>
            {user?.role?.toUpperCase()}
          </Text>
        </View>
      </View>

      <View style={styles.section}>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Account Information</Text>
          <TouchableOpacity onPress={() => setEditing(!editing)}>
            <Ionicons name={editing ? 'close' : 'create-outline'} size={20} color="#4F46E5" />
          </TouchableOpacity>
        </View>

        <View style={styles.infoCard}>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Full Name</Text>
            {editing ? (
              <TextInput style={styles.editInput} value={name} onChangeText={setName} />
            ) : (
              <Text style={styles.infoValue}>{user?.name}</Text>
            )}
          </View>
          <View style={styles.divider} />
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Email</Text>
            <Text style={styles.infoValue}>{user?.email}</Text>
          </View>
          <View style={styles.divider} />
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Company</Text>
            {editing ? (
              <TextInput style={styles.editInput} value={company} onChangeText={setCompany} placeholder="Company name" placeholderTextColor="#94A3B8" />
            ) : (
              <Text style={styles.infoValue}>{user?.company_name || 'Not set'}</Text>
            )}
          </View>
        </View>

        {editing && (
          <TouchableOpacity style={styles.saveBtn} onPress={handleSave} disabled={saving}>
            {saving ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.saveBtnText}>Save Changes</Text>}
          </TouchableOpacity>
        )}
      </View>

      {user?.role === 'admin' && (
        <TouchableOpacity style={styles.adminCard} onPress={() => router.push('/admin')}>
          <View style={styles.adminCardInner}>
            <View style={styles.adminIcon}>
              <Ionicons name="shield-checkmark" size={24} color="#4F46E5" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.adminCardTitle}>Admin Panel</Text>
              <Text style={styles.adminCardSub}>Manage users, screens, and campaigns</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color="#94A3B8" />
          </View>
        </TouchableOpacity>
      )}

      <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout}>
        <Ionicons name="log-out-outline" size={20} color="#EF4444" />
        <Text style={styles.logoutText}>Sign Out</Text>
      </TouchableOpacity>

      <Text style={styles.versionText}>MediaView v1.0.0</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F1F5F9', paddingHorizontal: 20 },
  title: { fontSize: 24, fontWeight: '700', color: '#0F172A', marginBottom: 24 },
  avatarSection: { alignItems: 'center', marginBottom: 28 },
  avatar: {
    width: 72, height: 72, borderRadius: 36, backgroundColor: '#4F46E5',
    justifyContent: 'center', alignItems: 'center', marginBottom: 12,
  },
  avatarText: { fontSize: 28, fontWeight: '700', color: '#FFFFFF' },
  avatarName: { fontSize: 20, fontWeight: '700', color: '#0F172A' },
  avatarEmail: { fontSize: 14, color: '#64748B', marginTop: 2 },
  roleBadge: { paddingHorizontal: 12, paddingVertical: 4, borderRadius: 8, marginTop: 8 },
  roleText: { fontSize: 11, fontWeight: '700' },
  section: { marginBottom: 24 },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  sectionTitle: { fontSize: 16, fontWeight: '600', color: '#0F172A' },
  infoCard: {
    backgroundColor: '#FFFFFF', borderRadius: 16, padding: 4,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04, shadowRadius: 6, elevation: 2,
  },
  infoRow: { paddingHorizontal: 16, paddingVertical: 14 },
  infoLabel: { fontSize: 12, color: '#64748B', marginBottom: 4 },
  infoValue: { fontSize: 15, fontWeight: '500', color: '#0F172A' },
  divider: { height: 1, backgroundColor: '#F1F5F9', marginHorizontal: 16 },
  editInput: {
    fontSize: 15, fontWeight: '500', color: '#0F172A',
    backgroundColor: '#F8FAFC', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8,
    borderWidth: 1, borderColor: '#E2E8F0',
  },
  saveBtn: {
    backgroundColor: '#4F46E5', borderRadius: 12, paddingVertical: 14,
    alignItems: 'center', marginTop: 12,
  },
  saveBtnText: { color: '#FFFFFF', fontSize: 15, fontWeight: '700' },
  adminCard: {
    backgroundColor: '#FFFFFF', borderRadius: 16, padding: 16, marginBottom: 24,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04, shadowRadius: 6, elevation: 2,
  },
  adminCardInner: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  adminIcon: {
    width: 44, height: 44, borderRadius: 12, backgroundColor: '#EEF2FF',
    justifyContent: 'center', alignItems: 'center',
  },
  adminCardTitle: { fontSize: 16, fontWeight: '600', color: '#0F172A' },
  adminCardSub: { fontSize: 13, color: '#64748B', marginTop: 2 },
  logoutBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    backgroundColor: '#FEF2F2', borderRadius: 14, paddingVertical: 14, gap: 8,
    marginBottom: 16,
  },
  logoutText: { fontSize: 15, fontWeight: '600', color: '#EF4444' },
  versionText: { fontSize: 12, color: '#CBD5E1', textAlign: 'center', marginTop: 8 },
});
