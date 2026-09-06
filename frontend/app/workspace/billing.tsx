import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, ActivityIndicator,
  TouchableOpacity, Modal, Alert
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { workspaceAPI } from '../../src/services/api';

function Row({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <View style={sb.row}>
      <Text style={sb.rowLabel}>{label}</Text>
      <Text style={[sb.rowValue, accent && { color: '#059669', fontWeight: '700' }]}>{value}</Text>
    </View>
  );
}

function PlanBadge({ planId }: { planId?: string }) {
  const colors: Record<string, string> = { free: '#64748B', starter: '#0891B2', pro: '#06B6D4', enterprise: '#D97706' };
  const c = colors[planId?.toLowerCase() || ''] || '#64748B';
  return (
    <View style={[sb.badge, { backgroundColor: c + '22', borderColor: c + '44' }]}>
      <Text style={[sb.badgeText, { color: c }]}>{(planId || 'plan').toUpperCase()}</Text>
    </View>
  );
}

export default function WorkspaceBilling() {
  const insets = useSafeAreaInsets();
  const [billing, setBilling] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Add screens modal
  const [showAddScreens, setShowAddScreens] = useState(false);
  const [addCount, setAddCount] = useState(1);
  const [preview, setPreview] = useState<any>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const load = useCallback(async () => {
    try { setLoading(true); setError(''); const res = await workspaceAPI.billing(); setBilling(res.data); }
    catch (e: any) { setError(e.response?.data?.detail || e.message || 'Failed to load'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const fetchPreview = useCallback(async (count: number) => {
    setPreviewLoading(true); setPreview(null);
    try { const res = await workspaceAPI.screenCostPreview(count); setPreview(res.data); }
    catch (e: any) { setPreview({ error: e.response?.data?.detail || e.message }); }
    finally { setPreviewLoading(false); }
  }, []);

  const openAddScreens = () => {
    setAddCount(1); setPreview(null);
    setShowAddScreens(true);
    fetchPreview(1);
  };

  const changeCount = (delta: number) => {
    const next = Math.max(1, addCount + delta);
    setAddCount(next);
    fetchPreview(next);
  };

  const confirmAddScreens = async () => {
    setConfirming(true);
    try {
      await workspaceAPI.addScreens(addCount);
      Alert.alert('Done!', `${addCount} screen(s) added. New monthly: $${preview?.new_monthly?.toFixed(2)}`);
      setShowAddScreens(false);
      load();
    } catch (e: any) { Alert.alert('Error', e.response?.data?.detail || e.message); }
    finally { setConfirming(false); }
  };

  const fmtDate = (d?: string) => d ? new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—';
  const fmtMoney = (n?: number) => n != null ? `$${Number(n).toFixed(2)}` : '—';
  const sub = billing?.subscription;
  const pa = billing?.current_pricing_agreement;
  const plan = billing?.plan_config;

  return (
    <View style={sb.root}>
      <ScrollView contentContainerStyle={[sb.content, { paddingBottom: insets.bottom + 24 }]}>
        <Text style={sb.title}>Facturación y Plan</Text>

        {loading && <ActivityIndicator color="#0891B2" style={{ marginTop: 40 }} />}
        {!!error && !loading && <Text style={sb.error}>{error}</Text>}

        {!loading && !sub && !error && (
          <View style={sb.empty}>
            <Ionicons name="card-outline" size={40} color="#CBD5E1" />
            <Text style={sb.emptyTitle}>No se encontró suscripción</Text>
            <Text style={sb.emptyText}>Contacta a soporte si crees que esto es un error.</Text>
          </View>
        )}

        {!loading && sub && (
          <>
            {/* Current plan card */}
            <View style={sb.card}>
              <View style={sb.cardHeader}>
                <View>
                  <Text style={sb.cardTitle}>Plan Actual</Text>
                  {plan && <Text style={sb.planName}>{plan.display_name}</Text>}
                </View>
                <PlanBadge planId={pa?.plan_id || plan?.plan_id} />
              </View>
              <Row label="Precio Mensual" value={fmtMoney(pa?.agreed_monthly_price || plan?.monthly_price)} accent />
              <Row label="Pantallas Incluidas" value={String(pa?.screens_included || plan?.screens_included || '—')} />
              {pa?.overage_price_per_screen != null && (
                <Row label="Pantalla Extra" value={`${fmtMoney(pa.overage_price_per_screen)}/pantalla`} />
              )}
              {pa?.billing_cycle && <Row label="Ciclo de Facturación" value={pa.billing_cycle === 'monthly' ? 'Mensual' : pa.billing_cycle === 'annual' ? 'Anual' : pa.billing_cycle} />}
              {pa?.pricing_model && <Row label="Modelo de Precio" value={pa.pricing_model.toUpperCase()} />}
            </View>

            {/* Suscripción status */}
            <View style={sb.card}>
              <Text style={sb.cardTitle}>Suscripción</Text>
              <Row label="Estado" value={sub.status === 'trial' ? 'En prueba' : sub.status === 'active' ? 'Activa' : (sub.status || '—')} />
              <Row label="Proveedor" value={sub.billing_provider === 'manual' ? 'Manual' : (sub.billing_provider || '—')} />
              {sub.trial_ends_at && <Row label="Fin de Prueba" value={fmtDate(sub.trial_ends_at)} />}
              <Row label="Inicio de Periodo" value={fmtDate(sub.current_period_start)} />
              <Row label="Fin de Periodo" value={fmtDate(sub.current_period_end)} />
            </View>

            {/* Add screens CTA */}
            <TouchableOpacity style={sb.addScreensCTA} onPress={openAddScreens}>
              <View style={sb.addScreensLeft}>
                <View style={sb.addScreensIcon}>
                  <Ionicons name="add-circle" size={22} color="#0891B2" />
                </View>
                <View>
                  <Text style={sb.addScreensTitle}>Agregar Más Pantallas</Text>
                  <Text style={sb.addScreensSub}>
                    {pa?.overage_price_per_screen
                      ? `$${pa.overage_price_per_screen}/pantalla extra al mes`
                      : 'View pricing for additional screens'}
                  </Text>
                </View>
              </View>
              <Ionicons name="chevron-forward" size={18} color="#94A3B8" />
            </TouchableOpacity>

            {/* Pricing history */}
            {billing?.pricing_history?.length > 1 && (
              <View style={sb.card}>
                <Text style={sb.cardTitle}>Historial de Precios</Text>
                {billing.pricing_history.map((h: any) => (
                  <View key={h.id} style={sb.historyRow}>
                    <View>
                      <Text style={sb.historyVer}>v{h.version} — {fmtMoney(h.agreed_monthly_price)}/mo</Text>
                      <Text style={sb.historyNote}>{h.notes || `${h.screens_included} screens`}</Text>
                    </View>
                    <Text style={sb.historyDate}>{fmtDate(h.effective_from || h.created_at)}</Text>
                  </View>
                ))}
              </View>
            )}
          </>
        )}
      </ScrollView>

      {/* Agregar Pantallas Modal */}
      <Modal visible={showAddScreens} transparent animationType="slide" onRequestClose={() => setShowAddScreens(false)}>
        <View style={sb.modalOverlay}>
          <View style={sb.modal}>
            <View style={sb.modalHeader}>
              <Text style={sb.modalTitle}>Agregar Pantallas</Text>
              <TouchableOpacity onPress={() => setShowAddScreens(false)}>
                <Ionicons name="close" size={22} color="#64748B" />
              </TouchableOpacity>
            </View>

            {/* Count stepper */}
            <Text style={sb.stepperLabel}>¿Cuántas pantallas quieres agregar?</Text>
            <View style={sb.stepper}>
              <TouchableOpacity style={sb.stepBtn} onPress={() => changeCount(-1)} disabled={addCount <= 1}>
                <Ionicons name="remove" size={20} color={addCount <= 1 ? '#CBD5E1' : '#0F172A'} />
              </TouchableOpacity>
              <Text style={sb.stepCount}>{addCount}</Text>
              <TouchableOpacity style={sb.stepBtn} onPress={() => changeCount(1)}>
                <Ionicons name="add" size={20} color="#0F172A" />
              </TouchableOpacity>
            </View>

            {/* Cost preview */}
            {previewLoading && <ActivityIndicator color="#0891B2" style={{ marginVertical: 16 }} />}

            {preview && !preview.error && !previewLoading && (
              <View style={sb.previewBox}>
                <View style={sb.previewRow}>
                  <Text style={sb.previewLabel}>Mensual actual</Text>
                  <Text style={sb.previewVal}>{fmtMoney(preview.current_monthly)}</Text>
                </View>
                <View style={sb.previewRow}>
                  <Text style={sb.previewLabel}>Adding {addCount} screen{addCount !== 1 ? 's' : ''}</Text>
                  <Text style={[sb.previewVal, { color: '#D97706' }]}>+{fmtMoney(preview.added_cost)}</Text>
                </View>
                <View style={[sb.previewRow, sb.previewTotal]}>
                  <Text style={[sb.previewLabel, { color: '#0F172A', fontWeight: '700' }]}>Nuevo total mensual</Text>
                  <Text style={[sb.previewVal, { color: '#059669', fontSize: 20, fontWeight: '800' }]}>{fmtMoney(preview.new_monthly)}</Text>
                </View>
                <Text style={sb.previewMeta}>
                  {preview.current_screens} → {preview.new_total_screens} screens
                  {preview.extra_price_per_screen > 0 ? ` · $${preview.extra_price_per_screen}/screen/mo` : ''}
                </Text>
              </View>
            )}

            {preview?.error && <Text style={sb.error}>{preview.error}</Text>}

            <TouchableOpacity
              style={[sb.confirmBtn, (confirming || !preview || preview?.error) && { opacity: 0.5 }]}
              onPress={confirmAddScreens}
              disabled={confirming || !preview || !!preview?.error}
            >
              {confirming
                ? <ActivityIndicator color="#fff" size={16} />
                : <Text style={sb.confirmBtnText}>Confirm — Add {addCount} Screen{addCount !== 1 ? 's' : ''}</Text>
              }
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const sb = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  content: { padding: 20, gap: 16 },
  title: { fontSize: 22, fontWeight: '800', color: '#0F172A', marginBottom: 4 },
  error: { color: '#DC2626', fontSize: 13 },
  empty: { alignItems: 'center', paddingVertical: 60, gap: 10 },
  emptyTitle: { fontSize: 16, fontWeight: '700', color: '#64748B' },
  emptyText: { fontSize: 13, color: '#64748B', textAlign: 'center', maxWidth: 260 },
  card: { backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 16, padding: 18 },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 },
  cardTitle: { fontSize: 12, fontWeight: '700', color: '#64748B', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 },
  planName: { fontSize: 18, fontWeight: '800', color: '#0F172A' },
  badge: { borderWidth: 1, borderRadius: 20, paddingHorizontal: 10, paddingVertical: 3 },
  badgeText: { fontSize: 11, fontWeight: '700' },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#E2E8F0' },
  rowLabel: { fontSize: 13, color: '#64748B' },
  rowValue: { fontSize: 13, color: '#334155', fontWeight: '500' },
  addScreensCTA: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#CFFAFE', borderRadius: 16, padding: 18, gap: 12 },
  addScreensLeft: { flexDirection: 'row', alignItems: 'center', gap: 14, flex: 1 },
  addScreensIcon: { width: 44, height: 44, borderRadius: 12, backgroundColor: '#CFFAFE22', justifyContent: 'center', alignItems: 'center' },
  addScreensTitle: { fontSize: 15, fontWeight: '700', color: '#0F172A' },
  addScreensSub: { fontSize: 12, color: '#64748B', marginTop: 2 },
  historyRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#E2E8F0' },
  historyVer: { fontSize: 13, fontWeight: '600', color: '#334155' },
  historyNote: { fontSize: 11, color: '#64748B', marginTop: 2 },
  historyDate: { fontSize: 11, color: '#94A3B8' },
  modalOverlay: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(15,23,42,0.45)' },
  modal: { backgroundColor: '#FFFFFF', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, paddingBottom: 36 },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 },
  modalTitle: { fontSize: 18, fontWeight: '800', color: '#0F172A' },
  stepperLabel: { fontSize: 13, fontWeight: '600', color: '#64748B', marginBottom: 12 },
  stepper: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 24, marginBottom: 20 },
  stepBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: '#E2E8F0', justifyContent: 'center', alignItems: 'center' },
  stepCount: { fontSize: 32, fontWeight: '800', color: '#0F172A', minWidth: 48, textAlign: 'center' },
  previewBox: { backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 14, padding: 16, marginBottom: 20, gap: 4 },
  previewRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 6 },
  previewLabel: { fontSize: 13, color: '#64748B' },
  previewVal: { fontSize: 14, fontWeight: '600', color: '#334155' },
  previewTotal: { borderTopWidth: 1, borderTopColor: '#E2E8F0', marginTop: 6, paddingTop: 12 },
  previewMeta: { fontSize: 11, color: '#94A3B8', textAlign: 'center', marginTop: 6 },
  confirmBtn: { backgroundColor: '#059669', borderRadius: 12, padding: 16, alignItems: 'center' },
  confirmBtnText: { color: '#fff', fontSize: 15, fontWeight: '700' },
});
