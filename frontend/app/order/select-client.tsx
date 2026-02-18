import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  FlatList,
  TextInput,
  Alert,
  Modal,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getClients, createClient, createVehicle } from '../../src/services/api';
import { Client, VinDecodeResult } from '../../src/types';

export default function SelectClientScreen() {
  const params = useLocalSearchParams();
  const vinData: VinDecodeResult = params.vinData ? JSON.parse(params.vinData as string) : null;
  
  const [clients, setClients] = useState<Client[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [newClient, setNewClient] = useState({
    name: '',
    phone: '',
    email: '',
  });

  useEffect(() => {
    loadClients();
  }, []);

  const loadClients = async (search?: string) => {
    try {
      const data = await getClients(search);
      setClients(data);
    } catch (error) {
      console.error('Error loading clients:', error);
    }
  };

  const handleSearch = () => {
    loadClients(searchQuery);
  };

  const handleSelectClient = async (client: Client) => {
    setLoading(true);
    try {
      // Create vehicle for this client
      const vehicle = await createVehicle({
        client_id: client.id,
        vin: vinData.vin,
        make: vinData.make,
        model: vinData.model,
        year: vinData.year,
        trim: vinData.trim,
        body_type: vinData.body_type,
        engine: vinData.engine,
      });

      router.push({
        pathname: '/order/new',
        params: {
          vehicleId: vehicle.id,
          clientId: client.id,
          vehicleData: JSON.stringify(vehicle),
        },
      });
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Error al crear vehículo');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateClient = async () => {
    if (!newClient.name.trim()) {
      Alert.alert('Error', 'El nombre es requerido');
      return;
    }

    setLoading(true);
    try {
      const client = await createClient(newClient);
      
      // Create vehicle for new client
      const vehicle = await createVehicle({
        client_id: client.id,
        vin: vinData.vin,
        make: vinData.make,
        model: vinData.model,
        year: vinData.year,
        trim: vinData.trim,
        body_type: vinData.body_type,
        engine: vinData.engine,
      });

      setModalVisible(false);
      router.push({
        pathname: '/order/new',
        params: {
          vehicleId: vehicle.id,
          clientId: client.id,
          vehicleData: JSON.stringify(vehicle),
        },
      });
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Error al crear cliente');
    } finally {
      setLoading(false);
    }
  };

  const renderClient = ({ item }: { item: Client }) => (
    <TouchableOpacity
      style={styles.clientCard}
      onPress={() => handleSelectClient(item)}
      disabled={loading}
    >
      <View style={styles.avatar}>
        <Text style={styles.avatarText}>{item.name.charAt(0).toUpperCase()}</Text>
      </View>
      <View style={styles.clientInfo}>
        <Text style={styles.clientName}>{item.name}</Text>
        {item.phone && <Text style={styles.clientDetail}>{item.phone}</Text>}
        {item.email && <Text style={styles.clientDetail}>{item.email}</Text>}
      </View>
      <Ionicons name="chevron-forward" size={20} color="#6B7280" />
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      {/* Vehicle Info */}
      {vinData && (
        <View style={styles.vehicleInfo}>
          <Ionicons name="car" size={24} color="#3B82F6" />
          <View style={styles.vehicleDetails}>
            <Text style={styles.vehicleTitle}>
              {vinData.year} {vinData.make} {vinData.model}
            </Text>
            <Text style={styles.vehicleVin}>VIN: {vinData.vin}</Text>
          </View>
        </View>
      )}

      <Text style={styles.sectionTitle}>Seleccionar Cliente</Text>

      {/* Search */}
      <View style={styles.searchContainer}>
        <View style={styles.searchInputContainer}>
          <Ionicons name="search" size={20} color="#6B7280" />
          <TextInput
            style={styles.searchInput}
            placeholder="Buscar por nombre o teléfono"
            placeholderTextColor="#6B7280"
            value={searchQuery}
            onChangeText={setSearchQuery}
            onSubmitEditing={handleSearch}
            returnKeyType="search"
          />
        </View>
      </View>

      {/* New Client Button */}
      <TouchableOpacity
        style={styles.newClientButton}
        onPress={() => setModalVisible(true)}
      >
        <Ionicons name="add-circle" size={24} color="#3B82F6" />
        <Text style={styles.newClientText}>Crear Nuevo Cliente</Text>
      </TouchableOpacity>

      {/* Clients List */}
      <FlatList
        data={clients}
        renderItem={renderClient}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <View style={styles.emptyState}>
            <Ionicons name="people-outline" size={48} color="#4B5563" />
            <Text style={styles.emptyText}>No se encontraron clientes</Text>
          </View>
        }
      />

      {/* Loading Overlay */}
      {loading && (
        <View style={styles.loadingOverlay}>
          <ActivityIndicator size="large" color="#3B82F6" />
          <Text style={styles.loadingText}>Procesando...</Text>
        </View>
      )}

      {/* Create Client Modal */}
      <Modal
        visible={modalVisible}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setModalVisible(false)}
      >
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.modalOverlay}
        >
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Nuevo Cliente</Text>
              <TouchableOpacity onPress={() => setModalVisible(false)}>
                <Ionicons name="close" size={24} color="#FFFFFF" />
              </TouchableOpacity>
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Nombre *</Text>
              <TextInput
                style={styles.input}
                placeholder="Nombre completo"
                placeholderTextColor="#6B7280"
                value={newClient.name}
                onChangeText={(text) => setNewClient({ ...newClient, name: text })}
              />
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Teléfono</Text>
              <TextInput
                style={styles.input}
                placeholder="Número de teléfono"
                placeholderTextColor="#6B7280"
                value={newClient.phone}
                onChangeText={(text) => setNewClient({ ...newClient, phone: text })}
                keyboardType="phone-pad"
              />
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Email</Text>
              <TextInput
                style={styles.input}
                placeholder="Correo electrónico"
                placeholderTextColor="#6B7280"
                value={newClient.email}
                onChangeText={(text) => setNewClient({ ...newClient, email: text })}
                keyboardType="email-address"
                autoCapitalize="none"
              />
            </View>

            <TouchableOpacity
              style={[styles.saveButton, loading && styles.saveButtonDisabled]}
              onPress={handleCreateClient}
              disabled={loading}
            >
              {loading ? (
                <ActivityIndicator color="#FFFFFF" />
              ) : (
                <Text style={styles.saveButtonText}>Crear y Continuar</Text>
              )}
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#111827',
  },
  vehicleInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1F2937',
    margin: 16,
    padding: 16,
    borderRadius: 12,
  },
  vehicleDetails: {
    marginLeft: 12,
    flex: 1,
  },
  vehicleTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  vehicleVin: {
    fontSize: 13,
    color: '#9CA3AF',
    marginTop: 4,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
    paddingHorizontal: 16,
    marginBottom: 12,
  },
  searchContainer: {
    paddingHorizontal: 16,
    marginBottom: 12,
  },
  searchInputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1F2937',
    borderRadius: 12,
    paddingHorizontal: 16,
    borderWidth: 1,
    borderColor: '#374151',
  },
  searchInput: {
    flex: 1,
    height: 48,
    color: '#FFFFFF',
    fontSize: 16,
    marginLeft: 12,
  },
  newClientButton: {
    flexDirection: 'row',
    alignItems: 'center',
    marginHorizontal: 16,
    marginBottom: 16,
    padding: 16,
    backgroundColor: 'rgba(59, 130, 246, 0.1)',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#3B82F6',
    borderStyle: 'dashed',
  },
  newClientText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#3B82F6',
    marginLeft: 12,
  },
  list: {
    paddingHorizontal: 16,
    paddingBottom: 20,
  },
  clientCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 16,
    marginBottom: 8,
  },
  avatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: '#3B82F6',
    justifyContent: 'center',
    alignItems: 'center',
  },
  avatarText: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  clientInfo: {
    flex: 1,
    marginLeft: 12,
  },
  clientName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  clientDetail: {
    fontSize: 13,
    color: '#9CA3AF',
    marginTop: 2,
  },
  emptyState: {
    alignItems: 'center',
    padding: 40,
  },
  emptyText: {
    fontSize: 16,
    color: '#6B7280',
    marginTop: 12,
  },
  loadingOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    fontSize: 16,
    color: '#FFFFFF',
    marginTop: 12,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#1F2937',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: 24,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 24,
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  inputGroup: {
    marginBottom: 16,
  },
  inputLabel: {
    fontSize: 14,
    color: '#9CA3AF',
    marginBottom: 8,
  },
  input: {
    backgroundColor: '#374151',
    borderRadius: 12,
    paddingHorizontal: 16,
    height: 48,
    color: '#FFFFFF',
    fontSize: 16,
  },
  saveButton: {
    backgroundColor: '#3B82F6',
    borderRadius: 12,
    height: 50,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 8,
  },
  saveButtonDisabled: {
    opacity: 0.7,
  },
  saveButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
});
