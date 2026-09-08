import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, ActivityIndicator, TouchableOpacity,
  TextInput, Modal, useWindowDimensions, Platform, KeyboardAvoidingView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { teamAPI, type TeamRole } from '../../src/services/api';
import EmptyState from '../../src/components/EmptyState';
import AppDialog, { type DialogState } from '../../src/components/AppDialog';

type Member = {
  id: string; name: string; email: string; team_role: TeamRole;
  active: boolean; must_change_password: boolean; is_me: boolean; created_at?: string;
};

const ROLES: { key: TeamRole; label: string; desc: string; icon: keyof typeof Ionicons.glyphMap }[] = [
  { key: 'admin', label: 'Administrador', desc: 'Todo: pantallas, contenido, facturación y equipo', icon: 'shield-checkmark-outline' },
  { key: 'manager', label: 'Gerente', desc: 'Pantallas, menús, precios, fotos y horarios', icon: 'briefcase-outline' },
  { key: 'employee', label: 'Empleado', desc: 'Cambiar precios y fotos, y publicar contenido', icon: 'person-outline' },
];

const ROLE_LABEL: Record<TeamRole, string> = {
  admin: 'Administrador', manager: 'Gerente', employee: 'Empleado',
};

export default function WorkspaceTeam() {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const [members, setMembers] = useState<Member[]>([]);
  const [canManage, setCanManage] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [dialog, setDialog] = useState<DialogState>(null);

  // Invite form
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<TeamRole>('employee');
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [created, setCreated] = useState<{ email: string; password: string } | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true); setError('');
      const res = await teamAPI.list();
      setMembers(res.data.members || []);
      setCanManage(!!res.data.can_manage);
    } catch (e: any) { setError(e.response?.data?.detail || e.message || 'No se pudo cargar'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openForm = () => {
    setName(''); setEmail(''); setPassword(''); setRole('employee');
    setFormError(''); setCreated(null); setShowForm(true);
  };

  const suggestPassword = () =>
    setPassword(`MV${Math.floor(1000 + Math.random() * 9000)}${'abcdefghjkmnpqrstuvwxyz'[Math.floor(Math.random() * 23)]}!`);

  const submit = useCallback(async () => {
    setFormError('');
    if (!name.trim()) { setFormError('Escribe el nombre de la persona.'); return; }
    if (!email.includes('@')) { setFormError('Escribe un correo válido.'); return; }
    if (password.length < 8) { setFormError('La contraseña temporal debe tener al menos 8 caracteres.'); return; }
    setSaving(true);
    try {
      await teamAPI.create({
        name: name.trim(), email: email.trim().toLowerCase(),
        temporary_password: password, role,
      });
      setCreated({ email: email.trim().toLowerCase(), password });
      await load();
    } catch (e: any) {
      setFormError(e.response?.data?.detail || 'No se pudo crear la cuenta.');
    } finally { setSaving(false); }
  }, [name, email, password, role, load]);

  const changeRole = (m: Member) => {
    setDialog({
      title: `Cambiar rol de ${m.name}`,
      message: 'Elige el nuevo rol. La persona tendrá que iniciar sesión de nuevo.',
      icon: 'swap-horizontal-outline',
      options: [
        ...ROLES.filter(r => r.key !== m.team_role).map(o => ({
          label: o.label,
          primary: true,
          onPress: async () => {
            try { await teamAPI.update(m.id, { role: o.key }); await load(); }
            catch (e: any) { setDialog({ title: 'No se pudo cambiar el rol', message: e.response?.data?.detail }); }
          },
        })),
        { label: 'Cancelar' },
      ],
    });
  };

  const toggleActive = (m: Member) => {
    const turningOff = m.active;
    setDialog({
      title: turningOff ? `¿Desactivar a ${m.name}?` : `¿Reactivar a ${m.name}?`,
      message: turningOff
        ? 'No podrá iniciar sesión hasta que lo reactives. Su historial se conserva.'
        : 'Podrá volver a entrar con su contraseña.',
      icon: turningOff ? 'person-remove-outline' : 'person-add-outline',
      options: [
        {
          label: turningOff ? 'Desactivar' : 'Reactivar',
          primary: !turningOff,
          destructive: turningOff,
          onPress: async () => {
            try {
              if (turningOff) await teamAPI.deactivate(m.id);
              else await teamAPI.update(m.id, { active: true });
              await load();
            } catch (e: any) { setDialog({ title: 'No se pudo actualizar', message: e.response?.data?.detail }); }
          },
        },
        { label: 'Cancelar' },
      ],
    });
  };

  const resetPassword = (m: Member) => {
    const temp = `MV${Math.floor(1000 + Math.random() * 9000)}x!`;
    setDialog({
      title: `Nueva contraseña para ${m.name}`,
      message: `Se usará: ${temp}\n\nDásela a la persona; deberá cambiarla al entrar.`,
      icon: 'key-outline',
      options: [
        {
          label: 'Aplicar',
          primary: true,
          onPress: async () => {
            try {
              await teamAPI.resetPassword(m.id, temp);
              await load();
              setDialog({ title: 'Contraseña temporal lista', message: `${m.email}\n${temp}`, icon: 'checkmark-circle-outline' });
            } catch (e: any) { setDialog({ title: 'No se pudo restablecer', message: e.response?.data?.detail }); }
          },
        },
        { label: 'Cancelar' },
      ],
    });
  };

  return (
    <View style={su.root}>
      <ScrollView contentContainerStyle={[su.content, { paddingBottom: insets.bottom + 24 }]}>
        <View style={su.header}>
          <View style={{ flex: 1 }}>
            <Text style={su.title}>Equipo</Text>
            <Text style={su.sub}>{members.length} persona{members.length !== 1 ? 's' : ''} con acceso a tu panel</Text>
          </View>
          {canManage && members.length > 0 && (
            <TouchableOpacity style={su.addBtn} onPress={openForm} activeOpacity={0.85}>
              <Ionicons name="person-add-outline" size={16} color="#fff" />
              <Text style={su.addBtnText}>Agregar</Text>
            </TouchableOpacity>
          )}
        </View>

        {loading && <ActivityIndicator color="#0891B2" style={{ marginTop: 40 }} />}
        {error !== '' && !loading && <Text style={su.error}>{error}</Text>}

        {!loading && !error && members.length === 0 && (
          <EmptyState
            icon="people-outline"
            title="Todavía no hay equipo"
            text="Agrega a tus gerentes y empleados para que puedan cambiar precios, fotos y horarios sin darles tu contraseña."
            primary={canManage ? { label: 'Agregar Persona', icon: 'person-add-outline', onPress: openForm } : undefined}
          />
        )}

        {members.map(m => (
          <View key={m.id} style={[su.card, !m.active && su.cardOff]}>
            <View style={su.avatar}>
              <Text style={su.avatarText}>{(m.name || m.email || 'U')[0].toUpperCase()}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={su.name}>
                {m.name || '—'}{m.is_me ? ' (tú)' : ''}
              </Text>
              <Text style={su.email}>{m.email}</Text>
              <View style={su.tagRow}>
                <View style={su.roleBadge}><Text style={su.roleText}>{ROLE_LABEL[m.team_role]}</Text></View>
                {!m.active && <View style={su.offBadge}><Text style={su.offText}>Desactivado</Text></View>}
                {m.must_change_password && m.active && (
                  <View style={su.pendBadge}><Text style={su.pendText}>Contraseña temporal</Text></View>
                )}
              </View>
            </View>
            {canManage && !m.is_me && (
              <View style={su.actions}>
                <TouchableOpacity onPress={() => changeRole(m)} style={su.iconBtn} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                  <Ionicons name="swap-horizontal-outline" size={18} color="#0891B2" />
                </TouchableOpacity>
                <TouchableOpacity onPress={() => resetPassword(m)} style={su.iconBtn} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                  <Ionicons name="key-outline" size={18} color="#0891B2" />
                </TouchableOpacity>
                <TouchableOpacity onPress={() => toggleActive(m)} style={su.iconBtn} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                  <Ionicons name={m.active ? 'person-remove-outline' : 'person-add-outline'} size={18} color={m.active ? '#DC2626' : '#059669'} />
                </TouchableOpacity>
              </View>
            )}
          </View>
        ))}

        {canManage && members.length > 0 && (
          <View style={su.legend}>
            <Text style={su.legendTitle}>¿Qué puede hacer cada rol?</Text>
            {ROLES.map(r => (
              <View key={r.key} style={su.legendRow}>
                <Ionicons name={r.icon} size={16} color="#0891B2" />
                <Text style={su.legendText}><Text style={su.legendStrong}>{r.label}: </Text>{r.desc}</Text>
              </View>
            ))}
          </View>
        )}
      </ScrollView>

      {/* Add member */}
      <Modal visible={showForm} transparent animationType="slide" onRequestClose={() => setShowForm(false)}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={[su.overlay, width > 900 && su.overlayCentered]}>
          <View style={[su.modal, width > 900 && su.modalCentered, { width: Math.min(width - 24, 520) }]}>
            <View style={su.modalHeader}>
              <Text style={su.modalTitle}>{created ? 'Cuenta creada' : 'Agregar a tu equipo'}</Text>
              <TouchableOpacity onPress={() => setShowForm(false)} hitSlop={{ top: 12, right: 12, bottom: 12, left: 12 }}>
                <Ionicons name="close" size={22} color="#64748B" />
              </TouchableOpacity>
            </View>

            {created ? (
              <View>
                <View style={su.successBox}>
                  <Ionicons name="checkmark-circle" size={36} color="#059669" />
                  <Text style={su.successText}>Comparte estos datos con la persona. Al entrar deberá crear su propia contraseña.</Text>
                </View>
                <View style={su.credBox}>
                  <Text style={su.credLabel}>CORREO</Text>
                  <Text style={su.credValue}>{created.email}</Text>
                  <Text style={[su.credLabel, { marginTop: 12 }]}>CONTRASEÑA TEMPORAL</Text>
                  <Text style={su.credValue}>{created.password}</Text>
                </View>
                <TouchableOpacity style={su.primaryBtn} onPress={() => setShowForm(false)} activeOpacity={0.85}>
                  <Text style={su.primaryBtnText}>Listo</Text>
                </TouchableOpacity>
                <TouchableOpacity style={su.ghostBtn} onPress={openForm} activeOpacity={0.8}>
                  <Text style={su.ghostBtnText}>Agregar otra persona</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <>
              <ScrollView style={{ maxHeight: 400 }} keyboardShouldPersistTaps="handled">
                <Text style={su.inputLabel}>Nombre</Text>
                <TextInput style={su.input} value={name} onChangeText={setName}
                  placeholder="ej. María López" placeholderTextColor="#CBD5E1" autoCapitalize="words" />

                <Text style={[su.inputLabel, { marginTop: 14 }]}>Correo electrónico</Text>
                <TextInput style={su.input} value={email} onChangeText={setEmail}
                  placeholder="maria@minegocio.com" placeholderTextColor="#CBD5E1"
                  keyboardType="email-address" autoCapitalize="none" autoCorrect={false} />

                <Text style={[su.inputLabel, { marginTop: 14 }]}>Contraseña temporal</Text>
                <View style={su.pwdRow}>
                  <TextInput style={[su.input, { flex: 1 }]} value={password} onChangeText={setPassword}
                    placeholder="Mínimo 8 caracteres" placeholderTextColor="#CBD5E1" autoCapitalize="none" />
                  <TouchableOpacity style={su.genBtn} onPress={suggestPassword} activeOpacity={0.8}>
                    <Ionicons name="refresh" size={16} color="#0891B2" />
                    <Text style={su.genText}>Generar</Text>
                  </TouchableOpacity>
                </View>
                <Text style={su.hint}>La persona deberá cambiarla la primera vez que entre.</Text>

                <Text style={[su.inputLabel, { marginTop: 16 }]}>Rol</Text>
                {ROLES.map(r => {
                  const on = role === r.key;
                  return (
                    <TouchableOpacity key={r.key} style={[su.roleRow, on && su.roleRowOn]} onPress={() => setRole(r.key)} activeOpacity={0.8}>
                      <Ionicons name={r.icon} size={18} color={on ? '#0891B2' : '#94A3B8'} />
                      <View style={{ flex: 1 }}>
                        <Text style={su.roleName}>{r.label}</Text>
                        <Text style={su.roleDesc}>{r.desc}</Text>
                      </View>
                      <Ionicons name={on ? 'checkmark-circle' : 'ellipse-outline'} size={20} color={on ? '#0891B2' : '#CBD5E1'} />
                    </TouchableOpacity>
                  );
                })}

              </ScrollView>

              {!!formError && <Text style={su.formErr}>{formError}</Text>}
              <TouchableOpacity style={[su.primaryBtn, saving && { opacity: 0.6 }]} onPress={submit} disabled={saving} activeOpacity={0.85}>
                {saving ? <ActivityIndicator color="#fff" size="small" /> : <Text style={su.primaryBtnText}>Crear Cuenta</Text>}
              </TouchableOpacity>
              </>
            )}
          </View>
        </KeyboardAvoidingView>
      </Modal>

      <AppDialog state={dialog} onDismiss={() => setDialog(null)} />
    </View>
  );
}

const su = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  content: { padding: 20, gap: 12 },
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, marginBottom: 4 },
  title: { fontSize: 22, fontWeight: '800', color: '#0F172A', marginBottom: 4 },
  sub: { fontSize: 13, color: '#64748B' },
  addBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#0891B2', paddingHorizontal: 14, paddingVertical: 11, borderRadius: 10, minHeight: 44 },
  addBtnText: { color: '#fff', fontSize: 13, fontWeight: '700' },
  error: { color: '#DC2626', fontSize: 13, padding: 16 },
  card: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 14, padding: 14 },
  cardOff: { opacity: 0.65 },
  avatar: { width: 42, height: 42, borderRadius: 12, backgroundColor: '#CFFAFE', justifyContent: 'center', alignItems: 'center' },
  avatarText: { fontSize: 16, fontWeight: '800', color: '#0891B2' },
  name: { fontSize: 14, fontWeight: '700', color: '#0F172A' },
  email: { fontSize: 11.5, color: '#64748B', marginTop: 2 },
  tagRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 6 },
  roleBadge: { backgroundColor: '#ECFEFF', paddingHorizontal: 9, paddingVertical: 3, borderRadius: 12 },
  roleText: { fontSize: 10.5, color: '#0E7490', fontWeight: '700' },
  offBadge: { backgroundColor: '#FEF2F2', paddingHorizontal: 9, paddingVertical: 3, borderRadius: 12 },
  offText: { fontSize: 10.5, color: '#DC2626', fontWeight: '700' },
  pendBadge: { backgroundColor: '#FEF9C3', paddingHorizontal: 9, paddingVertical: 3, borderRadius: 12 },
  pendText: { fontSize: 10.5, color: '#A16207', fontWeight: '700' },
  actions: { flexDirection: 'row', gap: 4 },
  iconBtn: { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: '#F8FAFC' },
  legend: { backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 14, padding: 16, gap: 10, marginTop: 6 },
  legendTitle: { fontSize: 13.5, fontWeight: '800', color: '#0F172A' },
  legendRow: { flexDirection: 'row', gap: 10, alignItems: 'flex-start' },
  legendText: { fontSize: 12.5, color: '#64748B', flex: 1, lineHeight: 18 },
  legendStrong: { color: '#0F172A', fontWeight: '700' },

  overlay: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(15,23,42,0.45)' },
  overlayCentered: { justifyContent: 'center', alignItems: 'center' },
  modal: { backgroundColor: '#FFFFFF', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 22, paddingBottom: 30, alignSelf: 'center', maxHeight: '92%' },
  modalCentered: { borderRadius: 20, paddingBottom: 22 },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  modalTitle: { fontSize: 18, fontWeight: '800', color: '#0F172A' },
  inputLabel: { fontSize: 11, fontWeight: '700', color: '#64748B', letterSpacing: 0.6, textTransform: 'uppercase', marginBottom: 8 },
  input: {
    fontSize: 15, color: '#0F172A', backgroundColor: '#F8FAFC', borderWidth: 1,
    borderColor: '#E2E8F0', borderRadius: 10, padding: 14,
    ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : null),
  },
  pwdRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  genBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: '#ECFEFF', borderWidth: 1, borderColor: '#CFFAFE', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 13, minHeight: 44 },
  genText: { fontSize: 12.5, color: '#0E7490', fontWeight: '700' },
  hint: { fontSize: 11.5, color: '#94A3B8', marginTop: 6 },
  roleRow: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 12, padding: 12, marginBottom: 8, minHeight: 60 },
  roleRowOn: { borderColor: '#06B6D4', backgroundColor: '#ECFEFF' },
  roleName: { fontSize: 13.5, fontWeight: '700', color: '#0F172A' },
  roleDesc: { fontSize: 11.5, color: '#64748B', marginTop: 2 },
  formErr: { color: '#DC2626', fontSize: 13, marginTop: 12, textAlign: 'center' },
  primaryBtn: { backgroundColor: '#0891B2', borderRadius: 12, padding: 16, alignItems: 'center', marginTop: 16 },
  primaryBtnText: { color: '#fff', fontSize: 15, fontWeight: '700' },
  ghostBtn: { alignItems: 'center', paddingVertical: 12, minHeight: 44, justifyContent: 'center' },
  ghostBtnText: { color: '#0891B2', fontSize: 13.5, fontWeight: '700' },
  successBox: { alignItems: 'center', gap: 10, paddingVertical: 8 },
  successText: { fontSize: 13, color: '#475569', textAlign: 'center', lineHeight: 19 },
  credBox: { backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 12, padding: 16, marginTop: 14 },
  credLabel: { fontSize: 10.5, fontWeight: '800', color: '#94A3B8', letterSpacing: 1 },
  credValue: { fontSize: 15, fontWeight: '700', color: '#0F172A', marginTop: 4 },
});
