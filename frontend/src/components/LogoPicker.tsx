import React, { useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Image, Alert, Linking, Platform } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { Ionicons } from '@expo/vector-icons';

export type PickedLogo = { filename: string; base64: string; previewUri: string };

type Props = {
  /** Already-saved logo URL (absolute), shown when nothing new is picked. */
  currentUrl?: string | null;
  picked?: PickedLogo | null;
  onPicked: (logo: PickedLogo | null) => void;
  label?: string;
  hint?: string;
  compact?: boolean;
};

const C = {
  border: '#E2E8F0',
  text: '#0F172A',
  body: '#475569',
  muted: '#64748B',
  brand: '#0891B2',
  brandBg: '#ECFEFF',
  red: '#DC2626',
};

const MAX_BYTES = 2 * 1024 * 1024;

/**
 * Business-logo picker used at signup and in workspace settings.
 * Asks for library permission only after the user taps, and offers Settings
 * if the permission was permanently denied.
 */
export default function LogoPicker({
  currentUrl, picked, onPicked, label = 'Logo del negocio', hint, compact,
}: Props) {
  const [blocked, setBlocked] = useState(false);
  const [busy, setBusy] = useState(false);

  const pick = useCallback(async () => {
    setBusy(true);
    try {
      if (Platform.OS !== 'web') {
        const current = await ImagePicker.getMediaLibraryPermissionsAsync();
        let status = current.status;
        let canAskAgain = current.canAskAgain;

        if (status !== 'granted' && canAskAgain) {
          const asked = await ImagePicker.requestMediaLibraryPermissionsAsync();
          status = asked.status;
          canAskAgain = asked.canAskAgain;
        }
        if (status !== 'granted') {
          setBlocked(!canAskAgain);
          if (!canAskAgain) {
            Alert.alert(
              'Permiso necesario',
              'Para subir tu logo necesitamos acceso a tus fotos. Puedes activarlo en Ajustes.',
              [{ text: 'Cancelar', style: 'cancel' }, { text: 'Abrir Ajustes', onPress: () => Linking.openSettings() }],
            );
          }
          return;
        }
        setBlocked(false);
      }

      const res = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        base64: true,
        quality: 0.9,
        allowsEditing: false,
      });
      if (res.canceled || !res.assets?.length) return;

      const asset = res.assets[0];
      if (!asset.base64) {
        Alert.alert('No se pudo leer la imagen', 'Intenta con otro archivo.');
        return;
      }
      if (asset.fileSize && asset.fileSize > MAX_BYTES) {
        Alert.alert('Imagen muy grande', 'El logo debe pesar menos de 2 MB.');
        return;
      }
      const name = asset.fileName || `logo.${(asset.mimeType || 'image/png').split('/')[1] || 'png'}`;
      onPicked({ filename: name, base64: asset.base64, previewUri: asset.uri });
    } finally {
      setBusy(false);
    }
  }, [onPicked]);

  const preview = picked?.previewUri || currentUrl || null;

  return (
    <View style={compact ? undefined : lp.wrap}>
      <Text style={lp.label}>{label}</Text>
      <View style={lp.row}>
        <View style={lp.box}>
          {preview
            ? <Image source={{ uri: preview }} style={lp.img} resizeMode="contain" />
            : <Ionicons name="image-outline" size={22} color="#94A3B8" />}
        </View>
        <View style={{ gap: 8, alignItems: 'flex-start' }}>
          <TouchableOpacity style={lp.btn} onPress={pick} disabled={busy} activeOpacity={0.8}>
            <Ionicons name="cloud-upload-outline" size={16} color={C.brand} />
            <Text style={lp.btnText}>{preview ? 'Cambiar logo' : 'Subir logo'}</Text>
          </TouchableOpacity>
          {!!preview && (
            <TouchableOpacity onPress={() => onPicked(null)} activeOpacity={0.7}>
              <Text style={lp.remove}>Quitar</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>
      <Text style={lp.hint}>
        {hint || 'PNG, JPG, WEBP o SVG · máximo 2 MB. Aparecerá en la esquina de tu panel.'}
      </Text>
      {blocked && (
        <TouchableOpacity onPress={() => Linking.openSettings()} activeOpacity={0.7}>
          <Text style={lp.settings}>Abrir Ajustes para permitir el acceso a fotos →</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const lp = StyleSheet.create({
  wrap: { marginBottom: 18 },
  label: { fontSize: 11, fontWeight: '800', color: C.muted, letterSpacing: 1.1, marginBottom: 8 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  box: {
    width: 76, height: 76, borderRadius: 14, backgroundColor: '#FFFFFF',
    borderWidth: 1, borderColor: C.border, alignItems: 'center', justifyContent: 'center',
    overflow: 'hidden', padding: 8,
  },
  img: { width: '100%', height: '100%' },
  btn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7,
    backgroundColor: C.brandBg, borderWidth: 1, borderColor: '#A5F3FC',
    borderRadius: 10, paddingVertical: 11, paddingHorizontal: 18, minHeight: 44, minWidth: 160,
  },
  btnText: { fontSize: 13.5, fontWeight: '700', color: C.brand },
  remove: { fontSize: 12.5, color: C.red, fontWeight: '600' },
  hint: { fontSize: 11.5, color: C.muted, marginTop: 9, lineHeight: 17 },
  settings: { fontSize: 12.5, color: C.brand, fontWeight: '700', marginTop: 8 },
});
