import React from 'react';
import { View, ActivityIndicator, StyleSheet } from 'react-native';
import { Redirect } from 'expo-router';
import { useAuthStore, isWorkspaceUser } from '../src/store/authStore';

export default function Index() {
  const { token, user, isInitialized } = useAuthStore();

  if (!isInitialized) {
    return (
      <View style={styles.container}>
        <ActivityIndicator size="large" color="#4F46E5" />
      </View>
    );
  }

  if (token) {
    // Phase 2C P1: workspace customers go to /workspace
    if (isWorkspaceUser(user)) {
      return <Redirect href="/workspace" />;
    }
    return <Redirect href="/(tabs)" />;
  }
  return <Redirect href="/(auth)/login" />;
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#0B0F1A',
  },
});
