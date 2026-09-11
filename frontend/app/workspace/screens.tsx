import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity, TextInput,
  ActivityIndicator, Modal, useWindowDimensions, KeyboardAvoidingView, Platform
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { workspaceAPI } from '../../src/services/api';
import { formatScreenLocation, type ScreenLocation } from '../../src/utils/screenLocation';

type Screen = {
  id: string; name: string; status: string; code?: string;
  location?: ScreenLocation; active_menu_id?: string; created_at?: string;
  specs?: { orientation?: string };
};

const orientationOf = (s: Screen) => (s.specs?.orientation === 'portrait' ? 'portrait' : 'landscape');

function OrientationPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <View style={ss.fieldWrap}>
      <Text style={ss.inputLabel}>Orientación de la Pantalla</Text>
      <View style={ss.orientRow}>
        {(['landscape', 'portrait'] as const).map((opt) => {
          const on = value === opt;
          return (
            <TouchableOpacity
              key={opt}
              style={[ss.orientOpt, on && ss.orientOptOn]}
              onPress={() => onChange(opt)}
              activeOpacity={0.85}
            >
              <View style={[opt === 'portrait' ? ss.shapePortrait : ss.shapeLandscape, on && ss.shapeOn]} />
              <Text style={[ss.orientLabel, on && ss.orientLabelOn]}>
                {opt === 'portrait' ? 'Vertical' : 'Horizontal'}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
      <Text style={ss.codeHint}>
        El televisor se coloca solo en esta orientación y tus diseños deben subirse así.
      </Text>
    </View>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, { bg: string; text: string }> = {
    active: { bg: '#D1FAE5', text: '#059669' },
    offline: { bg: '#F8FAFC', text: '#64748B' },
    pending: { bg: '#ECFEFF', text: '#0891B2' },
  };
  const labels: Record<string, string> = {
    active: 'Activa', offline: 'Desconectada', pending: 'Pendiente',
  };
  const c = colors[status] || colors.offline;
  return (
    <View style={[ss.badge, { backgroundColor: c.bg }]}>
      <Text style={[ss.badgeText, { color: c.text }]}>{labels[status] || status}</Text>
    </View>
  );
}

export default function WorkspaceScreens() {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const [screens, setScreens] = useState<Screen[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showConnect, setShowConnect] = useState(false);
  const [code, setCode] = useState('');
  const [screenName, setScreenName] = useState('');
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState('');
  const [connectSuccess, setConnectSuccess] = useState('');
  const [orientation, setOrientation] = useState('landscape');
  const [savingOrient, setSavingOrient] = useState<string | null>(null);
  const [unlinkTarget, setUnlinkTarget] = useState<Screen | null>(null);
  const [unlinking, setUnlinking] = useState(false);
  const [unlinkError, setUnlinkError] = useState('');
  const [unlinkDone, setUnlinkDone] = useState('');

  const load = useCallback(async () => {
    try {
      setLoading(true); setError('');
      const res = await workspaceAPI.screens();
      setScreens(res.data || []);
    } catch (e: any) { setError(e.response?.data?.detail || e.message || 'No se pudo cargar'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openConnect = () => {
    setCode(''); setScreenName(''); setOrientation('landscape');
    setConnectError(''); setConnectSuccess('');
    setShowConnect(true);
  };

  const toggleOrientation = async (s: Screen) => {
    const next = orientationOf(s) === 'portrait' ? 'landscape' : 'portrait';
    setSavingOrient(s.id);
    try {
      await workspaceAPI.updateScreen(s.id, { orientation: next });
      setScreens(prev => prev.map(x => (x.id === s.id ? { ...x, specs: { ...x.specs, orientation: next } } : x)));
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'No se pudo cambiar la orientación');
    } finally { setSavingOrient(null); }
  };

  const openUnlink = (s: Screen) => {
    setUnlinkTarget(s); setUnlinkError(''); setUnlinkDone('');
  };

  const confirmUnlink = async () => {
    if (!unlinkTarget) return;
    setUnlinking(true); setUnlinkError('');
    try {
      const res = await workspaceAPI.deleteScreen(unlinkTarget.id);
      setUnlinkDone(res.data?.message || 'Pantalla desvinculada.');
      setScreens(prev => prev.filter(x => x.id !== unlinkTarget.id));
      setTimeout(() => { setUnlinkTarget(null); setUnlinkDone(''); }, 2600);
    } catch (e: any) {
      setUnlinkError(e.response?.data?.detail || e.message || 'No se pudo desvincular');
    } finally { setUnlinking(false); }
  };

  const handleConnect = async () => {
    if (code.trim().length < 6) { setConnectError('Please enter the 6-character code from your screen.'); return; }
    if (!screenName.trim()) { setConnectError('Please enter a name for this screen.'); return; }
    setConnecting(true); setConnectError('');
    try {
      const res = await workspaceAPI.connectScreen({
        activation_code: code.trim().toUpperCase(),
        screen_name: screenName.trim(),
        orientation,
      });
      setConnectSuccess(res.data?.message || 'Screen connected!');
      load();
      setTimeout(() => { setShowConnect(false); setConnectSuccess(''); }, 2000);
    } catch (e: any) {
      setConnectError(e.response?.data?.detail || e.message || 'Connection failed');
    } finally { setConnecting(false); }
  };

  return (
    <View style={ss.root}>
      <ScrollView contentContainerStyle={[ss.content, { paddingBottom: insets.bottom + 24 }]}>
        {/* Header */}
        <View style={ss.header}>
          <View>
            <Text style={ss.pageTitle}>Pantallas</Text>
            <Text style={ss.pageSub}>{screens.length} pantalla{screens.length !== 1 ? 's' : ''} conectada{screens.length !== 1 ? 's' : ''}</Text>
          </View>
          <TouchableOpacity style={ss.addBtn} onPress={openConnect}>
            <Ionicons name="add" size={16} color="#fff" />
            <Text style={ss.addBtnText}>Conectar Pantalla</Text>
          </TouchableOpacity>
        </View>

        {loading && <ActivityIndicator color="#0891B2" style={{ marginTop: 40 }} />}
        {!!error && !loading && <Text style={ss.errorText}>{error}</Text>}

        {!loading && screens.length === 0 && !error && (
          <View style={ss.empty}>
            <View style={ss.emptyIcon}>
              <Ionicons name="tv-outline" size={40} color="#CBD5E1" />
            </View>
            <Text style={ss.emptyTitle}>Todavía no tienes pantallas</Text>
            <Text style={ss.emptyText}>Connect your first screen by entering the 6-character code shown on your TV.</Text>
            <TouchableOpacity style={[ss.addBtn, { marginTop: 16 }]} onPress={openConnect}>
              <Ionicons name="add" size={16} color="#fff" />
              <Text style={ss.addBtnText}>Conectar Primera Pantalla</Text>
            </TouchableOpacity>
          </View>
        )}

        {screens.map((s) => (
          <View key={s.id} style={ss.card}>
            <View style={ss.cardIcon}>
              <Ionicons name="tv" size={20} color={s.status === 'active' ? '#059669' : '#64748B'} />
            </View>
            <View style={ss.cardBody}>
              <Text style={ss.cardName}>{s.name}</Text>
              <Text style={ss.cardMeta}>
                {[
                  s.code ? `Código: ${s.code}` : '',
                  formatScreenLocation(s.location),
                  s.active_menu_id ? 'Menú publicado' : '',
                ].filter(Boolean).join(' · ')}
              </Text>
              <View style={ss.cardActions}>
                <TouchableOpacity
                  style={ss.orientChip}
                  onPress={() => toggleOrientation(s)}
                  disabled={savingOrient === s.id}
                  activeOpacity={0.7}
                >
                  {savingOrient === s.id
                    ? <ActivityIndicator size="small" color="#0891B2" />
                    : (
                      <>
                        <Ionicons
                          name={orientationOf(s) === 'portrait' ? 'phone-portrait-outline' : 'tv-outline'}
                          size={13}
                          color="#0891B2"
                        />
                        <Text style={ss.orientChipText}>
                          {orientationOf(s) === 'portrait' ? 'Vertical' : 'Horizontal'} · cambiar
                        </Text>
                      </>
                    )}
                </TouchableOpacity>
                <TouchableOpacity
                  style={ss.unlinkChip}
                  onPress={() => openUnlink(s)}
                  activeOpacity={0.7}
                  testID={`unlink-${s.id}`}
                >
                  <Ionicons name="unlink-outline" size={13} color="#DC2626" />
                  <Text style={ss.unlinkChipText}>Desvincular</Text>
                </TouchableOpacity>
              </View>
            </View>
            <StatusBadge status={s.status} />
          </View>
        ))}

        {/* How-to hint */}
        <View style={ss.hint}>
          <Ionicons name="information-circle-outline" size={15} color="#94A3B8" />
          <Text style={ss.hintText}>
            Para conectar una pantalla: enciende el dispositivo, abre la app MediaView Player (o visita la URL del reproductor) e ingresa el código de 6 caracteres que aparece en pantalla.
          </Text>
        </View>
      </ScrollView>

      {/* Conectar Pantalla Modal */}
      <Modal visible={showConnect} transparent animationType="slide" onRequestClose={() => setShowConnect(false)}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={ss.modalOverlay}>
          <View style={[ss.modal, { width: Math.min(width - 32, 420) }]}>
            <View style={ss.modalHeader}>
              <Text style={ss.modalTitle}>Conectar una Pantalla</Text>
              <TouchableOpacity onPress={() => setShowConnect(false)} hitSlop={{ top: 12, right: 12, bottom: 12, left: 12 }}>
                <Ionicons name="close" size={22} color="#64748B" />
              </TouchableOpacity>
            </View>

            {!!connectSuccess ? (
              <View style={ss.successBox}>
                <Ionicons name="checkmark-circle" size={40} color="#059669" />
                <Text style={ss.successText}>{connectSuccess}</Text>
              </View>
            ) : (
              <>
                <View style={ss.codeInputContainer}>
                  <Text style={ss.inputLabel}>Código de Activación</Text>
                  <TextInput
                    style={ss.codeInput}
                    value={code}
                    onChangeText={t => setCode(t.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 6))}
                    placeholder="XY3K9P"
                    placeholderTextColor="#CBD5E1"
                    autoCapitalize="characters"
                    autoCorrect={false}
                    maxLength={6}
                    returnKeyType="next"
                  />
                  <Text style={ss.codeHint}>6 characters shown on your TV screen</Text>
                </View>

                <View style={ss.fieldWrap}>
                  <Text style={ss.inputLabel}>Nombre de la Pantalla</Text>
                  <TextInput
                    style={ss.fieldInput}
                    value={screenName}
                    onChangeText={setScreenName}
                    placeholder="ej. Entrada Principal, Vidriera"
                    placeholderTextColor="#CBD5E1"
                    returnKeyType="done"
                    onSubmitEditing={handleConnect}
                  />
                </View>

                {!!connectError && <Text style={ss.connectErr}>{connectError}</Text>}

                <OrientationPicker value={orientation} onChange={setOrientation} />

                <TouchableOpacity
                  style={[ss.connectBtn, connecting && ss.connectBtnDisabled]}
                  onPress={handleConnect}
                  disabled={connecting}
                >
                  {connecting
                    ? <ActivityIndicator color="#fff" size={16} />
                    : <Text style={ss.connectBtnText}>Conectar Pantalla</Text>
                  }
                </TouchableOpacity>
              </>
            )}
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Desvincular Pantalla — confirmación */}
      <Modal visible={!!unlinkTarget} transparent animationType="fade" onRequestClose={() => setUnlinkTarget(null)}>
        <View style={ss.modalOverlayCenter}>
          <View style={[ss.modalCard, { width: Math.min(width - 32, 420) }]}>
            {unlinkDone ? (
              <View style={ss.successBox}>
                <Ionicons name="checkmark-circle" size={40} color="#059669" />
                <Text style={ss.successText}>{unlinkDone}</Text>
              </View>
            ) : (
              <>
                <View style={ss.modalHeader}>
                  <Text style={ss.modalTitle}>Desvincular pantalla</Text>
                  <TouchableOpacity onPress={() => setUnlinkTarget(null)} hitSlop={{ top: 12, right: 12, bottom: 12, left: 12 }}>
                    <Ionicons name="close" size={22} color="#64748B" />
                  </TouchableOpacity>
                </View>
                <Text style={ss.unlinkBody}>
                  Vas a desvincular <Text style={ss.unlinkStrong}>{unlinkTarget?.name}</Text>. El televisor
                  volverá a mostrar un código nuevo y podrás conectarlo otra vez cuando quieras.
                </Text>
                {!!unlinkError && <Text style={ss.connectErr}>{unlinkError}</Text>}
                <View style={ss.unlinkBtnRow}>
                  <TouchableOpacity style={ss.cancelBtn} onPress={() => setUnlinkTarget(null)} disabled={unlinking}>
                    <Text style={ss.cancelBtnText}>Cancelar</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[ss.dangerBtn, unlinking && ss.connectBtnDisabled]}
                    onPress={confirmUnlink}
                    disabled={unlinking}
                    testID="confirm-unlink"
                  >
                    {unlinking
                      ? <ActivityIndicator color="#fff" size={16} />
                      : <Text style={ss.dangerBtnText}>Sí, desvincular</Text>}
                  </TouchableOpacity>
                </View>
              </>
            )}
          </View>
        </View>
      </Modal>
    </View>
  );
}

const ss = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  content: { padding: 20, gap: 12 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 },
  pageTitle: { fontSize: 22, fontWeight: '800', color: '#0F172A' },
  pageSub: { fontSize: 13, color: '#64748B', marginTop: 2 },
  addBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#0891B2', paddingHorizontal: 14, paddingVertical: 9, borderRadius: 10 },
  addBtnText: { color: '#fff', fontSize: 13, fontWeight: '700' },
  errorText: { color: '#DC2626', fontSize: 13, padding: 16 },
  card: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 14, padding: 14, gap: 12 },
  cardIcon: { width: 40, height: 40, borderRadius: 10, backgroundColor: '#E2E8F0', justifyContent: 'center', alignItems: 'center' },
  cardBody: { flex: 1, gap: 2 },
  cardName: { fontSize: 14, fontWeight: '700', color: '#0F172A' },
  cardMeta: { fontSize: 12, color: '#64748B' },
  orientChip: { flexDirection: 'row', alignItems: 'center', gap: 5, alignSelf: 'flex-start', marginTop: 6, minHeight: 30, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: '#ECFEFF', borderWidth: 1, borderColor: '#CFFAFE' },
  orientChipText: { fontSize: 11, fontWeight: '700', color: '#0891B2' },
  cardActions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 6 },
  unlinkChip: { flexDirection: 'row', alignItems: 'center', gap: 5, alignSelf: 'flex-start', minHeight: 30, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: '#FEF2F2', borderWidth: 1, borderColor: '#FECACA' },
  unlinkChipText: { fontSize: 11, fontWeight: '700', color: '#DC2626' },
  modalOverlayCenter: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: 'rgba(15,23,42,0.45)', padding: 16 },
  modalCard: { backgroundColor: '#FFFFFF', borderRadius: 18, padding: 24 },
  unlinkBody: { fontSize: 14, color: '#334155', lineHeight: 21, marginBottom: 18 },
  unlinkStrong: { fontWeight: '800', color: '#0F172A' },
  unlinkBtnRow: { flexDirection: 'row', gap: 10 },
  cancelBtn: { flex: 1, minHeight: 48, borderRadius: 12, borderWidth: 1, borderColor: '#E2E8F0', alignItems: 'center', justifyContent: 'center' },
  cancelBtnText: { fontSize: 14, fontWeight: '700', color: '#64748B' },
  dangerBtn: { flex: 1, minHeight: 48, borderRadius: 12, backgroundColor: '#DC2626', alignItems: 'center', justifyContent: 'center' },
  dangerBtnText: { color: '#fff', fontSize: 14, fontWeight: '700' },
  orientRow: { flexDirection: 'row', gap: 10 },
  orientOpt: { flex: 1, minHeight: 88, alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 12, borderRadius: 12, borderWidth: 2, borderColor: '#E2E8F0', backgroundColor: '#FFFFFF' },
  orientOptOn: { borderColor: '#0891B2', backgroundColor: '#ECFEFF' },
  shapeLandscape: { width: 40, height: 24, borderRadius: 4, backgroundColor: '#CBD5E1' },
  shapePortrait: { width: 24, height: 40, borderRadius: 4, backgroundColor: '#CBD5E1' },
  shapeOn: { backgroundColor: '#0891B2' },
  orientLabel: { fontSize: 12, fontWeight: '700', color: '#64748B' },
  orientLabelOn: { color: '#0891B2' },
  badge: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: 20 },
  badgeText: { fontSize: 11, fontWeight: '700' },
  empty: { alignItems: 'center', paddingVertical: 60, gap: 10 },
  emptyIcon: { width: 72, height: 72, borderRadius: 20, backgroundColor: '#FFFFFF', justifyContent: 'center', alignItems: 'center', marginBottom: 4 },
  emptyTitle: { fontSize: 17, fontWeight: '700', color: '#64748B' },
  emptyText: { fontSize: 13, color: '#64748B', textAlign: 'center', maxWidth: 280 },
  hint: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 12, padding: 14, marginTop: 8 },
  hintText: { fontSize: 12, color: '#94A3B8', flex: 1, lineHeight: 18 },
  modalOverlay: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(15,23,42,0.45)' },
  modal: { backgroundColor: '#FFFFFF', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, paddingBottom: 36, alignSelf: 'center', width: '100%' },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 },
  modalTitle: { fontSize: 18, fontWeight: '800', color: '#0F172A' },
  codeInputContainer: { marginBottom: 16 },
  inputLabel: { fontSize: 11, fontWeight: '700', color: '#64748B', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 },
  codeInput: { fontSize: 32, fontWeight: '800', color: '#0F172A', textAlign: 'center', letterSpacing: 12, backgroundColor: '#F8FAFC', borderWidth: 2, borderColor: '#0891B2', borderRadius: 14, paddingVertical: 16, paddingHorizontal: 20 },
  codeHint: { fontSize: 11, color: '#94A3B8', textAlign: 'center', marginTop: 6 },
  fieldWrap: { marginBottom: 16 },
  fieldInput: { fontSize: 15, color: '#0F172A', backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 10, padding: 14 },
  connectErr: { color: '#DC2626', fontSize: 13, marginBottom: 12, textAlign: 'center' },
  connectBtn: { backgroundColor: '#0891B2', borderRadius: 12, padding: 16, alignItems: 'center' },
  connectBtnDisabled: { opacity: 0.6 },
  connectBtnText: { color: '#fff', fontSize: 15, fontWeight: '700' },
  successBox: { alignItems: 'center', paddingVertical: 24, gap: 12 },
  successText: { fontSize: 15, fontWeight: '600', color: '#059669', textAlign: 'center' },
});
