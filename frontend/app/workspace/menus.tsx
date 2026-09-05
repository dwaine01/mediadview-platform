import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity, ActivityIndicator,
  Alert, useWindowDimensions
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { workspaceAPI } from '../../src/services/api';

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

export default function WorkspaceMenus() {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const [menus, setMenus] = useState<Menu[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try { setLoading(true); setError(''); const res = await workspaceAPI.menus(); setMenus(res.data || []); }
    catch (e: any) { setError(e.response?.data?.detail || e.message || 'Failed to load'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const createBlank = async () => {
    setCreating(true);
    try {
      const res = await workspaceAPI.createMenu({ name: 'New Menu', source: 'blank', items: [] });
      router.push({ pathname: '/workspace/menu-edit', params: { id: res.data.id } });
    } catch (e: any) { Alert.alert('Error', e.response?.data?.detail || e.message); }
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
    } catch (e: any) { Alert.alert('Error', e.response?.data?.detail || e.message); }
    finally { setCreating(false); setShowCreate(false); }
  };

  const deleteMenu = (menu: Menu) => {
    Alert.alert('Delete Menu', `Delete "${menu.name}"? This cannot be undone.`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: async () => {
        try { await workspaceAPI.deleteMenu(menu.id); load(); }
        catch (e: any) { Alert.alert('Error', e.response?.data?.detail || e.message); }
      }},
    ]);
  };

  if (showCreate) {
    return (
      <View style={ms.root}>
        <ScrollView contentContainerStyle={[ms.content, { paddingBottom: insets.bottom + 24 }]}>
          <View style={ms.createHeader}>
            <TouchableOpacity onPress={() => setShowCreate(false)} style={ms.backBtn}>
              <Ionicons name="arrow-back" size={20} color="#9CA3AF" />
            </TouchableOpacity>
            <View>
              <Text style={ms.pageTitle}>Create Menu</Text>
              <Text style={ms.pageSub}>Choose how to start</Text>
            </View>
          </View>

          {creating && <ActivityIndicator color="#6366F1" style={{ marginTop: 40 }} />}

          {!creating && (
            <>
              {/* Path A: Start blank */}
              <TouchableOpacity style={ms.pathCard} onPress={createBlank}>
                <View style={[ms.pathIcon, { backgroundColor: '#312E8122' }]}>
                  <Ionicons name="create-outline" size={28} color="#818CF8" />
                </View>
                <View style={ms.pathBody}>
                  <Text style={ms.pathTitle}>Start from Scratch</Text>
                  <Text style={ms.pathDesc}>Empty menu. Add items one by one with name, price, and photo.</Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color="#4B5563" />
              </TouchableOpacity>

              {/* Path B: Template */}
              <Text style={ms.sectionLabel}>Or choose a template</Text>
              {TEMPLATES.map(t => (
                <TouchableOpacity key={t.id} style={ms.pathCard} onPress={() => createFromTemplate(t)}>
                  <View style={[ms.pathIcon, { backgroundColor: '#0C4A2222' }]}>
                    <Ionicons name={t.icon as any} size={24} color="#34D399" />
                  </View>
                  <View style={ms.pathBody}>
                    <Text style={ms.pathTitle}>{t.name} Template</Text>
                    <Text style={ms.pathDesc}>{t.items.length} sample items · edit and add yours</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={18} color="#4B5563" />
                </TouchableOpacity>
              ))}

              {/* Path C: Import image */}
              <TouchableOpacity
                style={[ms.pathCard, { opacity: 0.6 }]}
                onPress={() => Alert.alert('Coming Soon', 'Image import with AI extraction coming soon. Use templates or start blank for now.')}
              >
                <View style={[ms.pathIcon, { backgroundColor: '#431407' }]}>
                  <Ionicons name="image-outline" size={28} color="#FB923C" />
                </View>
                <View style={ms.pathBody}>
                  <Text style={ms.pathTitle}>Import Image / PDF</Text>
                  <Text style={ms.pathDesc}>Upload your existing menu image. AI extracts items for you to review.</Text>
                </View>
                <View style={ms.comingSoon}><Text style={ms.comingSoonText}>Soon</Text></View>
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
            <Text style={ms.pageTitle}>Menus</Text>
            <Text style={ms.pageSub}>{menus.length} menu{menus.length !== 1 ? 's' : ''}</Text>
          </View>
          <TouchableOpacity style={ms.addBtn} onPress={() => setShowCreate(true)}>
            <Ionicons name="add" size={16} color="#fff" />
            <Text style={ms.addBtnText}>Create Menu</Text>
          </TouchableOpacity>
        </View>

        {loading && <ActivityIndicator color="#6366F1" style={{ marginTop: 40 }} />}
        {!!error && !loading && <Text style={ms.errorText}>{error}</Text>}

        {!loading && menus.length === 0 && !error && (
          <View style={ms.empty}>
            <Ionicons name="fast-food-outline" size={40} color="#374151" />
            <Text style={ms.emptyTitle}>No menus yet</Text>
            <Text style={ms.emptyText}>Create a menu to publish it to your screens.</Text>
            <TouchableOpacity style={[ms.addBtn, { marginTop: 16 }]} onPress={() => setShowCreate(true)}>
              <Ionicons name="add" size={16} color="#fff" />
              <Text style={ms.addBtnText}>Create First Menu</Text>
            </TouchableOpacity>
          </View>
        )}

        {menus.map(m => (
          <View key={m.id} style={ms.menuCard}>
            <TouchableOpacity
              style={ms.menuCardMain}
              onPress={() => router.push({ pathname: '/workspace/menu-edit', params: { id: m.id } })}
            >
              <View style={ms.menuIcon}>
                <Ionicons name="fast-food" size={20} color="#818CF8" />
              </View>
              <View style={ms.menuBody}>
                <Text style={ms.menuName}>{m.name}</Text>
                <Text style={ms.menuMeta}>
                  {m.items?.length || 0} item{(m.items?.length || 0) !== 1 ? 's' : ''}
                  {m.source ? ` · ${m.source}` : ''}
                </Text>
              </View>
              <View style={[ms.statusBadge, { backgroundColor: m.status === 'published' ? '#064E3B' : '#1C1917' }]}>
                <Text style={{ color: m.status === 'published' ? '#34D399' : '#9CA3AF', fontSize: 10, fontWeight: '700' }}>
                  {m.status === 'published' ? '● LIVE' : 'DRAFT'}
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={16} color="#4B5563" />
            </TouchableOpacity>
            <TouchableOpacity style={ms.deleteBtn} onPress={() => deleteMenu(m)}>
              <Ionicons name="trash-outline" size={16} color="#F87171" />
            </TouchableOpacity>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const ms = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0B0F1A' },
  content: { padding: 20, gap: 12 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 },
  createHeader: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 24 },
  backBtn: { padding: 8, backgroundColor: '#111827', borderRadius: 10 },
  pageTitle: { fontSize: 22, fontWeight: '800', color: '#F1F5F9' },
  pageSub: { fontSize: 13, color: '#64748B', marginTop: 2 },
  addBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#6366F1', paddingHorizontal: 14, paddingVertical: 9, borderRadius: 10 },
  addBtnText: { color: '#fff', fontSize: 13, fontWeight: '700' },
  errorText: { color: '#F87171', fontSize: 13, padding: 16 },
  empty: { alignItems: 'center', paddingVertical: 60, gap: 10 },
  emptyTitle: { fontSize: 17, fontWeight: '700', color: '#9CA3AF' },
  emptyText: { fontSize: 13, color: '#64748B', textAlign: 'center', maxWidth: 280 },
  pathCard: { flexDirection: 'row', alignItems: 'center', gap: 14, backgroundColor: '#111827', borderWidth: 1, borderColor: '#1E293B', borderRadius: 14, padding: 16 },
  pathIcon: { width: 52, height: 52, borderRadius: 14, justifyContent: 'center', alignItems: 'center' },
  pathBody: { flex: 1, gap: 3 },
  pathTitle: { fontSize: 15, fontWeight: '700', color: '#F1F5F9' },
  pathDesc: { fontSize: 12, color: '#64748B', lineHeight: 18 },
  sectionLabel: { fontSize: 11, fontWeight: '700', color: '#4B5563', textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 8, marginBottom: -4 },
  comingSoon: { backgroundColor: '#1C1917', borderRadius: 8, paddingHorizontal: 8, paddingVertical: 3 },
  comingSoonText: { color: '#D97706', fontSize: 10, fontWeight: '700' },
  menuCard: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#111827', borderWidth: 1, borderColor: '#1E293B', borderRadius: 14 },
  menuCardMain: { flex: 1, flexDirection: 'row', alignItems: 'center', padding: 14, gap: 12 },
  menuIcon: { width: 40, height: 40, borderRadius: 10, backgroundColor: '#312E8122', justifyContent: 'center', alignItems: 'center' },
  menuBody: { flex: 1, gap: 2 },
  menuName: { fontSize: 14, fontWeight: '700', color: '#F1F5F9' },
  menuMeta: { fontSize: 12, color: '#64748B' },
  statusBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 12 },
  deleteBtn: { padding: 14, borderLeftWidth: 1, borderLeftColor: '#1E293B' },
});
