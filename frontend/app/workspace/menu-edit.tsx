import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity, TextInput,
  ActivityIndicator, Alert, Modal, Switch, KeyboardAvoidingView, Platform
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import { workspaceAPI } from '../../src/services/api';

type MenuItem = {
  id: string; name: string; price: number;
  description?: string; category?: string; available: boolean;
  media_id?: string; image_url?: string;
};
type Menu = {
  id: string; name: string; description?: string;
  items: MenuItem[]; status: string; screen_ids?: string[];
};

function ItemCard({
  item, onEdit, onDelete
}: { item: MenuItem; onEdit: () => void; onDelete: () => void }) {
  return (
    <View style={ed.itemCard}>
      <View style={ed.itemLeft}>
        <View style={ed.itemAvailDot}>
          <View style={[ed.availDot, { backgroundColor: item.available ? '#059669' : '#94A3B8' }]} />
        </View>
        <View style={ed.itemBody}>
          <Text style={ed.itemName}>{item.name}</Text>
          {!!item.category && <Text style={ed.itemCat}>{item.category}</Text>}
          {!!item.description && <Text style={ed.itemDesc} numberOfLines={1}>{item.description}</Text>}
        </View>
      </View>
      <View style={ed.itemRight}>
        <Text style={ed.itemPrice}>${Number(item.price).toFixed(2)}</Text>
        <TouchableOpacity onPress={onEdit} style={ed.iconBtn}>
          <Ionicons name="pencil-outline" size={16} color="#0891B2" />
        </TouchableOpacity>
        <TouchableOpacity onPress={onDelete} style={ed.iconBtn}>
          <Ionicons name="trash-outline" size={16} color="#DC2626" />
        </TouchableOpacity>
      </View>
    </View>
  );
}

