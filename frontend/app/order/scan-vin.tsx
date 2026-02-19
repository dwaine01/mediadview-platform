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
  const [manualMode, setManualMode] = useState(false);
  const [manualVin, setManualVin] = useState('');
  const [loading, setLoading] = useState(false);
  const [cameraActive, setCameraActive] = useState(true);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  
  // Global lock - once set, nothing else can process
  const lockRef = useRef(false);
  const lastVinRef = useRef<string | null>(null);
  const alertShownRef = useRef(false);

  // Clean VIN function
  const cleanVin = (rawVin: string): string => {
    if (!rawVin) return '';
    let cleaned = rawVin.toUpperCase().replace(/[^A-Z0-9]/g, '');
    
    if (cleaned.length === 18) {
      cleaned = cleaned.substring(1);
    }
    
    cleaned = cleaned.replace(/I/g, '1').replace(/O/g, '0').replace(/Q/g, '0');
    
    return cleaned;
  };

  const validateVin = (vin: string): boolean => {
    return vin && vin.length === 17;
  };

  const showSuccessAndGoBack = (vehicleInfo: string, vin: string) => {
    if (alertShownRef.current) return;
    alertShownRef.current = true;
    
    setSuccessMessage(`${vehicleInfo}\nVIN: ${vin}`);
    
    // Auto navigate back after 2 seconds
    setTimeout(() => {
      router.back();
    }, 2000);
  };

  const showError = (message: string) => {
    if (alertShownRef.current) return;
    alertShownRef.current = true;
    
    Alert.alert('Error', message, [
      {
        text: 'Reintentar',
        onPress: () => {
          alertShownRef.current = false;
          lockRef.current = false;
          lastVinRef.current = null;
          setCameraActive(true);
        }
      },
      {
        text: 'Manual',
        onPress: () => {
          alertShownRef.current = false;
          lockRef.current = false;
          setManualMode(true);
        }
      }
    ]);
  };

  const processVin = async (vin: string) => {
    setLoading(true);
    setCameraActive(false);
    
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
      
      const vehicleInfo = `${vehicleData.year} ${vehicleData.make} ${vehicleData.model}`;
      showSuccessAndGoBack(vehicleInfo, vin);
      
    } catch (error: any) {
      console.error('Error processing VIN:', error);
      setLoading(false);
      showError(error.response?.data?.detail || 'No se pudo procesar el VIN');
    }
  };

  const handleBarCodeScanned = ({ data }: { data: string }) => {
    // IMMEDIATE lock check - if locked, do absolutely nothing
    if (lockRef.current) {
      return;
    }
    
    const cleanedVin = cleanVin(data);
    
    // Check if same VIN was already processed
    if (lastVinRef.current === cleanedVin) {
      return;
    }
    
    // Validate VIN
    if (!validateVin(cleanedVin)) {
      return; // Silently ignore invalid VINs
    }
    
    // LOCK immediately - before any async operation
    lockRef.current = true;
    lastVinRef.current = cleanedVin;
    
    // Process the VIN
    processVin(cleanedVin);
  };

  const handleManualSubmit = async () => {
    if (lockRef.current) return;
    
    const cleanedVin = cleanVin(manualVin);
    
    if (!validateVin(cleanedVin)) {
      Alert.alert('Error', 'VIN debe tener 17 caracteres');
      return;
    }
    
    lockRef.current = true;
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
            Necesitamos acceso a la cámara para escanear el VIN
          </Text>
          <TouchableOpacity style={styles.permissionBtn} onPress={requestPermission}>
            <Text style={styles.permissionBtnText}>Permitir Cámara</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  // Success screen
  if (successMessage) {
    return (
      <View style={styles.container}>
        <View style={styles.successCard}>
          <View style={styles.successIcon}>
            <Ionicons name="checkmark-circle" size={80} color="#10B981" />
          </View>
          <Text style={styles.successTitle}>¡VIN Escaneado!</Text>
          <Text style={styles.successText}>{successMessage}</Text>
          <Text style={styles.successHint}>Regresando...</Text>
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
            style={[styles.submitBtn, (manualVin.length !== 17 || loading) && styles.submitBtnDisabled]}
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
            onPress={() => {
              lockRef.current = false;
              alertShownRef.current = false;
              setManualMode(false);
              setCameraActive(true);
            }}
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
        <Text style={styles.headerTitle}>Escanear VIN</Text>
      </View>

      <View style={styles.cameraContainer}>
        {cameraActive && !loading && (
          <CameraView
            style={styles.camera}
            facing="back"
            barcodeScannerSettings={{
              barcodeTypes: ['code39', 'code128', 'datamatrix', 'qr'],
            }}
            onBarcodeScanned={handleBarCodeScanned}
          />
        )}
        
        {loading && (
          <View style={styles.processingOverlay}>
            <ActivityIndicator size="large" color="#3B82F6" />
            <Text style={styles.processingText}>Procesando VIN...</Text>
          </View>
        )}
        
        {cameraActive && !loading && (
          <View style={styles.overlay}>
            <View style={styles.scanArea}>
              <View style={[styles.corner, styles.topLeft]} />
              <View style={[styles.corner, styles.topRight]} />
              <View style={[styles.corner, styles.bottomLeft]} />
              <View style={[styles.corner, styles.bottomRight]} />
            </View>
            <Text style={styles.scanHint}>Apunte al código de barras</Text>
          </View>
        )}
      </View>

      <TouchableOpacity 
        style={styles.manualBtn}
        onPress={() => setManualMode(true)}
        disabled={loading}
      >
        <Ionicons name="keypad" size={20} color="#FFF" />
        <Text style={styles.manualBtnText}>Ingresar Manualmente</Text>
      </TouchableOpacity>
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
    backgroundColor: '#000',
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
    width: 280,
    height: 80,
    position: 'relative',
  },
  scanHint: {
    color: '#FFF',
    fontSize: 14,
    marginTop: 20,
    textAlign: 'center',
  },
  corner: {
    position: 'absolute',
    width: 25,
    height: 25,
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
  processingOverlay: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#111827',
  },
  processingText: {
    color: '#FFF',
    fontSize: 16,
    marginTop: 16,
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
  successCard: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  successIcon: {
    marginBottom: 20,
  },
  successTitle: {
    color: '#10B981',
    fontSize: 24,
    fontWeight: '700',
    marginBottom: 16,
  },
  successText: {
    color: '#FFF',
    fontSize: 16,
    textAlign: 'center',
    lineHeight: 24,
  },
  successHint: {
    color: '#6B7280',
    fontSize: 14,
    marginTop: 24,
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
});
