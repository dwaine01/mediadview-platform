import React, { useEffect } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useAuthStore } from '../src/store/authStore';

export default function RootLayout() {
  const initialize = useAuthStore((s) => s.initialize);

  useEffect(() => {
    initialize();
  // initialize is a stable zustand action — intentional single run on mount
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="index" />
        <Stack.Screen name="(auth)" />
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="campaign/create" />
        <Stack.Screen name="campaign/[id]" />
        <Stack.Screen name="screen/[id]" />
        <Stack.Screen name="admin/index" />
        <Stack.Screen name="player" />
      </Stack>
    </>
  );
}