export default function MenuEditor() {
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ id: string }>();
  const menuId = params.id;

  const [menu, setMenu] = useState<Menu | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState('');

  // Add/edit item modal
  const [showItemModal, setShowItemModal] = useState(false);
  const [editingItem, setEditingItem] = useState<MenuItem | null>(null);
  const [itemName, setItemName] = useState('');
  const [itemPrice, setItemPrice] = useState('');
  const [itemDesc, setItemDesc] = useState('');
  const [itemCat, setItemCat] = useState('');
  const [itemAvail, setItemAvail] = useState(true);
  const [itemSaving, setItemSaving] = useState(false);
  const [itemError, setItemError] = useState('');

  // Edit menu name
  const [menuName, setMenuName] = useState('');

  const load = useCallback(async () => {
    try {
      setLoading(true); setError('');
      const res = await workspaceAPI.getMenu(menuId);
      setMenu(res.data);
      setMenuName(res.data.name || '');
    } catch (e: any) { setError(e.response?.data?.detail || e.message || 'No se pudo cargar el menú'); }
    finally { setLoading(false); }
  }, [menuId]);

  useEffect(() => { load(); }, [load]);

  const saveMenuName = async () => {
    if (!menuName.trim()) return;
    setSaving(true);
    try {
      await workspaceAPI.updateMenu(menuId, { name: menuName.trim() });
      setMenu(prev => prev ? { ...prev, name: menuName.trim() } : prev);
    } catch (e: any) { Alert.alert('Error', e.response?.data?.detail || e.message); }
    finally { setSaving(false); }
  };

  const openAddItem = () => {
    setEditingItem(null);
    setItemName(''); setItemPrice(''); setItemDesc(''); setItemCat(''); setItemAvail(true); setItemError('');
    setShowItemModal(true);
  };

  const openEditItem = (item: MenuItem) => {
    setEditingItem(item);
    setItemName(item.name); setItemPrice(String(item.price)); setItemDesc(item.description || '');
    setItemCat(item.category || ''); setItemAvail(item.available); setItemError('');
    setShowItemModal(true);
  };

  const saveItem = async () => {
    if (!itemName.trim()) { setItemError('El nombre del producto es obligatorio'); return; }
    const price = parseFloat(itemPrice) || 0;
    setItemSaving(true); setItemError('');
    try {
      const payload = {
        name: itemName.trim(), price,
        description: itemDesc.trim() || undefined,
        category: itemCat.trim() || undefined,
        available: itemAvail,
      };
      if (editingItem) {
        await workspaceAPI.updateMenuItem(menuId, editingItem.id, payload);
      } else {
        await workspaceAPI.addMenuItem(menuId, payload);
      }
      await load();
      setShowItemModal(false);
    } catch (e: any) { setItemError(e.response?.data?.detail || e.message || 'No se pudo guardar'); }
    finally { setItemSaving(false); }
  };

  const deleteItem = (item: MenuItem) => {
    Alert.alert('Remove Item', `Remove "${item.name}"?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Remove', style: 'destructive', onPress: async () => {
        try { await workspaceAPI.deleteMenuItem(menuId, item.id); load(); }
        catch (e: any) { Alert.alert('Error', e.response?.data?.detail || e.message); }
      }},
    ]);
  };

  const publishMenu = async () => {
    if (!menu?.items?.length) {
      Alert.alert('Sin productos', 'Agrega al menos un producto antes de publicar.'); return;
    }
    Alert.alert(
      'Publish Menu',
      'This will make the menu visible on all your connected screens. Continue?',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Publish', onPress: async () => {
          setPublishing(true);
          try {
            await workspaceAPI.publishMenu(menuId);
            Alert.alert('Published!', 'Your menu is now live on your screens.', [
              { text: 'OK', onPress: () => router.back() },
            ]);
          } catch (e: any) { Alert.alert('Error', e.response?.data?.detail || e.message); }
          finally { setPublishing(false); }
        }},
      ]
    );
  };

  // Group items by category
  const grouped = (menu?.items || []).reduce<Record<string, MenuItem[]>>((acc, item) => {
    const cat = item.category || 'Other';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(item);
    return acc;
  }, {});

  if (loading) {
    return (
      <View style={[ed.root, { justifyContent: 'center', alignItems: 'center' }]}>
        <ActivityIndicator color="#0891B2" size="large" />
      </View>
    );
  }

  if (error) {
    return (
      <View style={[ed.root, { padding: 24 }]}>
        <TouchableOpacity style={ed.backBtn} onPress={() => router.back()}>
          <Ionicons name="arrow-back" size={20} color="#64748B" />
          <Text style={ed.backBtnText}>Atrás</Text>
        </TouchableOpacity>
        <Text style={{ color: '#DC2626', marginTop: 24, fontSize: 14 }}>{error}</Text>
      </View>
    );
  }

  return (
    <View style={ed.root}>
      <ScrollView contentContainerStyle={[ed.content, { paddingBottom: insets.bottom + 100 }]}>
        {/* Header */}
        <View style={ed.topBar}>
          <TouchableOpacity style={ed.backBtn} onPress={() => router.back()}>
            <Ionicons name="arrow-back" size={20} color="#64748B" />
            <Text style={ed.backBtnText}>Menús</Text>
          </TouchableOpacity>
          <View style={[ed.liveTag, { backgroundColor: menu?.status === 'published' ? '#D1FAE5' : '#F8FAFC' }]}>
            <View style={[ed.liveDot, { backgroundColor: menu?.status === 'published' ? '#059669' : '#64748B' }]} />
            <Text style={{ color: menu?.status === 'published' ? '#059669' : '#64748B', fontSize: 11, fontWeight: '700' }}>
              {menu?.status === 'published' ? 'LIVE' : 'DRAFT'}
            </Text>
          </View>
        </View>

        {/* Nombre del menú */}
        <View style={ed.nameSec}>
          <TextInput
            style={ed.nameInput}
            value={menuName}
            onChangeText={setMenuName}
            onBlur={saveMenuName}
            placeholder="Nombre del menú"
            placeholderTextColor="#CBD5E1"
            returnKeyType="done"
            onSubmitEditing={saveMenuName}
          />
          {saving && <ActivityIndicator size={14} color="#0891B2" style={{ marginLeft: 8 }} />}
        </View>

        {/* Items by category */}
        {Object.keys(grouped).length === 0 ? (
          <View style={ed.empty}>
            <Ionicons name="fast-food-outline" size={36} color="#CBD5E1" />
            <Text style={ed.emptyTitle}>Todavía no hay productos</Text>
            <Text style={ed.emptyText}>Agrega tu primer producto abajo.</Text>
          </View>
        ) : (
          Object.entries(grouped).map(([cat, catItems]) => (
            <View key={cat} style={ed.catSection}>
              <Text style={ed.catLabel}>{cat}</Text>
              {catItems.map(item => (
                <ItemCard
                  key={item.id} item={item}
                  onEdit={() => openEditItem(item)}
                  onDelete={() => deleteItem(item)}
                />
              ))}
            </View>
          ))
        )}

        {/* Add item button */}
        <TouchableOpacity style={ed.addItemBtn} onPress={openAddItem}>
          <Ionicons name="add-circle-outline" size={20} color="#0891B2" />
          <Text style={ed.addItemBtnText}>Agregar Producto</Text>
        </TouchableOpacity>
      </ScrollView>

      {/* Sticky publish bar */}
      <View style={[ed.publishBar, { paddingBottom: insets.bottom + 12 }]}>
        <View style={ed.publishInfo}>
          <Text style={ed.publishCount}>{menu?.items?.length || 0} items</Text>
          <Text style={ed.publishHint}>
            {menu?.status === 'published' ? 'En vivo en tus pantallas' : 'Todavía sin publicar'}
          </Text>
        </View>
        <TouchableOpacity
          style={[ed.publishBtn, publishing && { opacity: 0.6 }]}
          onPress={publishMenu}
          disabled={publishing}
        >
          {publishing
            ? <ActivityIndicator color="#fff" size={16} />
            : <>
                <Ionicons name="cloud-upload-outline" size={18} color="#fff" />
                <Text style={ed.publishBtnText}>
                  {menu?.status === 'published' ? 'Update Live' : 'Publicar en Pantallas'}
                </Text>
              </>
          }
        </TouchableOpacity>
      </View>

      {/* Add/Edit Item Modal */}
      <Modal visible={showItemModal} transparent animationType="slide" onRequestClose={() => setShowItemModal(false)}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={ed.modalOverlay}>
          <View style={ed.modal}>
            <View style={ed.modalHeader}>
              <Text style={ed.modalTitle}>{editingItem ? 'Edit Item' : 'Agregar Producto'}</Text>
              <TouchableOpacity onPress={() => setShowItemModal(false)}>
                <Ionicons name="close" size={22} color="#64748B" />
              </TouchableOpacity>
            </View>

            <ScrollView showsVerticalScrollIndicator={false}>
              <View style={ed.fieldRow}>
                <View style={ed.fieldFlex}>
                  <Text style={ed.fieldLabel}>Name *</Text>
                  <TextInput style={ed.fieldInput} value={itemName} onChangeText={setItemName}
                    placeholder="ej. Pizza Margherita" placeholderTextColor="#CBD5E1" />
                </View>
                <View style={{ width: 100 }}>
                  <Text style={ed.fieldLabel}>Price ($)</Text>
                  <TextInput style={ed.fieldInput} value={itemPrice} onChangeText={setItemPrice}
                    placeholder="12.50" placeholderTextColor="#CBD5E1" keyboardType="decimal-pad" />
                </View>
              </View>

              <View style={ed.fieldWrap}>
                <Text style={ed.fieldLabel}>Categoría</Text>
                <TextInput style={ed.fieldInput} value={itemCat} onChangeText={setItemCat}
                  placeholder="ej. Pizza, Bebidas, Postres" placeholderTextColor="#CBD5E1" />
              </View>

              <View style={ed.fieldWrap}>
                <Text style={ed.fieldLabel}>Description (optional)</Text>
                <TextInput style={[ed.fieldInput, { minHeight: 64 }]}
                  value={itemDesc} onChangeText={setItemDesc} multiline
                  placeholder="Descripción corta…" placeholderTextColor="#CBD5E1" />
              </View>

              <View style={ed.availRow}>
                <Text style={ed.fieldLabel}>Disponible</Text>
                <Switch value={itemAvail} onValueChange={setItemAvail}
                  trackColor={{ false: '#E2E8F0', true: '#0E7490' }} thumbColor="#fff" />
              </View>

              {!!itemError && <Text style={ed.itemErrText}>{itemError}</Text>}

              <TouchableOpacity
                style={[ed.saveItemBtn, itemSaving && { opacity: 0.6 }]}
                onPress={saveItem} disabled={itemSaving}
              >
                {itemSaving
                  ? <ActivityIndicator color="#fff" size={16} />
                  : <Text style={ed.saveItemBtnText}>{editingItem ? 'Save Changes' : 'Agregar Producto'}</Text>
                }
              </TouchableOpacity>
            </ScrollView>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const ed = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F8FAFC' },
  content: { padding: 20, gap: 16 },
  topBar: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, padding: 8 },
  backBtnText: { fontSize: 14, color: '#64748B', fontWeight: '600' },
  liveTag: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 20 },
  liveDot: { width: 6, height: 6, borderRadius: 3 },
  nameSec: { flexDirection: 'row', alignItems: 'center' },
  nameInput: { flex: 1, fontSize: 24, fontWeight: '800', color: '#0F172A', padding: 0 },
  empty: { alignItems: 'center', paddingVertical: 40, gap: 8 },
  emptyTitle: { fontSize: 16, fontWeight: '700', color: '#64748B' },
  emptyText: { fontSize: 13, color: '#64748B', textAlign: 'center' },
  catSection: { gap: 8 },
  catLabel: { fontSize: 11, fontWeight: '700', color: '#0891B2', textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 4 },
  itemCard: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 12, padding: 14, gap: 8 },
  itemLeft: { flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 },
  itemAvailDot: { justifyContent: 'center', alignItems: 'center' },
  availDot: { width: 8, height: 8, borderRadius: 4 },
  itemBody: { flex: 1, gap: 2 },
  itemName: { fontSize: 14, fontWeight: '700', color: '#0F172A' },
  itemCat: { fontSize: 11, color: '#0891B2', fontWeight: '600' },
  itemDesc: { fontSize: 11, color: '#64748B' },
  itemRight: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  itemPrice: { fontSize: 15, fontWeight: '800', color: '#059669' },
  iconBtn: { padding: 6 },
  addItemBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderWidth: 2, borderColor: '#E2E8F0', borderStyle: 'dashed', borderRadius: 12, padding: 16, marginTop: 4 },
  addItemBtnText: { fontSize: 14, fontWeight: '600', color: '#0891B2' },
  publishBar: { position: 'absolute', bottom: 0, left: 0, right: 0, backgroundColor: '#FFFFFF', borderTopWidth: 1, borderTopColor: '#E2E8F0', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, paddingTop: 12 },
  publishInfo: { gap: 2 },
  publishCount: { fontSize: 15, fontWeight: '700', color: '#0F172A' },
  publishHint: { fontSize: 11, color: '#64748B' },
  publishBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: '#059669', paddingHorizontal: 18, paddingVertical: 12, borderRadius: 12 },
  publishBtnText: { color: '#fff', fontSize: 14, fontWeight: '700' },
  modalOverlay: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(15,23,42,0.45)' },
  modal: { backgroundColor: '#FFFFFF', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, paddingBottom: 36, maxHeight: '90%' },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 },
  modalTitle: { fontSize: 18, fontWeight: '800', color: '#0F172A' },
  fieldRow: { flexDirection: 'row', gap: 12, marginBottom: 14 },
  fieldFlex: { flex: 1 },
  fieldWrap: { marginBottom: 14 },
  fieldLabel: { fontSize: 11, fontWeight: '700', color: '#64748B', textTransform: 'uppercase', letterSpacing: 0.4, marginBottom: 6 },
  fieldInput: { fontSize: 15, color: '#0F172A', backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 10, padding: 12 },
  availRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 },
  itemErrText: { color: '#DC2626', fontSize: 13, marginBottom: 12, textAlign: 'center' },
  saveItemBtn: { backgroundColor: '#0891B2', borderRadius: 12, padding: 16, alignItems: 'center', marginTop: 4 },
  saveItemBtnText: { color: '#fff', fontSize: 15, fontWeight: '700' },
});
