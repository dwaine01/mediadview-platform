import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { workspaceAPI } from '../../src/services/api';
import AppDialog, { type DialogState } from '../../src/components/AppDialog';

type Menu = {
  id: string; name: string; description?: string;
  items: any[]; status: string; source?: string;
  screen_ids?: string[]; updated_at?: string;
};

const TEMPLATES = [
  { id: 'restaurant', name: 'Restaurant', icon: 'restaurant', items: [
    { name: 'Grilled Chicken', price: 14.99, category: 'Main', description: 'With seasonal vegetables' },
    { name: 'Caesar Salad', price: 8.99, category: 'Salads' },
    { name: 'Sparkling Water', price: 2.50, category: 'Drinks' },
  ]},
  { id: 'cafe', name: 'Café', icon: 'cafe', items: [
    { name: 'Espresso', price: 2.50, category: 'Coffee' },
    { name: 'Cappuccino', price: 3.80, category: 'Coffee' },
    { name: 'Croissant', price: 2.90, category: 'Pastries' },
    { name: 'Avocado Toast', price: 7.50, category: 'Breakfast' },
  ]},
  { id: 'pizza', name: 'Pizza', icon: 'pizza', items: [
    { name: 'Margherita', price: 12.00, category: 'Pizza' },
    { name: 'Pepperoni', price: 14.00, category: 'Pizza' },
    { name: 'Garlic Bread', price: 4.50, category: 'Sides' },
    { name: 'Soda', price: 2.00, category: 'Drinks' },
  ]},
  { id: 'bar', name: 'Bar', icon: 'wine', items: [
    { name: 'Classic Mojito', price: 9.00, category: 'Cocktails' },
    { name: 'Craft Beer', price: 6.50, category: 'Beer' },
    { name: 'House Wine', price: 7.00, category: 'Wine' },
  ]},
];

type Design = {
  id: string; name: string; template_id: string; status: string;
  screen_ids?: string[]; updated_at?: string;
};

