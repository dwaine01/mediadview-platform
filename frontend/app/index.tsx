import React, { useEffect } from 'react';
import { View, Text, StyleSheet, ActivityIndicator } from 'react-native';
import { router } from 'expo-router';
import { useAuthStore } from '../src/store/authStore';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';

// Company logo - Ohio Airbag Light Reset
const CompanyLogo = () => (
  <View style={logoStyles.container}>
    {/* Icon row with car, airbag, lightning */}
    <View style={logoStyles.iconRow}>
      <View style={logoStyles.iconCircle}>
        <Ionicons name="car" size={28} color="#D4A017" />
      </View>
      <View style={logoStyles.iconCircle}>
        <MaterialCommunityIcons name="airbag" size={28} color="#D4A017" />
      </View>
      <View style={logoStyles.iconCircle}>
        <Ionicons name="flash" size={28} color="#D4A017" />
      </View>
    </View>
    {/* OHIO text */}
    <Text style={logoStyles.ohioText}>OHIO</Text>
    {/* AIRBAG LIGHT text */}
    <Text style={logoStyles.airbagText}>AIRBAG LIGHT</Text>
    {/* RESET text */}
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
    justifyContent: 'center',
    gap: 16,
    marginBottom: 20,
  },
  iconCircle: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: 'rgba(212, 160, 23, 0.15)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  ohioText: {
    fontSize: 64,
    fontWeight: '900',
    color: '#D4A017',
    letterSpacing: 14,
    textShadowColor: 'rgba(212, 160, 23, 0.4)',
    textShadowOffset: { width: 0, height: 3 },
    textShadowRadius: 6,
  },
  airbagText: {
    fontSize: 22,
    fontWeight: '800',
    color: '#FFFFFF',
    letterSpacing: 8,
    marginTop: 4,
  },
  resetText: {
    fontSize: 48,
    fontWeight: '900',
    color: '#D4A017',
    letterSpacing: 18,
    marginTop: 6,
    textShadowColor: 'rgba(212, 160, 23, 0.4)',
    textShadowOffset: { width: 0, height: 3 },
    textShadowRadius: 6,
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
      <ActivityIndicator size="large" color="#D4A017" style={styles.loader} />
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
    marginTop: 50,
  },
});
