import React, { useState, useRef, useEffect } from 'react';
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

export default function ScanVinScreen() {
  const { orderId } = useLocalSearchParams();
  const [permission, requestPermission] = useCameraPermissions();
  const [scanned, setScanned] = useState(false);
  const [manualMode, setManualMode] = useState(false);
  const [manualVin, setManualVin] = useState('');
  const [loading, setLoading] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const cameraRef = useRef(null);

  // Clean VIN function
  const cleanVin = (rawVin: string): string => {
    if (!rawVin) return '';
    let cleaned = rawVin.toUpperCase().replace(/[^A-Z0-9]/g, '');
    
    // If 18 chars, remove first one (scanner error)
    if (cleaned.length === 18) {
      cleaned = cleaned.substring(1);
    }
    
    // Replace invalid VIN chars
    cleaned = cleaned.replace(/I/g, '1').replace(/O/g, '0').replace(/Q/g, '0');
    
    return cleaned;
  };

  // Validate VIN
  const validateVin = (vin: string): { valid: boolean; error?: string } => {
    if (!vin || vin.length === 0) {
      return { valid: false, error: 'No se pudo leer el código' };
    }
    
    if (vin.length !== 17) {
      return { 
        valid: false, 
        error: `VIN inválido: ${vin.length} caracteres (se requieren 17)`
      };
    }

    return { valid: true };
  };

  const handleBarCodeScanned = async ({ data }: { data: string }) => {
    if (scanned || isProcessing) return;
    
    setIsProcessing(true);
    const cleanedVin = cleanVin(data);
    const validation = validateVin(cleanedVin);

    if (!validation.valid) {
      Alert.alert('Error de Escaneo', validation.error, [
        { text: 'Reintentar', onPress: () => setIsProcessing(false) },
        { text: 'Ingresar Manual', onPress: () => { setManualMode(true); setIsProcessing(false); } }
      ]);
      return;
    }

    setScanned(true);
    await processVin(cleanedVin);
  };

  const processVin = async (vin: string) => {
    setLoading(true);
    try {
      // Decode VIN
      const vehicleData = await decodeVin(vin);
      
      // Update work order with vehicle info
      await updateWorkOrder(orderId as string, {
        vehicle: {
          vin: vin,
          make: vehicleData.make || '',
          model: vehicleData.model || '',
          year: vehicleData.year || '',
          color: vehicleData.color || '',
        }
      });
      
      Alert.alert(
        '✅ VIN Escaneado',
        `Vehículo: ${vehicleData.year} ${vehicleData.make} ${vehicleData.model}\nVIN: ${vin}`,
        [{ text: 'Continuar', onPress: () => router.back() }]
      );
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'No se pudo procesar el VIN');
      setScanned(false);
      setIsProcessing(false);
    } finally {
      setLoading(false);
    }
  };

  const handleManualSubmit = async () => {
    const cleanedVin = cleanVin(manualVin);
    const validation = validateVin(cleanedVin);

    if (!validation.valid) {
      Alert.alert('Error', validation.error);
      return;
    }

    await processVin(cleanedVin);
  };

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
        <View style={styles.permissionCard}>
          <Ionicons name="camera-outline" size={64} color="#6B7280" />
          <Text style={styles.permissionTitle}>Permiso de Cámara</Text>
          <Text style={styles.permissionText}>
            Necesitamos acceso a la cámara para escanear el código VIN del vehículo
          </Text>
          <TouchableOpacity style={styles.permissionBtn} onPress={requestPermission}>
            <Text style={styles.permissionBtnText}>Permitir Cámara</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

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
          <Text style={styles.headerTitle}>Ingresar VIN Manual</Text>
        </View>

        <View style={styles.manualContent}>
          <View style={styles.vinInputCard}>
            <Text style={styles.vinInputLabel}>Número VIN (17 caracteres)</Text>
            <TextInput
              style={styles.vinInput}
              value={manualVin}
              onChangeText={setManualVin}
              placeholder="Ej: 1HGBH41JXMN109186"
              placeholderTextColor="#6B7280"
              autoCapitalize="characters"
              maxLength={17}
              autoFocus
            />
            <Text style={styles.vinCounter}>{manualVin.length}/17</Text>
          </View>

          <TouchableOpacity 
            style={[styles.submitBtn, manualVin.length !== 17 && styles.submitBtnDisabled]}
            onPress={handleManualSubmit}
            disabled={manualVin.length !== 17 || loading}
          >
            {loading ? (
              <ActivityIndicator color="#FFF" />
            ) : (
              <>
                <Ionicons name="checkmark-circle" size={22} color="#FFF" />
                <Text style={styles.submitBtnText}>Confirmar VIN</Text>
              </>
            )}
          </TouchableOpacity>

          <TouchableOpacity 
            style={styles.switchModeBtn}
            onPress={() => { setManualMode(false); setIsProcessing(false); }}
          >
            <Ionicons name="scan" size={20} color="#3B82F6" />
            <Text style={styles.switchModeText}>Volver a Escanear</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color="#FFF" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Escanear VIN del Vehículo</Text>
      </View>

      <View style={styles.cameraContainer}>
        <CameraView
          ref={cameraRef}
          style={styles.camera}
          facing="back"
          barcodeScannerSettings={{
            barcodeTypes: ['code39', 'code128', 'datamatrix', 'qr'],
          }}
          onBarcodeScanned={scanned ? undefined : handleBarCodeScanned}
        />
        
        <View style={styles.overlay}>
          <View style={styles.scanArea}>
            <View style={[styles.corner, styles.topLeft]} />
            <View style={[styles.corner, styles.topRight]} />
            <View style={[styles.corner, styles.bottomLeft]} />
            <View style={[styles.corner, styles.bottomRight]} />
          </View>
        </View>
      </View>

      <View style={styles.instructions}>
        <Ionicons name="scan-outline" size={28} color="#3B82F6" />
        <Text style={styles.instructionText}>
          Apunte la cámara al código de barras del VIN en el vehículo
        </Text>
      </View>

      <TouchableOpacity 
        style={styles.manualBtn}
        onPress={() => setManualMode(true)}
      >
        <Ionicons name="keypad" size={20} color="#FFF" />
        <Text style={styles.manualBtnText}>Ingresar Manualmente</Text>
      </TouchableOpacity>

      {loading && (
        <View style={styles.loadingOverlay}>
          <ActivityIndicator size="large" color="#3B82F6" />
          <Text style={styles.loadingText}>Procesando VIN...</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#111827',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingTop: 50,
    paddingHorizontal: 16,
    paddingBottom: 16,
    backgroundColor: '#1F2937',
  },
  backBtn: {
    padding: 8,
  },
  headerTitle: {
    color: '#FFF',
    fontSize: 18,
    fontWeight: '600',
    marginLeft: 12,
  },
  cameraContainer: {
    flex: 1,
    position: 'relative',
  },
  camera: {
    flex: 1,
  },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'center',
    alignItems: 'center',
  },
  scanArea: {
    width: 300,
    height: 100,
    position: 'relative',
  },
  corner: {
    position: 'absolute',
    width: 30,
    height: 30,
    borderColor: '#3B82F6',
  },
  topLeft: {
    top: 0,
    left: 0,
    borderTopWidth: 4,
    borderLeftWidth: 4,
    borderTopLeftRadius: 8,
  },
  topRight: {
    top: 0,
    right: 0,
    borderTopWidth: 4,
    borderRightWidth: 4,
    borderTopRightRadius: 8,
  },
  bottomLeft: {
    bottom: 0,
    left: 0,
    borderBottomWidth: 4,
    borderLeftWidth: 4,
    borderBottomLeftRadius: 8,
  },
  bottomRight: {
    bottom: 0,
    right: 0,
    borderBottomWidth: 4,
    borderRightWidth: 4,
    borderBottomRightRadius: 8,
  },
  instructions: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 20,
    backgroundColor: '#1F2937',
    gap: 12,
  },
  instructionText: {
    color: '#D1D5DB',
    fontSize: 14,
    flex: 1,
  },
  manualBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#374151',
    margin: 16,
    marginBottom: 30,
    paddingVertical: 16,
    borderRadius: 12,
    gap: 10,
  },
  manualBtnText: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '600',
  },
  permissionCard: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  permissionTitle: {
    color: '#FFF',
    fontSize: 22,
    fontWeight: '700',
    marginTop: 20,
  },
  permissionText: {
    color: '#9CA3AF',
    fontSize: 15,
    textAlign: 'center',
    marginTop: 12,
    lineHeight: 22,
  },
  permissionBtn: {
    backgroundColor: '#3B82F6',
    paddingHorizontal: 32,
    paddingVertical: 16,
    borderRadius: 12,
    marginTop: 24,
  },
  permissionBtnText: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '600',
  },
  manualContent: {
    flex: 1,
    padding: 20,
  },
  vinInputCard: {
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 20,
  },
  vinInputLabel: {
    color: '#9CA3AF',
    fontSize: 14,
    marginBottom: 12,
  },
  vinInput: {
    backgroundColor: '#374151',
    borderRadius: 10,
    padding: 16,
    color: '#FFF',
    fontSize: 18,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    letterSpacing: 2,
  },
  vinCounter: {
    color: '#6B7280',
    fontSize: 12,
    textAlign: 'right',
    marginTop: 8,
  },
  submitBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#10B981',
    marginTop: 24,
    paddingVertical: 16,
    borderRadius: 12,
    gap: 10,
  },
  submitBtnDisabled: {
    backgroundColor: '#374151',
    opacity: 0.6,
  },
  submitBtnText: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '700',
  },
  switchModeBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 20,
    paddingVertical: 14,
    gap: 8,
  },
  switchModeText: {
    color: '#3B82F6',
    fontSize: 15,
    fontWeight: '600',
  },
  loadingOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.8)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    color: '#FFF',
    marginTop: 12,
    fontSize: 16,
  },
});