export default function WorkspaceMenus() {
  const insets = useSafeAreaInsets();
  const [menus, setMenus] = useState<Menu[]>([]);
  // Las carteleras armadas con plantilla profesional viven en esta misma
  // lista: el dueño edita precios y fotos donde ya está acostumbrado, sin
  // volver al catálogo de plantillas.
  const [designs, setDesigns] = useState<Design[]>([]);
  const [screenNames, setScreenNames] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [dialog, setDialog] = useState<DialogState>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try { setLoading(true); setError(''); const res = await workspaceAPI.menus(); setMenus(res.data || []); }
    catch (e: any) { setError(e.response?.data?.detail || e.message || 'No se pudo cargar'); }
    finally { setLoading(false); }
    try {
      const [mine, screens] = await Promise.all([workspaceAPI.designs(), workspaceAPI.screens()]);
      setDesigns(mine.data || []);
      setScreenNames(Object.fromEntries((screens.data || []).map((s: any) => [s.id, s.name])));
    } catch { /* las carteleras son un extra: los menús ya se ven */ }
  }, []);

  const whereLive = (design: Design): string => {
    const names = (design.screen_ids || []).map(id => screenNames[id]).filter(Boolean);
    if (design.status !== 'published' || names.length === 0) return 'Sin publicar';
    return names.length <= 2
      ? `En vivo en ${names.join(' y ')}`
      : `En vivo en ${names.length} pantallas`;
  };

  const deleteDesign = (design: Design) => {
    setDialog({
      title: `¿Eliminar «${design.name}»?`,
      message: design.status === 'published'
        ? 'Está en vivo: las pantallas dejan de mostrarla.'
        : 'Esta acción no se puede deshacer.',
      icon: 'trash-outline',
      options: [
        { label: 'Eliminar', destructive: true, onPress: async () => {
          try { await workspaceAPI.deleteDesign(design.id); load(); }
          catch (e: any) { setDialog({ title: 'No se pudo eliminar', message: e.response?.data?.detail || e.message }); }
        }},
        { label: 'Cancelar' },
      ],
    });
  };

  useEffect(() => { load(); }, [load]);

  const createBlank = async () => {
    setCreating(true);
    try {
      const res = await workspaceAPI.createMenu({ name: 'New Menu', source: 'blank', items: [] });
      router.push({ pathname: '/workspace/menu-edit', params: { id: res.data.id } });
    } catch (e: any) { setDialog({ title: 'No se pudo crear', message: e.response?.data?.detail || e.message }); }
    finally { setCreating(false); setShowCreate(false); }
  };

  const createFromTemplate = async (template: typeof TEMPLATES[0]) => {
    setCreating(true);
    try {
      const res = await workspaceAPI.createMenu({
        name: `${template.name} Menu`,
        source: 'template',
        items: template.items.map(it => ({ ...it, available: true })),
      });
      router.push({ pathname: '/workspace/menu-edit', params: { id: res.data.id } });
    } catch (e: any) { setDialog({ title: 'No se pudo crear', message: e.response?.data?.detail || e.message }); }
    finally { setCreating(false); setShowCreate(false); }
  };

  const deleteMenu = (menu: Menu) => {
    setDialog({
      title: `¿Eliminar "${menu.name}"?`,
      message: 'Esta acción no se puede deshacer.',
      icon: 'trash-outline',
      options: [
        { label: 'Eliminar', destructive: true, onPress: async () => {
          try { await workspaceAPI.deleteMenu(menu.id); load(); }
          catch (e: any) { setDialog({ title: 'No se pudo eliminar', message: e.response?.data?.detail || e.message }); }
        }},
        { label: 'Cancelar' },
      ],
    });
  };

  if (showCreate) {
    return (
      <View style={ms.root}>
        <ScrollView contentContainerStyle={[ms.content, { paddingBottom: insets.bottom + 24 }]}>
          <View style={ms.createHeader}>
            <TouchableOpacity onPress={() => setShowCreate(false)} style={ms.backBtn}>
              <Ionicons name="arrow-back" size={20} color="#64748B" />
            </TouchableOpacity>
            <View>
              <Text style={ms.pageTitle}>Crear Menú</Text>
              <Text style={ms.pageSub}>Elige cómo empezar</Text>
            </View>
          </View>

          {creating && <ActivityIndicator color="#0891B2" style={{ marginTop: 40 }} />}

          {!creating && (
            <>
              {/* Path A: Start blank */}
              <TouchableOpacity style={ms.pathCard} onPress={createBlank}>
                <View style={[ms.pathIcon, { backgroundColor: '#CFFAFE22' }]}>
                  <Ionicons name="create-outline" size={28} color="#0891B2" />
                </View>
                <View style={ms.pathBody}>
                  <Text style={ms.pathTitle}>Empezar de Cero</Text>
                  <Text style={ms.pathDesc}>Menú vacío. Agrega productos uno por uno con nombre, precio y foto.</Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color="#94A3B8" />
              </TouchableOpacity>

              {/* Path B: Template */}
              <Text style={ms.sectionLabel}>O elige una plantilla</Text>
              {TEMPLATES.map(t => (
                <TouchableOpacity key={t.id} style={ms.pathCard} onPress={() => createFromTemplate(t)}>
                  <View style={[ms.pathIcon, { backgroundColor: '#D1FAE522' }]}>
                    <Ionicons name={t.icon as any} size={24} color="#059669" />
                  </View>
                  <View style={ms.pathBody}>
                    <Text style={ms.pathTitle}>{t.name} Template</Text>
                    <Text style={ms.pathDesc}>{t.items.length} productos de ejemplo · edítalos y agrega los tuyos</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={18} color="#94A3B8" />
                </TouchableOpacity>
              ))}

              {/* Path C: Import image */}
              <TouchableOpacity
                style={ms.pathCard}
                onPress={() => { setShowCreate(false); router.push('/workspace/menu-import'); }}
              >
                <View style={[ms.pathIcon, { backgroundColor: '#FFEDD5' }]}>
                  <Ionicons name="sparkles-outline" size={28} color="#EA580C" />
                </View>
                <View style={ms.pathBody}>
                  <Text style={ms.pathTitle}>Importar con IA (foto del menú)</Text>
                  <Text style={ms.pathDesc}>Sube la foto de tu menú físico. La IA escribe los productos y precios; tú solo revisas.</Text>
                </View>
                <View style={ms.comingPronto}><Text style={ms.comingProntoText}>NUEVO</Text></View>
              </TouchableOpacity>
              {/* Path D: mi propio diseño, ya leído por la IA */}
              <TouchableOpacity
                style={ms.pathCard}
                onPress={() => { setShowCreate(false); router.push('/workspace/menu-templates'); }}
                testID="create-from-my-design"
              >
                <View style={[ms.pathIcon, { backgroundColor: '#F5F3FF' }]}>
                  <Ionicons name="albums-outline" size={26} color="#7C3AED" />
                </View>
                <View style={ms.pathBody}>
                  <Text style={ms.pathTitle}>Desde mi propio diseño</Text>
                  <Text style={ms.pathDesc}>Reusá un diseño tuyo que la IA ya volvió editable. Cambiás nombres, precios y fotos; el diseño queda igual.</Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color="#94A3B8" />
              </TouchableOpacity>
            </>
          )}
        </ScrollView>
      </View>
    );
  }

  return (
    <View style={ms.root}>
      <ScrollView contentContainerStyle={[ms.content, { paddingBottom: insets.bottom + 24 }]}>
        <View style={ms.header}>
          <View>
            <Text style={ms.pageTitle}>Menús y carteleras</Text>
            <Text style={ms.pageSub}>
              {menus.length + designs.length} en total
              {designs.length ? ` · ${designs.length} cartelera${designs.length !== 1 ? 's' : ''}` : ''}
            </Text>
          </View>
          <View style={ms.headerActions}>
            <TouchableOpacity
              style={ms.templatesBtn}
              onPress={() => router.push('/workspace/signage-templates')}
              testID="open-templates"
            >
              <Ionicons name="albums-outline" size={16} color="#7C3AED" />
              <Text style={ms.templatesBtnText}>Plantillas Pro</Text>
            </TouchableOpacity>
            <TouchableOpacity style={ms.addBtn} onPress={() => setShowCreate(true)}>
              <Ionicons name="add" size={16} color="#fff" />
              <Text style={ms.addBtnText}>Crear Menú</Text>
            </TouchableOpacity>
          </View>
        </View>

        {loading && <ActivityIndicator color="#0891B2" style={{ marginTop: 40 }} />}
        {!!error && !loading && <Text style={ms.errorText}>{error}</Text>}

        {!loading && menus.length === 0 && designs.length === 0 && !error && (
          <View style={ms.empty}>
            <Ionicons name="fast-food-outline" size={40} color="#CBD5E1" />
            <Text style={ms.emptyTitle}>Todavía no tienes menús</Text>
            <Text style={ms.emptyText}>Crea un menú para publicarlo en tus pantallas.</Text>
            <TouchableOpacity style={[ms.addBtn, { marginTop: 16 }]} onPress={() => setShowCreate(true)}>
              <Ionicons name="add" size={16} color="#fff" />
              <Text style={ms.addBtnText}>Crear Primer Menú</Text>
            </TouchableOpacity>
          </View>
        )}

        {designs.map(d => (
          <View key={d.id} style={ms.menuCard} testID={`design-row-${d.id}`}>
            <TouchableOpacity
              style={ms.menuCardMain}
              onPress={() => router.push(`/workspace/design-edit?id=${d.id}`)}
            >
              <View style={[ms.menuIcon, { backgroundColor: '#F5F3FF' }]}>
                <Ionicons name="color-wand" size={20} color="#7C3AED" />
              </View>
              <View style={ms.menuBody}>
                <Text style={ms.menuName}>{d.name}</Text>
                <Text style={ms.menuMeta}>Cartelera profesional · {whereLive(d)}</Text>
              </View>
              <View style={[ms.statusBadge, { backgroundColor: d.status === 'published' ? '#D1FAE5' : '#F8FAFC' }]}>
                <Text style={{ color: d.status === 'published' ? '#059669' : '#64748B', fontSize: 10, fontWeight: '700' }}>
                  {d.status === 'published' ? '● EN VIVO' : 'BORRADOR'}
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={16} color="#94A3B8" />
            </TouchableOpacity>
            <TouchableOpacity style={ms.deleteBtn} onPress={() => deleteDesign(d)}
                              testID={`delete-design-row-${d.id}`}>
              <Ionicons name="trash-outline" size={16} color="#DC2626" />
            </TouchableOpacity>
          </View>
        ))}

        {menus.map(m => (
          <View key={m.id} style={ms.menuCard}>
            <TouchableOpacity
              style={ms.menuCardMain}
              onPress={() => router.push({ pathname: '/workspace/menu-edit', params: { id: m.id } })}
            >
              <View style={ms.menuIcon}>
                <Ionicons name="fast-food" size={20} color="#0891B2" />
              </View>
              <View style={ms.menuBody}>
                <Text style={ms.menuName}>{m.name}</Text>
                <Text style={ms.menuMeta}>
                  {m.items?.length || 0} producto{(m.items?.length || 0) !== 1 ? 's' : ''}
                  {m.source && m.source !== 'blank' ? ` · ${m.source}` : ''}
                </Text>
              </View>
              <View style={[ms.statusBadge, { backgroundColor: m.status === 'published' ? '#D1FAE5' : '#F8FAFC' }]}>
                <Text style={{ color: m.status === 'published' ? '#059669' : '#64748B', fontSize: 10, fontWeight: '700' }}>
                  {m.status === 'published' ? '● LIVE' : 'DRAFT'}
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={16} color="#94A3B8" />
            </TouchableOpacity>
            <TouchableOpacity style={ms.deleteBtn} onPress={() => deleteMenu(m)}>
              <Ionicons name="trash-outline" size={16} color="#DC2626" />
            </TouchableOpacity>
          </View>
        ))}
      </ScrollView>
      <AppDialog state={dialog} onDismiss={() => setDialog(null)} />
    </View>
  );
}

