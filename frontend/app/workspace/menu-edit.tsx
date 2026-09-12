import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity, TextInput,
  ActivityIndicator, Modal, Switch, KeyboardAvoidingView, Platform, Image, Linking
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import { workspaceAPI } from '../../src/services/api';
import AppDialog, { type DialogState } from '../../src/components/AppDialog';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

type MenuItem = {
  id: string; name: string; price: number;
  description?: string; category?: string; available: boolean;
  media_id?: string; image_url?: string;
};
type Menu = {
  id: string; name: string; description?: string;
  items: MenuItem[]; status: string; screen_ids?: string[];
  layout_mode?: string;
};

function ItemCard({
  item, onEdit, onDelete, onAiPhoto, generating, onToggleAvailable, toggling,
}: {
  item: MenuItem; onEdit: () => void; onDelete: () => void;
  onAiPhoto: () => void; generating: boolean;
  onToggleAvailable: () => void; toggling: boolean;
}) {
  return (
    <View style={[ed.itemCard, !item.available && ed.itemCardOut]}>
      <View style={ed.itemLeft}>
        {item.image_url ? (
          <Image source={{ uri: `${API_URL}${item.image_url}` }} style={ed.itemPhoto} resizeMode="cover" />
        ) : (
          <TouchableOpacity style={ed.aiPhotoBtn} onPress={onAiPhoto} disabled={generating} activeOpacity={0.8}>
            {generating
              ? <ActivityIndicator size="small" color="#0891B2" />
              : <><Ionicons name="sparkles" size={15} color="#0891B2" />
                  <Text style={ed.aiPhotoText}>Foto IA</Text></>}
          </TouchableOpacity>
        )}
        <View style={ed.itemAvailDot}>
          <View style={[ed.availDot, { backgroundColor: item.available ? '#059669' : '#94A3B8' }]} />
        </View>
        <View style={ed.itemBody}>
          <Text style={[ed.itemName, !item.available && ed.itemNameOut]}>{item.name}</Text>
          {!!item.category && <Text style={ed.itemCat}>{item.category}</Text>}
          {!!item.description && <Text style={ed.itemDesc} numberOfLines={1}>{item.description}</Text>}
          <TouchableOpacity
            style={[ed.soldOutChip, !item.available && ed.soldOutChipOn]}
            onPress={onToggleAvailable}
            disabled={toggling}
            activeOpacity={0.8}
          >
            {toggling
              ? <ActivityIndicator size="small" color={item.available ? '#64748B' : '#B45309'} />
              : <>
                  <Ionicons
                    name={item.available ? 'ellipse-outline' : 'close-circle'}
                    size={13}
                    color={item.available ? '#64748B' : '#B45309'}
                  />
                  <Text style={[ed.soldOutText, !item.available && ed.soldOutTextOn]}>
                    {item.available ? 'Marcar agotado' : 'AGOTADO · toca para reponer'}
                  </Text>
                </>}
          </TouchableOpacity>
        </View>
      </View>
      <View style={ed.itemRight}>
        <Text style={ed.itemPrice}>${Number(item.price).toFixed(2)}</Text>
        {!!item.image_url && (
          <TouchableOpacity onPress={onAiPhoto} style={ed.iconBtn} disabled={generating}>
            {generating
              ? <ActivityIndicator size="small" color="#0891B2" />
              : <Ionicons name="sparkles-outline" size={16} color="#0891B2" />}
          </TouchableOpacity>
        )}
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

  // Screen picker at publish time — a menu goes to the screens you choose,
  // not to every screen you own.
  const [showScreenPicker, setShowScreenPicker] = useState(false);
  const [screens, setScreens] = useState<{ id: string; name: string; status?: string }[]>([]);
  const [pickedScreens, setPickedScreens] = useState<string[]>([]);
  const [loadingScreens, setLoadingScreens] = useState(false);
  const [screensError, setScreensError] = useState('');

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

  // AI photos
  const [dialog, setDialog] = useState<DialogState>(null);
  const [generatingId, setGeneratingId] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [bulkProgress, setBulkProgress] = useState('');
  const [previewing, setPreviewing] = useState(false);

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
    } catch (e: any) { setDialog({ title: 'No se pudo guardar', message: e.response?.data?.detail || e.message }); }
    finally { setSaving(false); }
  };

  const generatePhoto = useCallback(async (item: MenuItem) => {
    setGeneratingId(item.id);
    try {
      const res = await workspaceAPI.aiPhotoForItem(menuId, item.id);
      setMenu(prev => prev ? {
        ...prev,
        items: prev.items.map(i => i.id === item.id
          ? { ...i, image_url: res.data.image_url, media_id: res.data.media_id }
          : i),
      } : prev);
    } catch (e: any) {
      setDialog({
        title: 'No se pudo generar la foto',
        message: e.response?.data?.detail || e.message || 'Intenta de nuevo en un momento.',
      });
    } finally { setGeneratingId(null); }
  }, [menuId]);

  const toggleAvailable = useCallback(async (item: MenuItem) => {
    setTogglingId(item.id);
    const next = !item.available;
    try {
      await workspaceAPI.updateMenuItem(menuId, item.id, { available: next });
      setMenu(prev => prev ? {
        ...prev,
        items: prev.items.map(i => i.id === item.id ? { ...i, available: next } : i),
      } : prev);
    } catch (e: any) {
      setDialog({ title: 'No se pudo actualizar', message: e.response?.data?.detail || e.message });
    } finally { setTogglingId(null); }
  }, [menuId]);

  const generateMissingPhotos = useCallback(async () => {
    const missing = (menu?.items || []).filter(i => !i.image_url);
    if (missing.length === 0) return;
    for (let i = 0; i < missing.length; i++) {
      setBulkProgress(`Generando foto ${i + 1} de ${missing.length}…`);
      await generatePhoto(missing[i]);
    }
    setBulkProgress('');
    setDialog({
      title: 'Fotos listas',
      icon: 'sparkles',
      message: `Generamos ${missing.length} foto(s). Revisa el menú y publica cuando estés conforme.`,
    });
  }, [menu, generatePhoto]);

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
    setDialog({
      title: `¿Quitar "${item.name}"?`,
      icon: 'trash-outline',
      options: [
        { label: 'Quitar', destructive: true, onPress: async () => {
          try { await workspaceAPI.deleteMenuItem(menuId, item.id); load(); }
          catch (e: any) { setDialog({ title: 'No se pudo quitar', message: e.response?.data?.detail || e.message }); }
        }},
        { label: 'Cancelar' },
      ],
    });
  };

  // Un menú sobre diseño propio no tiene lista de productos: lo que se publica
  // es la imagen con sus recuadros editados.
  const hasContent = !!menu?.items?.length || menu?.layout_mode === 'canvas';

  const publishMenu = () => {
    if (!hasContent) {
      setDialog({ title: 'Sin productos', message: 'Agrega al menos un producto antes de publicar.' });
      return;
    }
    // Preselect where this menu is already live; first publish preselects nothing
    // so the user has to choose consciously in which screen it goes.
    setPickedScreens(menu?.screen_ids?.length ? [...menu.screen_ids] : []);
    setScreensError('');
    setShowScreenPicker(true);
    setLoadingScreens(true);
    workspaceAPI.screens()
      .then(r => setScreens(r.data || []))
      .catch(e => setScreensError(e.response?.data?.detail || 'No pudimos cargar tus pantallas'))
      .finally(() => setLoadingScreens(false));
  };

  const toggleScreen = (id: string) =>
    setPickedScreens(prev => (prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]));

  const confirmPublish = async () => {
    if (!pickedScreens.length) { setScreensError('Elegí al menos una pantalla.'); return; }
    setPublishing(true); setScreensError('');
    try {
      const res = await workspaceAPI.publishMenu(menuId, { screen_ids: pickedScreens });
      setShowScreenPicker(false);
      const n = pickedScreens.length;
      const removed = res.data?.removed_from || 0;
      setDialog({
        title: '¡Publicado!',
        icon: 'checkmark-circle-outline',
        message: `Tu menú ya está en vivo en ${n} pantalla${n === 1 ? '' : 's'}.`
          + (removed ? ` Se quitó de ${removed} pantalla${removed === 1 ? '' : 's'} donde estaba antes.` : ''),
        options: [{ label: 'Volver a Menús', primary: true, onPress: () => router.push('/workspace/menus') },
                  { label: 'Seguir editando' }],
      });
      load();
    } catch (e: any) {
      setScreensError(e.response?.data?.detail || e.message || 'No se pudo publicar');
    } finally { setPublishing(false); }
  };

  // «Vista previa» — abre exactamente la página que el TV renderiza, a pantalla
  // completa. Para menús en borrador el backend firma un token corto porque el
  // render público sólo sirve menús publicados.
  const openPreview = async () => {
    if (!hasContent) {
      setDialog({ title: 'Sin productos', message: 'Agrega al menos un producto para ver la vista previa.' });
      return;
    }
    setPreviewing(true);
    try {
      const res = await workspaceAPI.menuPreviewUrl(menuId);
      await Linking.openURL(`${API_URL}${res.data.url}`);
    } catch (e: any) {
      setDialog({
        title: 'No se pudo abrir la vista previa',
        message: e.response?.data?.detail || e.message || 'Intentá de nuevo en un momento.',
      });
    } finally { setPreviewing(false); }
  };

  const missingPhotos = (menu?.items || []).filter(i => !i.image_url).length;
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
                  onAiPhoto={() => generatePhoto(item)}
                  generating={generatingId === item.id}
                  onToggleAvailable={() => toggleAvailable(item)}
                  toggling={togglingId === item.id}
                />
              ))}
            </View>
          ))
        )}

        {/* Fotos con IA */}
        {missingPhotos > 0 && (
          <TouchableOpacity
            style={ed.aiBanner}
            onPress={generateMissingPhotos}
            disabled={!!bulkProgress || !!generatingId}
            activeOpacity={0.85}
          >
            <View style={ed.aiBannerIcon}>
              {bulkProgress
                ? <ActivityIndicator size="small" color="#EA580C" />
                : <Ionicons name="sparkles" size={18} color="#EA580C" />}
            </View>
            <View style={{ flex: 1 }}>
              <Text style={ed.aiBannerTitle}>
                {bulkProgress || `${missingPhotos} producto${missingPhotos !== 1 ? 's' : ''} sin foto`}
              </Text>
              <Text style={ed.aiBannerText}>
                Genera fotos apetitosas con IA en segundos, sin sesión de fotografía.
              </Text>
            </View>
            {!bulkProgress && <Ionicons name="chevron-forward" size={18} color="#EA580C" />}
          </TouchableOpacity>
        )}

        {/* Mi propio diseño */}
        <TouchableOpacity
          style={ed.designBanner}
          onPress={() => router.push(`/workspace/menu-canvas?id=${menuId}`)}
          activeOpacity={0.85}
          testID="own-design"
        >
          <View style={ed.designIcon}>
            <Ionicons name="color-palette-outline" size={18} color="#7C3AED" />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={ed.designTitle}>Usar mi propio diseño</Text>
            <Text style={ed.designText}>
              Subí tu menú en JPG, PNG o PDF y cambiá precios y fotos sin tocar el diseño.
            </Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color="#7C3AED" />
        </TouchableOpacity>

        {/* Add item button */}
        <TouchableOpacity style={ed.addItemBtn} onPress={openAddItem}>
          <Ionicons name="add-circle-outline" size={20} color="#0891B2" />
          <Text style={ed.addItemBtnText}>Agregar Producto</Text>
        </TouchableOpacity>
      </ScrollView>

      {/* Sticky publish bar */}
      <View style={[ed.publishBar, { paddingBottom: insets.bottom + 12 }]}>
        <View style={ed.publishInfo}>
          <Text style={ed.publishCount}>
            {menu?.layout_mode === 'canvas' ? 'Mi diseño' : `${menu?.items?.length || 0} items`}
          </Text>
          <Text style={ed.publishHint}>
            {menu?.status === 'published' ? 'En vivo en tus pantallas' : 'Todavía sin publicar'}
          </Text>
        </View>
        <View style={ed.publishActions}>
          <TouchableOpacity
            style={[ed.previewBtn, previewing && { opacity: 0.6 }]}
            onPress={openPreview}
            disabled={previewing}
            testID="preview-menu"
          >
            {previewing
              ? <ActivityIndicator color="#0E7490" size={16} />
              : <>
                  <Ionicons name="tv-outline" size={18} color="#0E7490" />
                  <Text style={ed.previewBtnText}>Vista previa</Text>
                </>
            }
          </TouchableOpacity>
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
                    {menu?.status === 'published' ? 'Update Live' : 'Publicar'}
                  </Text>
                </>
            }
          </TouchableOpacity>
        </View>
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

      {/* ¿En qué pantallas? — selección al publicar */}
      <Modal visible={showScreenPicker} transparent animationType="slide"
             onRequestClose={() => setShowScreenPicker(false)}>
        <View style={ed.pickerOverlay}>
          <View style={[ed.pickerCard, { paddingBottom: insets.bottom + 16 }]}>
            <View style={ed.pickerHeader}>
              <Text style={ed.pickerTitle}>¿En qué pantallas?</Text>
              <TouchableOpacity onPress={() => setShowScreenPicker(false)}
                                hitSlop={{ top: 12, right: 12, bottom: 12, left: 12 }}>
                <Ionicons name="close" size={22} color="#64748B" />
              </TouchableOpacity>
            </View>
            <Text style={ed.pickerHint}>
              Elegí dónde querés mostrar «{menu?.name}». Las pantallas que no marques siguen con
              lo que tienen ahora.
            </Text>

            {screens.length > 1 && (
              <TouchableOpacity
                style={ed.pickAll}
                onPress={() => setPickedScreens(
                  pickedScreens.length === screens.length ? [] : screens.map(s => s.id))}
                testID="pick-all-screens"
              >
                <Ionicons
                  name={pickedScreens.length === screens.length ? 'checkbox' : 'square-outline'}
                  size={20}
                  color={pickedScreens.length === screens.length ? '#0891B2' : '#94A3B8'}
                />
                <Text style={ed.pickAllText}>
                  {pickedScreens.length === screens.length ? 'Quitar todas' : 'Seleccionar todas'}
                </Text>
                <Text style={ed.pickCount}>{pickedScreens.length}/{screens.length}</Text>
              </TouchableOpacity>
            )}

            {loadingScreens ? (
              <ActivityIndicator color="#0891B2" style={{ marginVertical: 28 }} />
            ) : (
              <ScrollView style={ed.pickerList} nestedScrollEnabled>
                {screens.map(s => {
                  const on = pickedScreens.includes(s.id);
                  return (
                    <TouchableOpacity key={s.id} style={[ed.pickItem, on && ed.pickItemOn]}
                                      onPress={() => toggleScreen(s.id)} testID={`pick-${s.id}`}>
                      <Ionicons name={on ? 'checkbox' : 'square-outline'} size={20}
                                color={on ? '#0891B2' : '#94A3B8'} />
                      <Text style={ed.pickItemText} numberOfLines={1}>{s.name}</Text>
                      {menu?.screen_ids?.includes(s.id) && (
                        <Text style={ed.pickLive}>en vivo</Text>
                      )}
                    </TouchableOpacity>
                  );
                })}
                {!screens.length && (
                  <Text style={ed.pickerHint}>Todavía no tenés pantallas conectadas.</Text>
                )}
              </ScrollView>
            )}

            {!!screensError && <Text style={ed.pickerErr}>{screensError}</Text>}

            <TouchableOpacity
              style={[ed.pickerBtn, (publishing || !pickedScreens.length) && ed.pickerBtnOff]}
              onPress={confirmPublish}
              disabled={publishing || !pickedScreens.length}
              testID="confirm-publish-menu"
            >
              {publishing
                ? <ActivityIndicator color="#fff" size={16} />
                : <Text style={ed.pickerBtnText}>
                    Publicar en {pickedScreens.length || 0} pantalla{pickedScreens.length === 1 ? '' : 's'}
                  </Text>}
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      <AppDialog state={dialog} onDismiss={() => setDialog(null)} />
    </View>
  );
}

