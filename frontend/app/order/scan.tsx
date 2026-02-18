import React, { useState, useRef, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { decodeVin, getVehicleByVin } from '../../src/services/api';

export default function ScanVinScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const [manualVin, setManualVin] = useState('');
  const [loading, setLoading] = useState(false);
  const [showManual, setShowManual] = useState(false);
  const [torchOn, setTorchOn] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  
  // Use ref to prevent multiple scans - more reliable than state
  const isProcessingRef = useRef(false);
  const hasNavigatedRef = useRef(false);

  // Clean VIN function - removes all non-alphanumeric characters AND invalid VIN characters
  const cleanVin = (rawVin: string): string => {
    if (!rawVin) return '';
    
    // Step 1: Remove spaces, line breaks, carriage returns, tabs, and any non-alphanumeric characters
    let cleaned = rawVin.toUpperCase().replace(/[^A-Z0-9]/g, '');
    
    // Step 2: VINs cannot contain I, O, Q - these are often misread by scanners
    // If we have exactly 18 chars and starts with I, O, or Q, remove it (common scanner error)
    if (cleaned.length === 18 && ['I', 'O', 'Q'].includes(cleaned[0])) {
      cleaned = cleaned.substring(1);
    }
    
    // Step 3: Replace common misreads in the VIN
    // Sometimes scanners read '0' as 'O' or '1' as 'I' - but since I and O are invalid,
    // if they appear, they might be correct numbers misidentified
    // Only replace if it would result in a valid 17-char VIN
    if (cleaned.length === 17) {
      // If VIN contains I, O, or Q, try to fix them
      cleaned = cleaned.replace(/I/g, '1').replace(/O/g, '0').replace(/Q/g, '0');
    }
    
    return cleaned;
  };

  // Validate VIN
  const validateVin = (vin: string): { valid: boolean; error?: string; suggestedVin?: string } => {
    if (!vin || vin.length === 0) {
      return { valid: false, error: 'No se pudo leer el código. Intente de nuevo o ingrese manualmente.' };
    }
    
    // Check for invalid characters that weren't auto-corrected
    const invalidChars = ['I', 'O', 'Q'];
    for (const char of invalidChars) {
      if (vin.includes(char)) {
        return { 
          valid: false, 
          error: `El VIN contiene el carácter inválido "${char}". Los VINs no pueden contener I, O o Q.\n\nSe ha intentado corregir automáticamente.`
        };
      }
    }
    
    if (vin.length !== 17) {
      // Try to provide helpful suggestion
      let suggestion = '';
      if (vin.length === 18) {
        suggestion = '\n\nSugerencia: El código tiene un carácter extra. Intente ingresar manualmente.';
      } else if (vin.length === 16) {
        suggestion = '\n\nSugerencia: Puede faltar un carácter. Verifique el VIN completo.';
      }
      
      return { 
        valid: false, 
        error: `VIN inválido: ${vin.length} caracteres detectados (se requieren 17).\n\nVIN leído: ${vin}${suggestion}\n\nIntente escanear de nuevo o ingrese el VIN manualmente.`
      };
    }

    return { valid: true };
  };

  const handleBarCodeScanned = useCallback(({ data }: { data: string }) => {
    // Prevent multiple scans using ref (more reliable than state)
    if (isProcessingRef.current || hasNavigatedRef.current) {
      return;
    }
    
    isProcessingRef.current = true;
    
    console.log('Raw barcode data:', JSON.stringify(data));
    console.log('Raw barcode length:', data?.length);
    
    const cleanedVin = cleanVin(data);
    console.log('Cleaned VIN:', cleanedVin);
    console.log('Cleaned VIN length:', cleanedVin.length);
    
    const validation = validateVin(cleanedVin);
    
    if (!validation.valid) {
      setScanError(validation.error || 'VIN inválido');
      // Allow scanning again after showing error
      setTimeout(() => {
        isProcessingRef.current = false;
      }, 2000); // 2 second delay before allowing another scan
      return;
    }

    // Valid VIN - process it
    setScanError(null);
    processVin(cleanedVin);
  }, []);

  const processVin = async (vin: string) => {
    if (hasNavigatedRef.current) return;
    
    setLoading(true);
    try {
      // Check if vehicle already exists
      const existingVehicle = await getVehicleByVin(vin);
      
      hasNavigatedRef.current = true;
      
      if (existingVehicle) {
        // Vehicle exists, go to create order with existing vehicle
        router.replace({
          pathname: '/order/new',
          params: {
            vehicleId: existingVehicle.id,
            clientId: existingVehicle.client_id,
            vehicleData: JSON.stringify(existingVehicle),
          },
        });
      } else {
        // New vehicle, decode VIN
        const vinData = await decodeVin(vin);
        router.replace({
          pathname: '/order/select-client',
          params: {
            vinData: JSON.stringify(vinData),
          },
        });
      }
    } catch (error: any) {
      hasNavigatedRef.current = false;
      const message = error.response?.data?.detail || 'Error al procesar VIN';
      Alert.alert('Error', message);
      isProcessingRef.current = false;
    } finally {
      setLoading(false);
    }
  };

  const handleManualSubmit = () => {
    if (isProcessingRef.current || hasNavigatedRef.current) return;
    
    const cleanedVin = cleanVin(manualVin);
    const validation = validateVin(cleanedVin);
    
    if (!validation.valid) {
      Alert.alert('Error', validation.error || 'VIN inválido');
      return;
    }
    
    isProcessingRef.current = true;
    processVin(cleanedVin);
  };

  const dismissError = () => {
    setScanError(null);
    isProcessingRef.current = false;
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
        <Ionicons name="camera-outline" size={64} color="#4B5563" />
        <Text style={styles.permissionText}>Se requiere permiso de cámara</Text>
        <Text style={styles.permissionSubtext}>
          Para escanear el código VIN del vehículo
        </Text>
        <TouchableOpacity style={styles.permissionButton} onPress={requestPermission}>
          <Text style={styles.permissionButtonText}>Permitir Cámara</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.manualButton}
          onPress={() => setShowManual(true)}
        >
          <Text style={styles.manualButtonText}>Ingresar VIN manualmente</Text>
        </TouchableOpacity>
      </View>
    );
  }

  if (showManual) {
    return (
      <View style={styles.manualContainer}>
        <View style={styles.manualHeader}>
          <TouchableOpacity onPress={() => setShowManual(false)}>
            <Ionicons name="arrow-back" size={24} color="#FFFFFF" />
          </TouchableOpacity>
          <Text style={styles.manualTitle}>Ingresar VIN</Text>
          <View style={{ width: 24 }} />
        </View>

        <View style={styles.manualContent}>
          <Text style={styles.manualLabel}>Número VIN (17 caracteres)</Text>
          <TextInput
            style={styles.manualInput}
            placeholder="Ej: 1HGBH41JXMN109186"
            placeholderTextColor="#6B7280"
            value={manualVin}
            onChangeText={(text) => setManualVin(text.toUpperCase().replace(/[^A-Z0-9]/g, ''))}
            autoCapitalize="characters"
            maxLength={17}
            autoFocus
          />
          <Text style={styles.charCount}>{manualVin.length}/17</Text>

          <TouchableOpacity
            style={[
              styles.submitButton,
              (manualVin.length !== 17 || loading) && styles.submitButtonDisabled,
            ]}
            onPress={handleManualSubmit}
            disabled={manualVin.length !== 17 || loading}
          >
            {loading ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.submitButtonText}>Continuar</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <CameraView
        style={styles.camera}
        onBarcodeScanned={handleBarCodeScanned}
        barcodeScannerSettings={{
          barcodeTypes: ['code39', 'code128', 'pdf417', 'datamatrix', 'qr'],
        }}
        enableTorch={torchOn}
      >
        <View style={styles.overlay}>
          <View style={styles.scanArea}>
            <View style={styles.cornerTL} />
            <View style={styles.cornerTR} />
            <View style={styles.cornerBL} />
            <View style={styles.cornerBR} />
          </View>
        </View>

        <View style={styles.instructions}>
          <Ionicons name="scan" size={24} color="#FFFFFF" />
          <Text style={styles.instructionText}>
            Apunta al código de barras VIN
          </Text>
          <Text style={styles.instructionSubtext}>
            Usualmente en el tablero o puerta del conductor
          </Text>
        </View>

        <View style={styles.controls}>
          <TouchableOpacity
            style={styles.controlButton}
            onPress={() => setTorchOn(!torchOn)}
          >
            <Ionicons
              name={torchOn ? 'flash' : 'flash-outline'}
              size={28}
              color="#FFFFFF"
            />
            <Text style={styles.controlText}>Linterna</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.controlButton}
            onPress={() => setShowManual(true)}
          >
            <Ionicons name="keypad" size={28} color="#FFFFFF" />
            <Text style={styles.controlText}>Manual</Text>
          </TouchableOpacity>
        </View>

        {/* Error overlay */}
        {scanError && (
          <View style={styles.errorOverlay}>
            <View style={styles.errorCard}>
              <Ionicons name="alert-circle" size={48} color="#EF4444" />
              <Text style={styles.errorTitle}>Error de Escaneo</Text>
              <Text style={styles.errorText}>{scanError}</Text>
              <View style={styles.errorButtons}>
                <TouchableOpacity style={styles.retryButton} onPress={dismissError}>
                  <Ionicons name="refresh" size={20} color="#FFFFFF" />
                  <Text style={styles.retryButtonText}>Reintentar</Text>
                </TouchableOpacity>
                <TouchableOpacity 
                  style={styles.manualEntryButton} 
                  onPress={() => {
                    dismissError();
                    setShowManual(true);
                  }}
                >
                  <Ionicons name="keypad" size={20} color="#3B82F6" />
                  <Text style={styles.manualEntryButtonText}>Manual</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        )}

        {/* Loading overlay */}
        {loading && (
          <View style={styles.loadingOverlay}>
            <ActivityIndicator size="large" color="#3B82F6" />
            <Text style={styles.loadingText}>Procesando VIN...</Text>
          </View>
        )}
      </CameraView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#111827',
    justifyContent: 'center',
    alignItems: 'center',
  },
  camera: {
    flex: 1,
    width: '100%',
  },
  overlay: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.5)',
  },
  scanArea: {
    width: 300,
    height: 100,
    backgroundColor: 'transparent',
    borderWidth: 0,
    position: 'relative',
  },
  cornerTL: {
    position: 'absolute',
    top: 0,
    left: 0,
    width: 30,
    height: 30,
    borderTopWidth: 3,
    borderLeftWidth: 3,
    borderColor: '#3B82F6',
  },
  cornerTR: {
    position: 'absolute',
    top: 0,
    right: 0,
    width: 30,
    height: 30,
    borderTopWidth: 3,
    borderRightWidth: 3,
    borderColor: '#3B82F6',
  },
  cornerBL: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    width: 30,
    height: 30,
    borderBottomWidth: 3,
    borderLeftWidth: 3,
    borderColor: '#3B82F6',
  },
  cornerBR: {
    position: 'absolute',
    bottom: 0,
    right: 0,
    width: 30,
    height: 30,
    borderBottomWidth: 3,
    borderRightWidth: 3,
    borderColor: '#3B82F6',
  },
  instructions: {
    position: 'absolute',
    top: 60,
    left: 0,
    right: 0,
    alignItems: 'center',
    padding: 20,
  },
  instructionText: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
    marginTop: 12,
  },
  instructionSubtext: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.7)',
    marginTop: 4,
  },
  controls: {
    position: 'absolute',
    bottom: 60,
    left: 0,
    right: 0,
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 40,
  },
  controlButton: {
    alignItems: 'center',
    padding: 16,
  },
  controlText: {
    fontSize: 12,
    color: '#FFFFFF',
    marginTop: 4,
  },
  loadingOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.8)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    fontSize: 16,
    color: '#FFFFFF',
    marginTop: 16,
  },
  errorOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.9)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  errorCard: {
    backgroundColor: '#1F2937',
    borderRadius: 16,
    padding: 24,
    alignItems: 'center',
    maxWidth: 320,
    width: '100%',
  },
  errorTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#FFFFFF',
    marginTop: 16,
    marginBottom: 8,
  },
  errorText: {
    fontSize: 14,
    color: '#9CA3AF',
    textAlign: 'center',
    lineHeight: 22,
  },
  errorButtons: {
    flexDirection: 'row',
    marginTop: 24,
    gap: 12,
  },
  retryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#3B82F6',
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: 10,
    gap: 8,
  },
  retryButtonText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '600',
  },
  manualEntryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: '#3B82F6',
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: 10,
    gap: 8,
  },
  manualEntryButtonText: {
    color: '#3B82F6',
    fontSize: 15,
    fontWeight: '600',
  },
  permissionText: {
    fontSize: 20,
    fontWeight: '600',
    color: '#FFFFFF',
    marginTop: 24,
  },
  permissionSubtext: {
    fontSize: 14,
    color: '#9CA3AF',
    marginTop: 8,
    textAlign: 'center',
    paddingHorizontal: 40,
  },
  permissionButton: {
    backgroundColor: '#3B82F6',
    paddingHorizontal: 32,
    paddingVertical: 16,
    borderRadius: 12,
    marginTop: 32,
  },
  permissionButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  manualButton: {
    marginTop: 16,
    padding: 12,
  },
  manualButtonText: {
    fontSize: 14,
    color: '#3B82F6',
  },
  manualContainer: {
    flex: 1,
    backgroundColor: '#111827',
  },
  manualHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 20,
    paddingTop: 60,
    backgroundColor: '#1F2937',
  },
  manualTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  manualContent: {
    padding: 20,
  },
  manualLabel: {
    fontSize: 14,
    color: '#9CA3AF',
    marginBottom: 12,
  },
  manualInput: {
    backgroundColor: '#1F2937',
    borderRadius: 12,
    paddingHorizontal: 16,
    height: 56,
    color: '#FFFFFF',
    fontSize: 20,
    letterSpacing: 2,
    fontWeight: '600',
    borderWidth: 1,
    borderColor: '#374151',
  },
  charCount: {
    fontSize: 14,
    color: '#6B7280',
    textAlign: 'right',
    marginTop: 8,
  },
  submitButton: {
    backgroundColor: '#3B82F6',
    borderRadius: 12,
    height: 56,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 24,
  },
  submitButtonDisabled: {
    backgroundColor: '#374151',
  },
  submitButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
});
