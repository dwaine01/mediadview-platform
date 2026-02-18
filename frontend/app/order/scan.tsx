import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  Alert,
  ActivityIndicator,
  Platform,
} from 'react-native';
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { decodeVin, getVehicleByVin } from '../../src/services/api';
import { VinDecodeResult } from '../../src/types';

export default function ScanVinScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const [scanned, setScanned] = useState(false);
  const [manualVin, setManualVin] = useState('');
  const [loading, setLoading] = useState(false);
  const [showManual, setShowManual] = useState(false);
  const [torchOn, setTorchOn] = useState(false);

  const handleBarCodeScanned = async ({ data }: { data: string }) => {
    if (scanned || loading) return;
    setScanned(true);
    await processVin(data);
  };

  const processVin = async (vin: string) => {
    vin = vin.toUpperCase().trim();
    
    // Basic validation
    if (vin.length !== 17) {
      Alert.alert('Error', 'El VIN debe tener 17 caracteres');
      setScanned(false);
      return;
    }

    const invalidChars = ['I', 'O', 'Q'];
    for (const char of invalidChars) {
      if (vin.includes(char)) {
        Alert.alert('Error', `El VIN no puede contener la letra "${char}"`);
        setScanned(false);
        return;
      }
    }

    setLoading(true);
    try {
      // Check if vehicle already exists
      const existingVehicle = await getVehicleByVin(vin);
      
      if (existingVehicle) {
        // Vehicle exists, go to create order with existing vehicle
        router.push({
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
        router.push({
          pathname: '/order/select-client',
          params: {
            vinData: JSON.stringify(vinData),
          },
        });
      }
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Error al procesar VIN';
      Alert.alert('Error', message);
      setScanned(false);
    } finally {
      setLoading(false);
    }
  };

  const handleManualSubmit = () => {
    if (manualVin.trim()) {
      processVin(manualVin);
    }
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
            onChangeText={(text) => setManualVin(text.toUpperCase())}
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
        onBarcodeScanned={scanned ? undefined : handleBarCodeScanned}
        barcodeScannerSettings={{
          barcodeTypes: ['code39', 'code128', 'pdf417', 'datamatrix'],
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