const ed = StyleSheet.create({
  pickerOverlay: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(15,23,42,0.45)' },
  pickerCard: { backgroundColor: '#FFFFFF', borderTopLeftRadius: 22, borderTopRightRadius: 22, paddingHorizontal: 20, paddingTop: 18 },
  pickerHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 },
  pickerTitle: { fontSize: 18, fontWeight: '800', color: '#0F172A' },
  pickerHint: { fontSize: 13, color: '#64748B', lineHeight: 19, marginBottom: 14 },
  pickAll: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 44, paddingHorizontal: 12, borderRadius: 10, backgroundColor: '#F8FAFC', marginBottom: 10 },
  pickAllText: { flex: 1, fontSize: 13, fontWeight: '700', color: '#334155' },
  pickCount: { fontSize: 12, fontWeight: '700', color: '#0891B2' },
  pickerList: { maxHeight: 260, borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 12 },
  pickItem: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 52, paddingHorizontal: 12 },
  pickItemOn: { backgroundColor: '#ECFEFF' },
  pickItemText: { flex: 1, fontSize: 14, fontWeight: '600', color: '#0F172A' },
  pickLive: { fontSize: 10, fontWeight: '800', color: '#059669' },
  pickerErr: { fontSize: 13, color: '#DC2626', marginTop: 12, fontWeight: '600' },
  pickerBtn: { minHeight: 52, borderRadius: 14, backgroundColor: '#0891B2', alignItems: 'center', justifyContent: 'center', marginTop: 16 },
  pickerBtnOff: { opacity: 0.5 },
  pickerBtnText: { color: '#fff', fontSize: 15, fontWeight: '800' },

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
  itemPhoto: { width: 54, height: 42, borderRadius: 8, backgroundColor: '#E2E8F0' },
  itemCardOut: { backgroundColor: '#FFFBEB', borderColor: '#FDE68A' },
  itemNameOut: { textDecorationLine: 'line-through', color: '#92400E' },
  soldOutChip: {
    flexDirection: 'row', alignItems: 'center', gap: 5, alignSelf: 'flex-start',
    marginTop: 6, paddingHorizontal: 9, paddingVertical: 6, borderRadius: 20,
    backgroundColor: '#F1F5F9', minHeight: 30,
  },
  soldOutChipOn: { backgroundColor: '#FEF3C7' },
  soldOutText: { fontSize: 10.5, fontWeight: '700', color: '#64748B' },
  soldOutTextOn: { color: '#B45309' },
  aiPhotoBtn: {
    width: 54, height: 42, borderRadius: 8, backgroundColor: '#ECFEFF',
    borderWidth: 1, borderColor: '#CFFAFE', borderStyle: 'dashed',
    alignItems: 'center', justifyContent: 'center', gap: 1,
  },
  aiPhotoText: { fontSize: 8.5, fontWeight: '800', color: '#0891B2' },
  aiBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#FFF7ED',
    borderWidth: 1, borderColor: '#FED7AA', borderRadius: 14, padding: 14, marginTop: 6,
  },
  aiBannerIcon: { width: 38, height: 38, borderRadius: 11, backgroundColor: '#FFEDD5', alignItems: 'center', justifyContent: 'center' },
  aiBannerTitle: { fontSize: 13.5, fontWeight: '800', color: '#9A3412' },
  aiBannerText: { fontSize: 11.5, color: '#B45309', marginTop: 2, lineHeight: 16 },
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
  designBanner: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#F5F3FF', borderWidth: 1, borderColor: '#DDD6FE', borderRadius: 14, padding: 14, marginTop: 12 },
  designIcon: { width: 36, height: 36, borderRadius: 10, backgroundColor: '#EDE9FE', justifyContent: 'center', alignItems: 'center' },
  designTitle: { fontSize: 14, fontWeight: '700', color: '#4C1D95' },
  designText: { fontSize: 11, color: '#6D28D9', lineHeight: 16 },
  publishBar: { position: 'absolute', bottom: 0, left: 0, right: 0, backgroundColor: '#FFFFFF', borderTopWidth: 1, borderTopColor: '#E2E8F0', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingTop: 12 },
  publishInfo: { gap: 2 },
  publishCount: { fontSize: 15, fontWeight: '700', color: '#0F172A' },
  publishHint: { fontSize: 11, color: '#64748B' },
  publishActions: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  previewBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#ECFEFF', borderWidth: 1, borderColor: '#A5F3FC', paddingHorizontal: 12, paddingVertical: 11, borderRadius: 12, minHeight: 44 },
  previewBtnText: { color: '#0E7490', fontSize: 13, fontWeight: '700' },
  publishBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: '#059669', paddingHorizontal: 16, paddingVertical: 12, borderRadius: 12, minHeight: 44 },
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
