import React from 'react';
import { Stack } from 'expo-router';

export default function PlayerLayout() {
  return <Stack screenOptions={{ headerShown: false, animation: 'fade' }} />;
}
