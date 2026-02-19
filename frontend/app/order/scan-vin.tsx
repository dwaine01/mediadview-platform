import React, { useState, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Alert,
  TextInput,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { Ionicons } from '@expo/vector-icons';
import { decodeVin, updateWorkOrder } from '../../src/services/api';

// Module-level lock to prevent any duplicate processing across re-renders
let MODULE_LOCK = false;
let PROCESSED_VIN: string | null = null;

export default function ScanVinScreen() {
  const { orderId } = useLocalSearchParams();
  const [permission, requestPermission] = useCameraPermissions();
  const [manualMode, setManualMode] = useState(false);
  const [manualVin, setManualVin] = useState('');
  const [status, setStatus] = useState<'scanning' | 'processing' | 'success' | 'error'>('scanning');
  const [resultMessage, setResultMessage] = useState('');

  // Reset module lock when component unmounts
  React.useEffect(() => {
    return () => {
      MODULE_LOCK = false;
      PROCESSED_VIN = null;
    };
  }, []);

  const cleanVin = (rawVin: string): string => {
    if (!rawVin) return '';
    let cleaned = rawVin.toUpperCase().replace(/[^A-Z0-9]/g, '');
    if (cleaned.length === 18) cleaned = cleaned.substring(1);
    cleaned = cleaned.replace(/I/g, '1').replace(/O/g, '0').replace(/Q/g, '0');
    return cleaned;
  };

  const processVin = async (vin: string) => {
    try {
      const vehicleData = await decodeVin(vin);
      
      await updateWorkOrder(orderId as string, {
        vehicle: {
          vin: vin,
          make: vehicleData.make || '',
          model: vehicleData.model || '',
          year: vehicleData.year || '',
          color: vehicleData.color || '',
        }
      });
      
      setResultMessage(`${vehicleData.year} ${vehicleData.make} ${vehicleData.model}\nVIN: ${vin}`);
      setStatus('success');
      
      // Auto-close after 2 seconds
      setTimeout(() => router.back(), 2000);
      
    } catch (error: any) {
      console.error('Error:', error);
      setResultMessage(error.response?.data?.detail || 'Error al procesar VIN');
      setStatus('error');
    }
  };

  const handleBarCodeScanned = ({ data }: { data: string }) => {
    // SYNCHRONOUS CHECK - before any async operations
    if (MODULE_LOCK) return;
    
    const cleanedVin = cleanVin(data);
    
    // Skip invalid or already processed VINs
    if (cleanedVin.length !== 17) return;
    if (PROCESSED_VIN === cleanedVin) return;
    
    // LOCK IMMEDIATELY - synchronously
    MODULE_LOCK = true;
    PROCESSED_VIN = cleanedVin;
    
    // Update UI
    setStatus('processing');
    
    // Process async
    processVin(cleanedVin);
  };

  const handleManualSubmit = async () => {
    if (MODULE_LOCK) return;
    
    const cleanedVin = cleanVin(manualVin);
    if (cleanedVin.length !== 17) {
      Alert.alert('Error', 'VIN debe tener 17 caracteres');
      return;
    }
    
    MODULE_LOCK = true;
    PROCESSED_VIN = cleanedVin;
    setStatus('processing');
    await processVin(cleanedVin);
  };

  const handleRetry = () => {
    MODULE_LOCK = false;
    PROCESSED_VIN = null;
    setStatus('scanning');
    setResultMessage('');
  };

  // Permission check
  if (!permission) {
    return (
      <View style={styles.container}>
        <ActivityIndicator size="large" color="#3B82F6" />
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <View style={styles.container}>
        <View style={styles.centerContent}>
          <Ionicons name="camera-outline" size={64} color="#6B7280" />
          <Text style={styles.title}>Permiso de Cámara</Text>
          <Text style={styles.subtitle}>Necesitamos la cámara para escanear</Text>
          <TouchableOpacity style={styles.primaryBtn} onPress={requestPermission}>
            <Text style={styles.primaryBtnText}>Permitir</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  // Success screen
  if (status === 'success') {
    return (
      <View style={styles.container}>
        <View style={styles.centerContent}>
          <Ionicons name="checkmark-circle" size={80} color="#10B981" />
          <Text style={[styles.title, { color: '#10B981' }]}>¡VIN Escaneado!</Text>
          <Text style={styles.resultText}>{resultMessage}</Text>
          <Text style={styles.hint}>Regresando...</Text>
        </View>
      </View>
    );
  }

  // Error screen
  if (status === 'error') {
    return (
      <View style={styles.container}>
        <View style={styles.centerContent}>
          <Ionicons name="alert-circle" size={80} color="#EF4444" />
          <Text style={[styles.title, { color: '#EF4444' }]}>Error</Text>
          <Text style={styles.resultText}>{resultMessage}</Text>
          <TouchableOpacity style={styles.primaryBtn} onPress={handleRetry}>
            <Text style={styles.primaryBtnText}>Reintentar</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.secondaryBtn} onPress={() => router.back()}>
            <Text style={styles.secondaryBtnText}>Cancelar</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  // Processing screen
  if (status === 'processing') {
    return (
      <View style={styles.container}>
        <View style={styles.centerContent}>
          <ActivityIndicator size="large" color="#3B82F6" />
          <Text style={styles.title}>Procesando VIN...</Text>
          <Text style={styles.subtitle}>Por favor espere</Text>
        </View>
      </View>
    );
  }

  // Manual mode
  if (manualMode) {
    return (
      <KeyboardAvoidingView 
        style={styles.container} 
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="arrow-back" size={24} color="#FFF" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Ingresar VIN</Text>
        </View>

        <View style={styles.formContent}>
          <Text style={styles.label}>Número VIN (17 caracteres)</Text>
          <TextInput
            style={styles.input}
            value={manualVin}
            onChangeText={setManualVin}
            placeholder="1HGBH41JXMN109186"
            placeholderTextColor="#6B7280"
            autoCapitalize="characters"
            maxLength={17}
            autoFocus
          />
          <Text style={styles.counter}>{manualVin.length}/17</Text>

          <TouchableOpacity 
            style={[styles.primaryBtn, manualVin.length !== 17 && styles.disabledBtn]}
            onPress={handleManualSubmit}
            disabled={manualVin.length !== 17}
          >
            <Text style={styles.primaryBtnText}>Confirmar</Text>
          </TouchableOpacity>

          <TouchableOpacity 
            style={styles.secondaryBtn}
            onPress={() => setManualMode(false)}
          >
            <Ionicons name="scan" size={18} color="#3B82F6" />
            <Text style={styles.secondaryBtnText}>Escanear</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    );
  }

  // Scanner screen
  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color="#FFF" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Escanear VIN</Text>
      </View>

      <View style={styles.cameraBox}>
        <CameraView
          style={StyleSheet.absoluteFill}
          facing="back"
          barcodeScannerSettings={{
            barcodeTypes: ['code39', 'code128', 'datamatrix', 'qr'],
          }}
          onBarcodeScanned={handleBarCodeScanned}
        />
        <View style={styles.scanFrame}>
          <View style={[styles.corner, styles.tl]} />
          <View style={[styles.corner, styles.tr]} />
          <View style={[styles.corner, styles.bl]} />
          <View style={[styles.corner, styles.br]} />
        </View>
      </View>

      <View style={styles.footer}>
        <Text style={styles.footerText}>Apunte al código de barras del VIN</Text>
        <TouchableOpacity style={styles.manualBtn} onPress={() => setManualMode(true)}>
          <Ionicons name="keypad" size={20} color="#FFF" />
          <Text style={styles.manualBtnText}>Manual</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#111827' },
  header: { flexDirection: 'row', alignItems: 'center', paddingTop: 50, paddingHorizontal: 16, paddingBottom: 16, backgroundColor: '#1F2937' },
  backBtn: { padding: 8 },
  headerTitle: { color: '#FFF', fontSize: 18, fontWeight: '600', marginLeft: 12 },
  centerContent: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 32 },
  title: { color: '#FFF', fontSize: 22, fontWeight: '700', marginTop: 16, textAlign: 'center' },
  subtitle: { color: '#9CA3AF', fontSize: 15, marginTop: 8, textAlign: 'center' },
  resultText: { color: '#D1D5DB', fontSize: 16, marginTop: 16, textAlign: 'center', lineHeight: 24 },
  hint: { color: '#6B7280', fontSize: 14, marginTop: 24 },
  primaryBtn: { backgroundColor: '#3B82F6', paddingHorizontal: 32, paddingVertical: 16, borderRadius: 12, marginTop: 24 },
  primaryBtnText: { color: '#FFF', fontSize: 16, fontWeight: '600' },
  secondaryBtn: { flexDirection: 'row', alignItems: 'center', marginTop: 16, padding: 12, gap: 8 },
  secondaryBtnText: { color: '#3B82F6', fontSize: 15, fontWeight: '600' },
  disabledBtn: { backgroundColor: '#374151', opacity: 0.6 },
  cameraBox: { flex: 1, backgroundColor: '#000', position: 'relative' },
  scanFrame: { position: 'absolute', top: '35%', left: '10%', right: '10%', height: 80 },
  corner: { position: 'absolute', width: 24, height: 24, borderColor: '#3B82F6' },
  tl: { top: 0, left: 0, borderTopWidth: 4, borderLeftWidth: 4, borderTopLeftRadius: 8 },
  tr: { top: 0, right: 0, borderTopWidth: 4, borderRightWidth: 4, borderTopRightRadius: 8 },
  bl: { bottom: 0, left: 0, borderBottomWidth: 4, borderLeftWidth: 4, borderBottomLeftRadius: 8 },
  br: { bottom: 0, right: 0, borderBottomWidth: 4, borderRightWidth: 4, borderBottomRightRadius: 8 },
  footer: { backgroundColor: '#1F2937', padding: 20, alignItems: 'center' },
  footerText: { color: '#9CA3AF', fontSize: 14, marginBottom: 12 },
  manualBtn: { flexDirection: 'row', backgroundColor: '#374151', paddingVertical: 14, paddingHorizontal: 24, borderRadius: 10, gap: 8 },
  manualBtnText: { color: '#FFF', fontSize: 15, fontWeight: '600' },
  formContent: { flex: 1, padding: 20 },
  label: { color: '#9CA3AF', fontSize: 14, marginBottom: 8 },
  input: { backgroundColor: '#374151', borderRadius: 10, padding: 16, color: '#FFF', fontSize: 18, letterSpacing: 2 },
  counter: { color: '#6B7280', fontSize: 12, textAlign: 'right', marginTop: 8 },
});
