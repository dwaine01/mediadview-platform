import React, { useEffect } from 'react';
import { View, Text, StyleSheet, ActivityIndicator } from 'react-native';
import { router } from 'expo-router';
import { useAuthStore } from '../src/store/authStore';
import { Ionicons } from '@expo/vector-icons';

// Company logo component
const CompanyLogo = () => (
  <View style={logoStyles.container}>
    <View style={logoStyles.iconRow}>
      <Ionicons name="car" size={28} color="#F59E0B" />
      <Ionicons name="ellipse" size={24} color="#F59E0B" />
      <Ionicons name="flash" size={28} color="#F59E0B" />
    </View>
    <Text style={logoStyles.mainText}>OHIO</Text>
    <Text style={logoStyles.subText}>AIRBAG LIGHT</Text>
    <Text style={logoStyles.resetText}>RESET</Text>
  </View>
);

const logoStyles = StyleSheet.create({
  container: {
    alignItems: 'center',
  },
  iconRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 8,
  },
  mainText: {
    fontSize: 48,
    fontWeight: '900',
    color: '#F59E0B',
    letterSpacing: 8,
  },
  subText: {
    fontSize: 20,
    fontWeight: '700',
    color: '#FFFFFF',
    letterSpacing: 4,
    marginTop: 4,
  },
  resetText: {
    fontSize: 36,
    fontWeight: '900',
    color: '#F59E0B',
    letterSpacing: 12,
    marginTop: 4,
  },
});

export default function Index() {
  const { user, isLoading } = useAuthStore();

  useEffect(() => {
    if (!isLoading) {
      if (user) {
        router.replace('/(tabs)');
      } else {
        router.replace('/(auth)/login');
      }
    }
  }, [user, isLoading]);

  return (
    <View style={styles.container}>
      <CompanyLogo />
      <ActivityIndicator size="large" color="#F59E0B" style={styles.loader} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#111827',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 20,
  },
  loader: {
    marginTop: 40,
  },
});
