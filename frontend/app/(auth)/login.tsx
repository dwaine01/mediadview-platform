import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Alert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  ActivityIndicator,
} from 'react-native';
import { router } from 'expo-router';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import { login } from '../../src/services/api';
import { useAuthStore } from '../../src/store/authStore';

// Company logo - Ohio Airbag Light Reset
const CompanyLogo = () => (
  <View style={logoStyles.container}>
    {/* Icon row with car, airbag, lightning */}
    <View style={logoStyles.iconRow}>
      <View style={logoStyles.iconCircle}>
        <Ionicons name="car" size={26} color="#D4A017" />
      </View>
      <View style={logoStyles.iconCircle}>
        <MaterialCommunityIcons name="airbag" size={26} color="#D4A017" />
      </View>
      <View style={logoStyles.iconCircle}>
        <Ionicons name="flash" size={26} color="#D4A017" />
      </View>
    </View>
    {/* OHIO text */}
    <Text style={logoStyles.ohioText}>OHIO</Text>
    {/* AIRBAG LIGHT text */}
    <Text style={logoStyles.airbagText}>AIRBAG LIGHT</Text>
    {/* RESET text */}
    <Text style={logoStyles.resetText}>RESET</Text>
    {/* Decorative line */}
    <View style={logoStyles.decorLine} />
  </View>
);

const logoStyles = StyleSheet.create({
  container: {
    alignItems: 'center',
    marginBottom: 40,
  },
  iconRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    marginBottom: 16,
  },
  iconCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: 'rgba(212, 160, 23, 0.15)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  ohioText: {
    fontSize: 56,
    fontWeight: '900',
    color: '#D4A017',
    letterSpacing: 12,
    textShadowColor: 'rgba(212, 160, 23, 0.3)',
    textShadowOffset: { width: 0, height: 2 },
    textShadowRadius: 4,
  },
  airbagText: {
    fontSize: 20,
    fontWeight: '800',
    color: '#FFFFFF',
    letterSpacing: 6,
    marginTop: 2,
  },
  resetText: {
    fontSize: 42,
    fontWeight: '900',
    color: '#D4A017',
    letterSpacing: 16,
    marginTop: 4,
    textShadowColor: 'rgba(212, 160, 23, 0.3)',
    textShadowOffset: { width: 0, height: 2 },
    textShadowRadius: 4,
  },
  decorLine: {
    width: 120,
    height: 3,
    backgroundColor: '#D4A017',
    marginTop: 16,
    borderRadius: 2,
  },
});

export default function LoginScreen() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const { setAuth } = useAuthStore();

  const handleLogin = async () => {
    if (!email.trim() || !password.trim()) {
      Alert.alert('Error', 'Por favor ingrese email y contraseña');
      return;
    }

    setLoading(true);
    try {
      const response = await login(email.trim(), password);
      await setAuth(response.user, response.access_token);
      router.replace('/(tabs)');
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Error al iniciar sesión';
      Alert.alert('Error', message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.logoContainer}>
          <CompanyLogo />
          <Text style={styles.subtitle}>Iniciar Sesión</Text>
        </View>

        <View style={styles.form}>
          <View style={styles.inputContainer}>
            <Ionicons name="mail-outline" size={20} color="#9CA3AF" style={styles.inputIcon} />
            <TextInput
              style={styles.input}
              placeholder="Email"
              placeholderTextColor="#6B7280"
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
              keyboardType="email-address"
            />
          </View>

          <View style={styles.inputContainer}>
            <Ionicons name="lock-closed-outline" size={20} color="#9CA3AF" style={styles.inputIcon} />
            <TextInput
              style={styles.input}
              placeholder="Contraseña"
              placeholderTextColor="#6B7280"
              value={password}
              onChangeText={setPassword}
              secureTextEntry={!showPassword}
            />
            <TouchableOpacity onPress={() => setShowPassword(!showPassword)}>
              <Ionicons
                name={showPassword ? 'eye-off-outline' : 'eye-outline'}
                size={20}
                color="#9CA3AF"
              />
            </TouchableOpacity>
          </View>

          <TouchableOpacity
            style={[styles.button, loading && styles.buttonDisabled]}
            onPress={handleLogin}
            disabled={loading}
          >
            {loading ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.buttonText}>Ingresar</Text>
            )}
          </TouchableOpacity>

          <Text style={styles.contactText}>
            Contacta al administrador para obtener acceso
          </Text>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#111827',
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: 20,
  },
  logoContainer: {
    alignItems: 'center',
    marginBottom: 40,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginTop: 16,
  },
  subtitle: {
    fontSize: 16,
    color: '#9CA3AF',
    marginTop: 8,
  },
  form: {
    width: '100%',
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1F2937',
    borderRadius: 12,
    paddingHorizontal: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#374151',
  },
  inputIcon: {
    marginRight: 12,
  },
  input: {
    flex: 1,
    height: 50,
    color: '#FFFFFF',
    fontSize: 16,
  },
  button: {
    backgroundColor: '#3B82F6',
    borderRadius: 12,
    height: 50,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 8,
  },
  buttonDisabled: {
    opacity: 0.7,
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
  contactText: {
    marginTop: 24,
    color: '#6B7280',
    fontSize: 14,
    textAlign: 'center',
  },
});
