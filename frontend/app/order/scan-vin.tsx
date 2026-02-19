import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { Ionicons } from '@expo/vector-icons';
import { decodeVin, updateWorkOrder } from '../../src/services/api';

export default function ScanVinScreen() {
  const { orderId } = useLocalSearchParams();
  const [permission, requestPermission] = useCameraPermissions();
  const [manualMode, setManualMode] = useState(false);
  const [manualVin, setManualVin] = useState('');
  const [showCamera, setShowCamera] = useState(true);
  const [status, setStatus] = useState<'idle' | 'processing' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');
  
  // Collected VINs for debounce
  const [collectedVin, setCollectedVin] = useState<string | null>(null);

  // Process VIN after debounce
  useEffect(() => {
    if (!collectedVin || status !== 'idle') return;
    
    // Small delay to collect all rapid-fire events
    const timer = setTimeout(() => {
      processVinOnce(collectedVin);
    }, 300);
    
    return () => clearTimeout(timer);
  }, [collectedVin]);

  const cleanVin = (rawVin: string): string => {
    if (!rawVin) return '';
    let cleaned = rawVin.toUpperCase().replace(/[^A-Z0-9]/g, '');
    if (cleaned.length === 18) cleaned = cleaned.substring(1);
    return cleaned.replace(/I/g, '1').replace(/O/g, '0').replace(/Q/g, '0');
  };

  const processVinOnce = async (vin: string) => {
    if (status !== 'idle') return; // Extra safety check
    
    setStatus('processing');
    setShowCamera(false);
    
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
      
      setMessage(`${vehicleData.year} ${vehicleData.make} ${vehicleData.model}\nVIN: ${vin}`);
      setStatus('success');
      
      // Auto return after 2 seconds
      setTimeout(() => router.back(), 2000);
      
    } catch (error: any) {
      setMessage('No se pudo actualizar la orden');
      setStatus('error');
    }
  };

  const handleBarCodeScanned = ({ data }: { data: string }) => {
    // If already processing or done, ignore completely
    if (status !== 'idle') return;
    
    const vin = cleanVin(data);
    if (vin.length !== 17) return;
    
    // Just collect the VIN, useEffect will process it after debounce
    if (!collectedVin) {
      setShowCamera(false); // Hide camera immediately
      setCollectedVin(vin);
    }
  };

  const handleManualSubmit = () => {
    if (status !== 'idle') return;
    
    const vin = cleanVin(manualVin);
    if (vin.length !== 17) return;
    
    setCollectedVin(vin);
  };

  const retry = () => {
    setStatus('idle');
    setCollectedVin(null);
    setMessage('');
    setShowCamera(true);
  };

  // Loading permission
  if (!permission) {
    return <View style={s.container}><ActivityIndicator size="large" color="#3B82F6" /></View>;
  }

  // Need permission
  if (!permission.granted) {
    return (
      <View style={s.container}>
        <View style={s.center}>
          <Ionicons name="camera" size={64} color="#6B7280" />
          <Text style={s.title}>Permiso de Cámara</Text>
          <TouchableOpacity style={s.btn} onPress={requestPermission}>
            <Text style={s.btnText}>Permitir</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  // Success
  if (status === 'success') {
    return (
      <View style={s.container}>
        <View style={s.center}>
          <Ionicons name="checkmark-circle" size={80} color="#10B981" />
          <Text style={[s.title, {color: '#10B981'}]}>¡Listo!</Text>
          <Text style={s.msg}>{message}</Text>
        </View>
      </View>
    );
  }

  // Error
  if (status === 'error') {
    return (
      <View style={s.container}>
        <View style={s.center}>
          <Ionicons name="close-circle" size={80} color="#EF4444" />
          <Text style={[s.title, {color: '#EF4444'}]}>Error</Text>
          <Text style={s.msg}>{message}</Text>
          <TouchableOpacity style={s.btn} onPress={retry}>
            <Text style={s.btnText}>Reintentar</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.link} onPress={() => router.back()}>
            <Text style={s.linkText}>Cancelar</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  // Processing
  if (status === 'processing') {
    return (
      <View style={s.container}>
        <View style={s.center}>
          <ActivityIndicator size="large" color="#3B82F6" />
          <Text style={s.title}>Procesando...</Text>
        </View>
      </View>
    );
  }

  // Manual input
  if (manualMode) {
    return (
      <KeyboardAvoidingView style={s.container} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        <View style={s.header}>
          <TouchableOpacity onPress={() => router.back()}><Ionicons name="arrow-back" size={24} color="#FFF" /></TouchableOpacity>
          <Text style={s.headerText}>Ingresar VIN</Text>
        </View>
        <View style={s.form}>
          <TextInput
            style={s.input}
            value={manualVin}
            onChangeText={setManualVin}
            placeholder="17 caracteres"
            placeholderTextColor="#666"
            autoCapitalize="characters"
            maxLength={17}
            autoFocus
          />
          <Text style={s.counter}>{manualVin.length}/17</Text>
          <TouchableOpacity 
            style={[s.btn, manualVin.length !== 17 && s.btnOff]} 
            onPress={handleManualSubmit}
            disabled={manualVin.length !== 17}
          >
            <Text style={s.btnText}>Confirmar</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.link} onPress={() => setManualMode(false)}>
            <Text style={s.linkText}>Escanear</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    );
  }

  // Scanner
  return (
    <View style={s.container}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()}><Ionicons name="arrow-back" size={24} color="#FFF" /></TouchableOpacity>
        <Text style={s.headerText}>Escanear VIN</Text>
      </View>
      
      <View style={s.cam}>
        {showCamera && (
          <CameraView
            style={StyleSheet.absoluteFill}
            facing="back"
            barcodeScannerSettings={{ barcodeTypes: ['code39', 'code128', 'datamatrix', 'qr'] }}
            onBarcodeScanned={handleBarCodeScanned}
          />
        )}
        {!showCamera && (
          <View style={s.center}>
            <ActivityIndicator size="large" color="#3B82F6" />
          </View>
        )}
        {showCamera && (
          <View style={s.frame}>
            <View style={[s.c, s.tl]} />
            <View style={[s.c, s.tr]} />
            <View style={[s.c, s.bl]} />
            <View style={[s.c, s.br]} />
          </View>
        )}
      </View>
      
      <TouchableOpacity style={s.manualBtn} onPress={() => setManualMode(true)}>
        <Text style={s.manualText}>Ingresar Manual</Text>
      </TouchableOpacity>
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#111827' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 32 },
  header: { flexDirection: 'row', alignItems: 'center', paddingTop: 50, paddingHorizontal: 16, paddingBottom: 16, backgroundColor: '#1F2937', gap: 12 },
  headerText: { color: '#FFF', fontSize: 18, fontWeight: '600' },
  title: { color: '#FFF', fontSize: 22, fontWeight: '700', marginTop: 16 },
  msg: { color: '#9CA3AF', fontSize: 15, marginTop: 12, textAlign: 'center', lineHeight: 22 },
  btn: { backgroundColor: '#3B82F6', paddingHorizontal: 32, paddingVertical: 14, borderRadius: 10, marginTop: 24 },
  btnOff: { backgroundColor: '#374151', opacity: 0.5 },
  btnText: { color: '#FFF', fontSize: 16, fontWeight: '600' },
  link: { marginTop: 16, padding: 12 },
  linkText: { color: '#3B82F6', fontSize: 15 },
  cam: { flex: 1, backgroundColor: '#000' },
  frame: { position: 'absolute', top: '35%', left: '10%', right: '10%', height: 80 },
  c: { position: 'absolute', width: 20, height: 20, borderColor: '#3B82F6' },
  tl: { top: 0, left: 0, borderTopWidth: 3, borderLeftWidth: 3 },
  tr: { top: 0, right: 0, borderTopWidth: 3, borderRightWidth: 3 },
  bl: { bottom: 0, left: 0, borderBottomWidth: 3, borderLeftWidth: 3 },
  br: { bottom: 0, right: 0, borderBottomWidth: 3, borderRightWidth: 3 },
  manualBtn: { backgroundColor: '#374151', margin: 16, padding: 16, borderRadius: 10, alignItems: 'center' },
  manualText: { color: '#FFF', fontSize: 15, fontWeight: '600' },
  form: { flex: 1, padding: 20 },
  input: { backgroundColor: '#374151', borderRadius: 10, padding: 16, color: '#FFF', fontSize: 18, letterSpacing: 2 },
  counter: { color: '#666', fontSize: 12, textAlign: 'right', marginTop: 8 },
});