const ms = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  content: { padding: 20, gap: 12 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 },
  createHeader: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 24 },
  backBtn: { padding: 8, backgroundColor: '#FFFFFF', borderRadius: 10 },
  pageTitle: { fontSize: 22, fontWeight: '800', color: '#0F172A' },
  pageSub: { fontSize: 13, color: '#64748B', marginTop: 2 },
  headerActions: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  templatesBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#F5F3FF', borderWidth: 1, borderColor: '#DDD6FE', paddingHorizontal: 12, minHeight: 40, borderRadius: 10, justifyContent: 'center' },
  templatesBtnText: { color: '#6D28D9', fontSize: 13, fontWeight: '700' },

  addBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#0891B2', paddingHorizontal: 14, paddingVertical: 9, borderRadius: 10 },
  addBtnText: { color: '#fff', fontSize: 13, fontWeight: '700' },
  errorText: { color: '#DC2626', fontSize: 13, padding: 16 },
  empty: { alignItems: 'center', paddingVertical: 60, gap: 10 },
  emptyTitle: { fontSize: 17, fontWeight: '700', color: '#64748B' },
  emptyText: { fontSize: 13, color: '#64748B', textAlign: 'center', maxWidth: 280 },
  pathCard: { flexDirection: 'row', alignItems: 'center', gap: 14, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 14, padding: 16 },
  pathIcon: { width: 52, height: 52, borderRadius: 14, justifyContent: 'center', alignItems: 'center' },
  pathBody: { flex: 1, gap: 3 },
  pathTitle: { fontSize: 15, fontWeight: '700', color: '#0F172A' },
  pathDesc: { fontSize: 12, color: '#64748B', lineHeight: 18 },
  sectionLabel: { fontSize: 11, fontWeight: '700', color: '#94A3B8', textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 8, marginBottom: -4 },
  comingPronto: { backgroundColor: '#F8FAFC', borderRadius: 8, paddingHorizontal: 8, paddingVertical: 3 },
  comingProntoText: { color: '#D97706', fontSize: 10, fontWeight: '700' },
  menuCard: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 14 },
  menuCardMain: { flex: 1, flexDirection: 'row', alignItems: 'center', padding: 14, gap: 12 },
  menuIcon: { width: 40, height: 40, borderRadius: 10, backgroundColor: '#CFFAFE22', justifyContent: 'center', alignItems: 'center' },
  menuBody: { flex: 1, gap: 2 },
  menuName: { fontSize: 14, fontWeight: '700', color: '#0F172A' },
  menuMeta: { fontSize: 12, color: '#64748B' },
  statusBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 12 },
  deleteBtn: { padding: 14, borderLeftWidth: 1, borderLeftColor: '#E2E8F0' },
});
