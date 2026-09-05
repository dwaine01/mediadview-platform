import React, { useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextInput,
  ActivityIndicator, ScrollView, KeyboardAvoidingView, Platform
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { workspaceAPI } from '../../src/services/api';

const STEPS = [
  { key: 'welcome', title: 'Welcome to MediaView', subtitle: 'Let’s set up your digital signage in 3 simple steps.' },
  { key: 'connect', title: 'Connect your first screen', subtitle: 'Enter the 6-character code shown on your TV or device.' },
  { key: 'menu', title: 'Create your first menu', subtitle: 'Give your menu a name — you’ll add items next.' },
  { key: 'publish', title: 'Publish to your screen', subtitle: 'Your menu will appear live on the connected screen.' },
  { key: 'done', title: 'You’re live! 🎉', subtitle: 'Your content is now visible on your screen.' },
];

export default function Onboarding() {
  const insets = useSafeAreaInsets();
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Step 1 state
  const [code, setCode] = useState('');
  const [screenName, setScreenName] = useState('');
  const [connectedScreen, setConnectedScreen] = useState<any>(null);

  // Step 2 state
  const [menuName, setMenuName] = useState('');
  const [createdMenu, setCreatedMenu] = useState<any>(null);

  const connectScreen = async () => {
    if (code.length < 6) { setError('Enter the 6-character code from your screen.'); return; }
    if (!screenName.trim()) { setError('Give this screen a name.'); return; }
    setLoading(true); setError('');
    try {
      const res = await workspaceAPI.connectScreen({ activation_code: code.toUpperCase(), screen_name: screenName.trim() });
      setConnectedScreen(res.data.screen);
      setStep(2);
    } catch (e: any) { setError(e.response?.data?.detail || e.message || 'Connection failed'); }
    finally { setLoading(false); }
  };

  const createMenu = async () => {
    if (!menuName.trim()) { setError('Enter a name for your menu.'); return; }
    setLoading(true); setError('');
    try {
      const res = await workspaceAPI.createMenu({ name: menuName.trim(), source: 'blank', items: [] });
      setCreatedMenu(res.data);
      setStep(3);
    } catch (e: any) { setError(e.response?.data?.detail || e.message || 'Failed'); }
    finally { setLoading(false); }
  };

  const publishMenu = async () => {
    if (!createdMenu) { setStep(3); return; }
    setLoading(true); setError('');
    try {
      await workspaceAPI.publishMenu(createdMenu.id);
      setStep(4);
    } catch (e: any) { setError(e.response?.data?.detail || e.message || 'Failed'); }
    finally { setLoading(false); }
  };

  const skip = () => router.replace('/workspace');
  const goToDashboard = () => router.replace('/workspace');
  const goToMenuEditor = () => {
    if (createdMenu) router.replace({ pathname: '/workspace/menu-edit', params: { id: createdMenu.id } });
    else router.replace('/workspace/menus');
  };

  const prog = (step / (STEPS.length - 1)) * 100;

  return (
    <View style={[ob.root, { paddingTop: insets.top }]}>
      {/* Progress bar */}
      <View style={ob.progressTrack}>
        <View style={[ob.progressFill, { width: `${prog}%` }]} />
      </View>

      {/* Skip */}
      {step < 4 && (
        <TouchableOpacity style={ob.skipBtn} onPress={skip}>
          <Text style={ob.skipText}>Skip</Text>
        </TouchableOpacity>
      )}

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={[ob.content, { paddingBottom: insets.bottom + 32 }]} keyboardShouldPersistTaps="handled">
          {/* Step indicator dots */}
          <View style={ob.dots}>
            {STEPS.map((_, i) => (
              <View key={i} style={[ob.dot, i <= step && ob.dotActive, i === step && ob.dotCurrent]} />
            ))}
          </View>

          {/* Step icon */}
          <View style={ob.iconWrap}>
            {step === 0 && <Ionicons name="tv" size={52} color="#818CF8" />}
            {step === 1 && <Ionicons name="qr-code" size={52} color="#818CF8" />}
            {step === 2 && <Ionicons name="fast-food" size={52} color="#34D399" />}
            {step === 3 && <Ionicons name="cloud-upload" size={52} color="#F59E0B" />}
            {step === 4 && <Ionicons name="checkmark-circle" size={52} color="#34D399" />}
          </View>

          {/* Title & subtitle */}
          <Text style={ob.title}>{STEPS[step].title}</Text>
          <Text style={ob.subtitle}>{STEPS[step].subtitle}</Text>

          {/* Step content */}
          {step === 0 && (
            <View style={ob.stepCard}>
              {['📺 Connect your TV or Android device', '🍽️ Create your digital menu', '📡 Publish — live in seconds'].map((item, i) => (
                <View key={i} style={ob.featureRow}>
                  <Text style={ob.featureText}>{item}</Text>
                </View>
              ))}
            </View>
          )}

          {step === 1 && (
            <View style={ob.stepCard}>
              <View style={ob.fieldWrap}>
                <Text style={ob.fieldLabel}>Code shown on your screen</Text>
                <TextInput
                  style={ob.codeInput}
                  value={code}
                  onChangeText={t => setCode(t.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 6))}
                  placeholder="XY3K9P"
                  placeholderTextColor="#374151"
                  autoCapitalize="characters"
                  autoCorrect={false}
                  maxLength={6}
                />
              </View>
              <View style={ob.fieldWrap}>
                <Text style={ob.fieldLabel}>Screen name</Text>
                <TextInput
                  style={ob.textInput}
                  value={screenName}
                  onChangeText={setScreenName}
                  placeholder="e.g. Main Entrance, Counter"
                  placeholderTextColor="#374151"
                />
              </View>
              {!!connectedScreen && (
                <View style={ob.successRow}>
                  <Ionicons name="checkmark-circle" size={18} color="#34D399" />
                  <Text style={ob.successText}>Connected: {connectedScreen.name}</Text>
                </View>
              )}
            </View>
          )}

          {step === 2 && (
            <View style={ob.stepCard}>
              {connectedScreen && (
                <View style={ob.successRow}>
                  <Ionicons name="checkmark-circle" size={16} color="#34D399" />
                  <Text style={ob.successText}>Screen “{connectedScreen.name}” connected</Text>
                </View>
              )}
              <View style={ob.fieldWrap}>
                <Text style={ob.fieldLabel}>Menu name</Text>
                <TextInput
                  style={ob.textInput}
                  value={menuName}
                  onChangeText={setMenuName}
                  placeholder="e.g. Lunch Menu, Drinks, Daily Specials"
                  placeholderTextColor="#374151"
                />
              </View>
            </View>
          )}

          {step === 3 && (
            <View style={ob.stepCard}>
              {createdMenu && (
                <View style={ob.successRow}>
                  <Ionicons name="checkmark-circle" size={16} color="#34D399" />
                  <Text style={ob.successText}>Menu “{createdMenu.name}” created</Text>
                </View>
              )}
              <Text style={ob.infoText}>
                Tap Publish to make your menu live. You can add items and edit details at any time from the Menus section.
              </Text>
            </View>
          )}

          {step === 4 && (
            <View style={ob.stepCard}>
              <Text style={ob.infoText}>
                Your screen is connected and your menu is published. You can now add items, edit prices, and make changes from the Menus section.
              </Text>
            </View>
          )}

          {!!error && <Text style={ob.errorText}>{error}</Text>}

          {/* CTA button */}
          <View style={ob.ctaWrap}>
            {step === 0 && (
              <TouchableOpacity style={ob.ctaBtn} onPress={() => setStep(1)}>
                <Text style={ob.ctaBtnText}>Get Started</Text>
                <Ionicons name="arrow-forward" size={18} color="#fff" />
              </TouchableOpacity>
            )}
            {step === 1 && (
              <TouchableOpacity style={[ob.ctaBtn, loading && ob.ctaBtnDisabled]} onPress={connectScreen} disabled={loading}>
                {loading ? <ActivityIndicator color="#fff" size={16} /> : (
                  <><Text style={ob.ctaBtnText}>Connect Screen</Text><Ionicons name="arrow-forward" size={18} color="#fff" /></>
                )}
              </TouchableOpacity>
            )}
            {step === 2 && (
              <TouchableOpacity style={[ob.ctaBtn, loading && ob.ctaBtnDisabled]} onPress={createMenu} disabled={loading}>
                {loading ? <ActivityIndicator color="#fff" size={16} /> : (
                  <><Text style={ob.ctaBtnText}>Create Menu</Text><Ionicons name="arrow-forward" size={18} color="#fff" /></>
                )}
              </TouchableOpacity>
            )}
            {step === 3 && (
              <><TouchableOpacity style={[ob.ctaBtn, loading && ob.ctaBtnDisabled]} onPress={publishMenu} disabled={loading}>
                  {loading ? <ActivityIndicator color="#fff" size={16} /> : (
                    <><Text style={ob.ctaBtnText}>Publish to Screen</Text><Ionicons name="cloud-upload-outline" size={18} color="#fff" /></>
                  )}
                </TouchableOpacity>
                <TouchableOpacity style={ob.secBtn} onPress={goToMenuEditor}>
                  <Text style={ob.secBtnText}>Add items first</Text>
                </TouchableOpacity>
              </>
            )}
            {step === 4 && (
              <><TouchableOpacity style={ob.ctaBtn} onPress={goToMenuEditor}>
                  <Text style={ob.ctaBtnText}>Add Menu Items</Text>
                  <Ionicons name="pencil" size={16} color="#fff" />
                </TouchableOpacity>
                <TouchableOpacity style={ob.secBtn} onPress={goToDashboard}>
                  <Text style={ob.secBtnText}>Go to Dashboard</Text>
                </TouchableOpacity>
              </>
            )}
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

const ob = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0B0F1A' },
  progressTrack: { height: 3, backgroundColor: '#1E293B' },
  progressFill: { height: 3, backgroundColor: '#6366F1', borderRadius: 2 },
  skipBtn: { position: 'absolute', top: 16, right: 20, zIndex: 10, padding: 8 },
  skipText: { fontSize: 13, color: '#64748B', fontWeight: '600' },
  content: { padding: 28, alignItems: 'center', gap: 16 },
  dots: { flexDirection: 'row', gap: 8 },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#1E293B' },
  dotActive: { backgroundColor: '#312E81' },
  dotCurrent: { backgroundColor: '#6366F1', width: 20 },
  iconWrap: { width: 96, height: 96, borderRadius: 28, backgroundColor: '#111827', justifyContent: 'center', alignItems: 'center', marginTop: 8 },
  title: { fontSize: 26, fontWeight: '800', color: '#F1F5F9', textAlign: 'center' },
  subtitle: { fontSize: 15, color: '#64748B', textAlign: 'center', lineHeight: 22 },
  stepCard: { width: '100%', backgroundColor: '#111827', borderWidth: 1, borderColor: '#1E293B', borderRadius: 16, padding: 20, gap: 14 },
  featureRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  featureText: { fontSize: 15, color: '#D1D5DB', fontWeight: '500' },
  fieldWrap: { gap: 8 },
  fieldLabel: { fontSize: 11, fontWeight: '700', color: '#64748B', textTransform: 'uppercase', letterSpacing: 0.5 },
  codeInput: { fontSize: 30, fontWeight: '800', color: '#F1F5F9', textAlign: 'center', letterSpacing: 10, backgroundColor: '#0B0F1A', borderWidth: 2, borderColor: '#6366F1', borderRadius: 14, paddingVertical: 14, paddingHorizontal: 20 },
  textInput: { fontSize: 15, color: '#F1F5F9', backgroundColor: '#0B0F1A', borderWidth: 1, borderColor: '#1E293B', borderRadius: 10, padding: 14 },
  successRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  successText: { fontSize: 13, color: '#34D399', fontWeight: '600' },
  infoText: { fontSize: 14, color: '#9CA3AF', lineHeight: 22, textAlign: 'center' },
  errorText: { color: '#F87171', fontSize: 13, textAlign: 'center', width: '100%' },
  ctaWrap: { width: '100%', gap: 10, marginTop: 8 },
  ctaBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, backgroundColor: '#6366F1', borderRadius: 14, padding: 18 },
  ctaBtnDisabled: { opacity: 0.6 },
  ctaBtnText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  secBtn: { alignItems: 'center', padding: 14 },
  secBtnText: { color: '#64748B', fontSize: 14, fontWeight: '600' },
});
