import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator, Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuthStore } from '../../src/store/authStore';
import { Ionicons } from '@expo/vector-icons';

export default function RegisterScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { register, isLoading } = useAuthStore();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [company, setCompany] = useState('');
  const [showPwd, setShowPwd] = useState(false);

  const handleRegister = async () => {
    if (!name.trim() || !email.trim() || !password.trim()) { Alert.alert('Error', 'Fill in all required fields'); return; }
    if (password.length < 6) { Alert.alert('Error', 'Password must be 6+ characters'); return; }
    try { await register(name.trim(), email.trim(), password, company.trim() || undefined); router.replace('/(tabs)'); }
    catch (e: any) { Alert.alert('Registration Failed', e.message); }
  };

  return (
    <KeyboardAvoidingView style={$.flex} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <ScrollView contentContainerStyle={[$.container, { paddingTop: insets.top + 40 }]} keyboardShouldPersistTaps="handled">
        <View style={$.logo}>
          <View style={$.logoIcon}><Ionicons name="tv" size={28} color="#FFF" /></View>
          <Text style={$.logoText}>MediaView</Text>
        </View>
        <View style={$.card}>
          <Text style={$.title}>Create Account</Text>
          <Text style={$.subtitle}>Start advertising on digital screens</Text>
          {[{l:'Full Name *',v:name,s:setName,p:'John Doe',i:'person-outline'},
            {l:'Email *',v:email,s:setEmail,p:'your@email.com',i:'mail-outline',k:'email-address' as any},
          ].map((f,i) => (
            <View key={i} style={$.group}>
              <Text style={$.label}>{f.l}</Text>
              <View style={$.inputW}>
                <Ionicons name={f.i as any} size={20} color="#64748B" style={{marginRight:8}} />
                <TextInput style={$.input} placeholder={f.p} placeholderTextColor="#475569" value={f.v} onChangeText={f.s} keyboardType={f.k} autoCapitalize={f.k?'none':undefined} />
              </View>
            </View>
          ))}
          <View style={$.group}>
            <Text style={$.label}>Password *</Text>
            <View style={$.inputW}>
              <Ionicons name="lock-closed-outline" size={20} color="#64748B" style={{marginRight:8}} />
              <TextInput style={$.input} placeholder="Min 6 characters" placeholderTextColor="#475569" value={password} onChangeText={setPassword} secureTextEntry={!showPwd} />
              <TouchableOpacity onPress={() => setShowPwd(!showPwd)}><Ionicons name={showPwd?'eye-off-outline':'eye-outline'} size={20} color="#64748B" /></TouchableOpacity>
            </View>
          </View>
          <View style={$.group}>
            <Text style={$.label}>Company (Optional)</Text>
            <View style={$.inputW}>
              <Ionicons name="business-outline" size={20} color="#64748B" style={{marginRight:8}} />
              <TextInput style={$.input} placeholder="Your company" placeholderTextColor="#475569" value={company} onChangeText={setCompany} />
            </View>
          </View>
          <TouchableOpacity style={[$.btn, isLoading && $.btnDis]} onPress={handleRegister} disabled={isLoading}>
            {isLoading ? <ActivityIndicator color="#FFF" /> : <Text style={$.btnT}>Create Account</Text>}
          </TouchableOpacity>
        </View>
        <TouchableOpacity style={$.link} onPress={() => router.back()}>
          <Text style={$.linkT}>Already have an account? <Text style={$.linkB}>Sign In</Text></Text>
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const $ = StyleSheet.create({
  flex: { flex: 1, backgroundColor: '#0B0F1A' },
  container: { flexGrow: 1, paddingHorizontal: 24, paddingBottom: 40 },
  logo: { alignItems: 'center', marginBottom: 32 },
  logoIcon: { width: 56, height: 56, borderRadius: 14, backgroundColor: '#6366F1', justifyContent: 'center', alignItems: 'center', marginBottom: 8 },
  logoText: { fontSize: 24, fontWeight: '800', color: '#F1F5F9' },
  card: { backgroundColor: '#111827', borderRadius: 20, padding: 24, borderWidth: 1, borderColor: '#1E293B' },
  title: { fontSize: 24, fontWeight: '700', color: '#F1F5F9', marginBottom: 4 },
  subtitle: { fontSize: 14, color: '#64748B', marginBottom: 24 },
  group: { marginBottom: 14 },
  label: { fontSize: 13, fontWeight: '600', color: '#94A3B8', marginBottom: 6 },
  inputW: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#1F2937', borderWidth: 1, borderColor: '#374151', borderRadius: 12, paddingHorizontal: 12 },
  input: { flex: 1, paddingVertical: 14, fontSize: 16, color: '#F1F5F9' },
  btn: { backgroundColor: '#6366F1', borderRadius: 12, paddingVertical: 16, alignItems: 'center', marginTop: 8 },
  btnDis: { opacity: 0.7 },
  btnT: { color: '#FFF', fontSize: 16, fontWeight: '700' },
  link: { alignItems: 'center', marginTop: 24 },
  linkT: { fontSize: 14, color: '#64748B' },
  linkB: { color: '#818CF8', fontWeight: '700' },
});
