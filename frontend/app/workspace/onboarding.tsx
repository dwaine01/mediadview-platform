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
  { key: 'welcome', title: 'Bienvenido a MediaView', subtitle: 'Configuremos tus pantallas en 3 pasos simples.' },
  { key: 'connect', title: 'Conecta tu primera pantalla', subtitle: 'Ingresa el código de 6 caracteres que aparece en tu TV.' },
  { key: 'menu', title: 'Crea tu primer menú', subtitle: 'Ponle un nombre a tu menú — los productos los agregas después.' },
  { key: 'publish', title: 'Publica en tu pantalla', subtitle: 'Tu menú aparecerá en vivo en la pantalla conectada.' },
  { key: 'done', title: '¡Ya estás en vivo! 🎉', subtitle: 'Tu contenido ya se ve en tu pantalla.' },
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
    if (code.length < 6) { setError('Ingresa el código de 6 caracteres de tu pantalla.'); return; }
    if (!screenName.trim()) { setError('Ponle un nombre a esta pantalla.'); return; }
    setLoading(true); setError('');
    try {
      const res = await workspaceAPI.connectScreen({ activation_code: code.toUpperCase(), screen_name: screenName.trim() });
      setConnectedScreen(res.data.screen);
      setStep(2);
    } catch (e: any) { setError(e.response?.data?.detail || e.message || 'No se pudo conectar'); }
    finally { setLoading(false); }
  };

  const createMenu = async () => {
    if (!menuName.trim()) { setError('Ingresa un nombre para tu menú.'); return; }
    setLoading(true); setError('');
    try {
      const res = await workspaceAPI.createMenu({ name: menuName.trim(), source: 'blank', items: [] });
      setCreatedMenu(res.data);
      setStep(3);
    } catch (e: any) { setError(e.response?.data?.detail || e.message || 'Ocurrió un error'); }
    finally { setLoading(false); }
  };

  const publishMenu = async () => {
    if (!createdMenu) { setStep(3); return; }
    setLoading(true); setError('');
    try {
      await workspaceAPI.publishMenu(createdMenu.id);
      setStep(4);
    } catch (e: any) { setError(e.response?.data?.detail || e.message || 'Ocurrió un error'); }
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

      {/* Omitir */}
      {step < 4 && (
        <TouchableOpacity style={ob.skipBtn} onPress={skip}>
          <Text style={ob.skipText}>Omitir</Text>
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
            {step === 0 && <Ionicons name="tv" size={52} color="#0891B2" />}
            {step === 1 && <Ionicons name="qr-code" size={52} color="#0891B2" />}
            {step === 2 && <Ionicons name="fast-food" size={52} color="#059669" />}
            {step === 3 && <Ionicons name="cloud-upload" size={52} color="#D97706" />}
            {step === 4 && <Ionicons name="checkmark-circle" size={52} color="#059669" />}
          </View>

          {/* Title & subtitle */}
          <Text style={ob.title}>{STEPS[step].title}</Text>
          <Text style={ob.subtitle}>{STEPS[step].subtitle}</Text>

          {/* Step content */}
          {step === 0 && (
            <View style={ob.stepCard}>
              {['Conecta tu TV o dispositivo Android', 'Crea tu menú digital', 'Publica — en vivo en segundos'].map((item, i) => (
                <View key={i} style={ob.featureRow}>
                  <View style={ob.featureDot}><Text style={{ fontSize: 11, fontWeight: '800', color: '#0891B2' }}>{i + 1}</Text></View>
                  <Text style={ob.featureText}>{item}</Text>
                </View>
              ))}
            </View>
          )}

          {step === 1 && (
            <View style={ob.stepCard}>
              <View style={ob.fieldWrap}>
                <Text style={ob.fieldLabel}>Código que aparece en tu pantalla</Text>
                <TextInput
                  style={ob.codeInput}
                  value={code}
                  onChangeText={t => setCode(t.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 6))}
                  placeholder="XY3K9P"
                  placeholderTextColor="#CBD5E1"
                  autoCapitalize="characters"
                  autoCorrect={false}
                  maxLength={6}
                />
              </View>
              <View style={ob.fieldWrap}>
                <Text style={ob.fieldLabel}>Nombre de la pantalla</Text>
                <TextInput
                  style={ob.textInput}
                  value={screenName}
                  onChangeText={setScreenName}
                  placeholder="ej. Entrada Principal, Mostrador"
                  placeholderTextColor="#CBD5E1"
                />
              </View>
              {!!connectedScreen && (
                <View style={ob.successRow}>
                  <Ionicons name="checkmark-circle" size={18} color="#059669" />
                  <Text style={ob.successText}>Conectada: {connectedScreen.name}</Text>
                </View>
              )}
            </View>
          )}

          {step === 2 && (
            <View style={ob.stepCard}>
              {connectedScreen && (
                <View style={ob.successRow}>
                  <Ionicons name="checkmark-circle" size={16} color="#059669" />
                  <Text style={ob.successText}>Pantalla “{connectedScreen.name}” conectada</Text>
                </View>
              )}
              <View style={ob.fieldWrap}>
                <Text style={ob.fieldLabel}>Nombre del menú</Text>
                <TextInput
                  style={ob.textInput}
                  value={menuName}
                  onChangeText={setMenuName}
                  placeholder="ej. Menú de Almuerzo, Bebidas, Especiales"
                  placeholderTextColor="#CBD5E1"
                />
              </View>
            </View>
          )}

          {step === 3 && (
            <View style={ob.stepCard}>
              {createdMenu && (
                <View style={ob.successRow}>
                  <Ionicons name="checkmark-circle" size={16} color="#059669" />
                  <Text style={ob.successText}>Menú “{createdMenu.name}” creado</Text>
                </View>
              )}
              <Text style={ob.infoText}>
                Presiona Publicar para poner tu menú en vivo. Puedes agregar productos y editar detalles cuando quieras desde la sección Menús.
              </Text>
            </View>
          )}

          {step === 4 && (
            <View style={ob.stepCard}>
              <Text style={ob.infoText}>
                Tu pantalla está conectada y tu menú está publicado. Ahora puedes agregar productos, cambiar precios y editar todo desde la sección Menús.
              </Text>
            </View>
          )}

          {!!error && <Text style={ob.errorText}>{error}</Text>}

          {/* CTA button */}
          <View style={ob.ctaWrap}>
            {step === 0 && (
              <TouchableOpacity style={ob.ctaBtn} onPress={() => setStep(1)}>
                <Text style={ob.ctaBtnText}>Empezar</Text>
                <Ionicons name="arrow-forward" size={18} color="#fff" />
              </TouchableOpacity>
            )}
            {step === 1 && (
              <TouchableOpacity style={[ob.ctaBtn, loading && ob.ctaBtnDisabled]} onPress={connectScreen} disabled={loading}>
                {loading ? <ActivityIndicator color="#fff" size={16} /> : (
                  <><Text style={ob.ctaBtnText}>Conectar Pantalla</Text><Ionicons name="arrow-forward" size={18} color="#fff" /></>
                )}
              </TouchableOpacity>
            )}
            {step === 2 && (
              <TouchableOpacity style={[ob.ctaBtn, loading && ob.ctaBtnDisabled]} onPress={createMenu} disabled={loading}>
                {loading ? <ActivityIndicator color="#fff" size={16} /> : (
                  <><Text style={ob.ctaBtnText}>Crear Menú</Text><Ionicons name="arrow-forward" size={18} color="#fff" /></>
                )}
              </TouchableOpacity>
            )}
            {step === 3 && (
              <><TouchableOpacity style={[ob.ctaBtn, loading && ob.ctaBtnDisabled]} onPress={publishMenu} disabled={loading}>
                  {loading ? <ActivityIndicator color="#fff" size={16} /> : (
                    <><Text style={ob.ctaBtnText}>Publicar en Pantalla</Text><Ionicons name="cloud-upload-outline" size={18} color="#fff" /></>
                  )}
                </TouchableOpacity>
                <TouchableOpacity style={ob.secBtn} onPress={goToMenuEditor}>
                  <Text style={ob.secBtnText}>Agrega productos primero</Text>
                </TouchableOpacity>
              </>
            )}
            {step === 4 && (
              <><TouchableOpacity style={ob.ctaBtn} onPress={goToMenuEditor}>
                  <Text style={ob.ctaBtnText}>Agregar Productos</Text>
                  <Ionicons name="pencil" size={16} color="#fff" />
                </TouchableOpacity>
                <TouchableOpacity style={ob.secBtn} onPress={goToDashboard}>
                  <Text style={ob.secBtnText}>Ir al Panel</Text>
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
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  progressTrack: { height: 3, backgroundColor: '#E2E8F0' },
  progressFill: { height: 3, backgroundColor: '#0891B2', borderRadius: 2 },
  skipBtn: { position: 'absolute', top: 16, right: 20, zIndex: 10, padding: 8 },
  skipText: { fontSize: 13, color: '#64748B', fontWeight: '600' },
  content: { padding: 28, alignItems: 'center', gap: 16, width: '100%', maxWidth: 560, alignSelf: 'center' },
  dots: { flexDirection: 'row', gap: 8 },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#E2E8F0' },
  dotActive: { backgroundColor: '#CFFAFE' },
  dotCurrent: { backgroundColor: '#0891B2', width: 20 },
  iconWrap: { width: 96, height: 96, borderRadius: 28, backgroundColor: '#FFFFFF', justifyContent: 'center', alignItems: 'center', marginTop: 8 },
  title: { fontSize: 26, fontWeight: '800', color: '#0F172A', textAlign: 'center' },
  subtitle: { fontSize: 15, color: '#64748B', textAlign: 'center', lineHeight: 22 },
  stepCard: { width: '100%', backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 16, padding: 20, gap: 14 },
  featureRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  featureDot: { width: 22, height: 22, borderRadius: 11, backgroundColor: '#ECFEFF', alignItems: 'center', justifyContent: 'center' },
  featureText: { fontSize: 15, color: '#334155', fontWeight: '500' },
  fieldWrap: { gap: 8 },
  fieldLabel: { fontSize: 11, fontWeight: '700', color: '#64748B', textTransform: 'uppercase', letterSpacing: 0.5 },
  codeInput: { fontSize: 30, fontWeight: '800', color: '#0F172A', textAlign: 'center', letterSpacing: 10, backgroundColor: '#F8FAFC', borderWidth: 2, borderColor: '#0891B2', borderRadius: 14, paddingVertical: 14, paddingHorizontal: 20 },
  textInput: { fontSize: 15, color: '#0F172A', backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 10, padding: 14 },
  successRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  successText: { fontSize: 13, color: '#059669', fontWeight: '600' },
  infoText: { fontSize: 14, color: '#64748B', lineHeight: 22, textAlign: 'center' },
  errorText: { color: '#DC2626', fontSize: 13, textAlign: 'center', width: '100%' },
  ctaWrap: { width: '100%', gap: 10, marginTop: 8 },
  ctaBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, backgroundColor: '#0891B2', borderRadius: 14, padding: 18 },
  ctaBtnDisabled: { opacity: 0.6 },
  ctaBtnText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  secBtn: { alignItems: 'center', padding: 14 },
  secBtnText: { color: '#64748B', fontSize: 14, fontWeight: '600' },
});
