import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  TextInput,
  Alert,
  ActivityIndicator,
  Modal,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { getClients, createClient, getUsers, createWorkOrder } from '../../src/services/api';
import { Client, User } from '../../src/types';

// Servicios predefinidos
const SERVICES = [
  { id: 'srs-reset', name: 'Reset módulo SRS' },
  { id: 'srs-volante', name: 'Bolsa de volante' },
  { id: 'srs-techo', name: 'Bolsa de techo' },
  { id: 'srs-asiento', name: 'Bolsa de asiento' },
  { id: 'srs-lateral', name: 'Bolsa lateral' },
  { id: 'srs-cortina', name: 'Cortina' },
  { id: 'belt-conductor', name: 'Cinturón conductor' },
  { id: 'belt-pasajero', name: 'Cinturón pasajero' },
  { id: 'adas-radar', name: 'Calibración radar' },
  { id: 'adas-camara', name: 'Calibración cámara' },
];

export default function AssignOrderScreen() {
  const [step, setStep] = useState(1); // 1: Select Client, 2: Select Services & Tech
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  
  // Client
  const [clients, setClients] = useState<Client[]>([]);
  const [selectedClient, setSelectedClient] = useState<Client | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [showNewClient, setShowNewClient] = useState(false);
  const [newClient, setNewClient] = useState({ name: '', phone: '', address: '' });
  
  // Services & Tech
  const [selectedServices, setSelectedServices] = useState<Set<string>>(new Set());
  const [technicians, setTechnicians] = useState<User[]>([]);
  const [selectedTech, setSelectedTech] = useState<User | null>(null);
  const [notes, setNotes] = useState('');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [clientsRes, usersRes] = await Promise.all([
        getClients(),
        getUsers(),
      ]);
      setClients(clientsRes);
      setTechnicians(usersRes.filter((u: User) => u.role === 'tech' && u.active !== false));
    } catch (error) {
      Alert.alert('Error', 'No se pudieron cargar los datos');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateClient = async () => {
    if (!newClient.name.trim()) {
      Alert.alert('Error', 'El nombre es requerido');
      return;
    }

    setSaving(true);
    try {
      const created = await createClient({
        name: newClient.name.trim(),
        phone: newClient.phone.trim() || undefined,
        address: newClient.address.trim() || undefined,
      });
      setClients([created, ...clients]);
      setSelectedClient(created);
      setShowNewClient(false);
      setNewClient({ name: '', phone: '', address: '' });
      setStep(2);
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Error al crear cliente');
    } finally {
      setSaving(false);
    }
  };

  const toggleService = (serviceId: string) => {
    const newSet = new Set(selectedServices);
    if (newSet.has(serviceId)) {
      newSet.delete(serviceId);
    } else {
      newSet.add(serviceId);
    }
    setSelectedServices(newSet);
  };

  const handleCreateOrder = async () => {
    if (!selectedClient) {
      Alert.alert('Error', 'Selecciona un cliente');
      return;
    }
    if (selectedServices.size === 0) {
      Alert.alert('Error', 'Selecciona al menos un servicio');
      return;
    }
    if (!selectedTech) {
      Alert.alert('Error', 'Asigna un técnico');
      return;
    }

    setSaving(true);
    try {
      const servicesArray = Array.from(selectedServices).map(id => {
        const service = SERVICES.find(s => s.id === id);
        return {
          service_id: id,
          service_name: service?.name || id,
          quantity: 1,
          price: 0,
        };
      });

      const order = await createWorkOrder({
        client_id: selectedClient.id,
        tech_id: selectedTech.id,
        services: servicesArray,
        notes: notes || undefined,
        // No vehicle_id - tech will scan later
      });

      Alert.alert(
        '✅ Orden Asignada',
        `La orden fue asignada a ${selectedTech.name}.\n\nEl técnico escaneará el VIN del vehículo al llegar.`,
        [{ text: 'OK', onPress: () => router.replace(`/order/${order.id}`) }]
      );
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Error al crear orden');
    } finally {
      setSaving(false);
    }
  };

  const filteredClients = clients.filter(c => 
    c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (c.phone && c.phone.includes(searchQuery))
  );

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#3B82F6" />
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color="#FFF" />
        </TouchableOpacity>
        <View style={styles.headerContent}>
          <Text style={styles.headerTitle}>Asignar Orden</Text>
          <Text style={styles.headerSubtitle}>
            {step === 1 ? 'Paso 1: Seleccionar Cliente' : 'Paso 2: Servicios y Técnico'}
          </Text>
        </View>
      </View>

      {/* Step Indicator */}
      <View style={styles.steps}>
        <View style={[styles.stepDot, step >= 1 && styles.stepDotActive]} />
        <View style={styles.stepLine} />
        <View style={[styles.stepDot, step >= 2 && styles.stepDotActive]} />
      </View>

      {step === 1 ? (
        // STEP 1: Select Client
        <ScrollView style={styles.content}>
          <TextInput
            style={styles.searchInput}
            placeholder="Buscar cliente por nombre o teléfono..."
            placeholderTextColor="#6B7280"
            value={searchQuery}
            onChangeText={setSearchQuery}
          />

          <TouchableOpacity 
            style={styles.newClientBtn}
            onPress={() => setShowNewClient(true)}
          >
            <Ionicons name="add-circle" size={22} color="#3B82F6" />
            <Text style={styles.newClientBtnText}>Crear Nuevo Cliente</Text>
          </TouchableOpacity>

          <Text style={styles.sectionTitle}>Clientes Existentes</Text>
          
          {filteredClients.map(client => (
            <TouchableOpacity
              key={client.id}
              style={[
                styles.clientCard,
                selectedClient?.id === client.id && styles.clientCardSelected
              ]}
              onPress={() => {
                setSelectedClient(client);
                setStep(2);
              }}
            >
              <View style={styles.clientIcon}>
                <Ionicons name="person" size={24} color="#3B82F6" />
              </View>
              <View style={styles.clientInfo}>
                <Text style={styles.clientName}>{client.name}</Text>
                {client.phone && <Text style={styles.clientPhone}>📱 {client.phone}</Text>}
                {client.address && <Text style={styles.clientAddress} numberOfLines={1}>📍 {client.address}</Text>}
              </View>
              <Ionicons name="chevron-forward" size={20} color="#6B7280" />
            </TouchableOpacity>
          ))}
          
          {filteredClients.length === 0 && (
            <Text style={styles.emptyText}>No se encontraron clientes</Text>
          )}
        </ScrollView>
      ) : (
        // STEP 2: Services & Tech
        <ScrollView style={styles.content}>
          {/* Selected Client Summary */}
          <View style={styles.selectedClientCard}>
            <View style={styles.selectedClientHeader}>
              <Ionicons name="person" size={20} color="#10B981" />
              <Text style={styles.selectedClientName}>{selectedClient?.name}</Text>
              <TouchableOpacity onPress={() => setStep(1)}>
                <Text style={styles.changeText}>Cambiar</Text>
              </TouchableOpacity>
            </View>
            {selectedClient?.phone && <Text style={styles.selectedClientDetail}>📱 {selectedClient.phone}</Text>}
            {selectedClient?.address && <Text style={styles.selectedClientDetail}>📍 {selectedClient.address}</Text>}
          </View>

          {/* Services Selection */}
          <Text style={styles.sectionTitle}>Seleccionar Servicios</Text>
          <View style={styles.servicesList}>
            {SERVICES.map(service => (
              <TouchableOpacity
                key={service.id}
                style={[
                  styles.serviceItem,
                  selectedServices.has(service.id) && styles.serviceItemSelected
                ]}
                onPress={() => toggleService(service.id)}
              >
                <Text style={styles.serviceName}>{service.name}</Text>
                <View style={[
                  styles.checkbox,
                  selectedServices.has(service.id) && styles.checkboxSelected
                ]}>
                  {selectedServices.has(service.id) && (
                    <Ionicons name="checkmark" size={16} color="#FFF" />
                  )}
                </View>
              </TouchableOpacity>
            ))}
          </View>

          {/* Tech Selection */}
          <Text style={styles.sectionTitle}>Asignar Técnico</Text>
          <View style={styles.techList}>
            {technicians.map(tech => (
              <TouchableOpacity
                key={tech.id}
                style={[
                  styles.techCard,
                  selectedTech?.id === tech.id && styles.techCardSelected
                ]}
                onPress={() => setSelectedTech(tech)}
              >
                <View style={[
                  styles.techAvatar,
                  selectedTech?.id === tech.id && styles.techAvatarSelected
                ]}>
                  <Ionicons name="person" size={20} color={selectedTech?.id === tech.id ? '#FFF' : '#6B7280'} />
                </View>
                <Text style={[
                  styles.techName,
                  selectedTech?.id === tech.id && styles.techNameSelected
                ]}>
                  {tech.name}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* Notes */}
          <Text style={styles.sectionTitle}>Notas (opcional)</Text>
          <TextInput
            style={styles.notesInput}
            placeholder="Instrucciones especiales para el técnico..."
            placeholderTextColor="#6B7280"
            value={notes}
            onChangeText={setNotes}
            multiline
          />

          {/* Create Button */}
          <TouchableOpacity
            style={[styles.createBtn, (!selectedTech || selectedServices.size === 0) && styles.createBtnDisabled]}
            onPress={handleCreateOrder}
            disabled={saving || !selectedTech || selectedServices.size === 0}
          >
            {saving ? (
              <ActivityIndicator color="#FFF" />
            ) : (
              <>
                <Ionicons name="checkmark-circle" size={22} color="#FFF" />
                <Text style={styles.createBtnText}>Asignar Orden</Text>
              </>
            )}
          </TouchableOpacity>

          <View style={{ height: 40 }} />
        </ScrollView>
      )}

      {/* New Client Modal */}
      <Modal visible={showNewClient} animationType="slide" transparent>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.modalOverlay}
        >
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Nuevo Cliente</Text>
              <TouchableOpacity onPress={() => setShowNewClient(false)}>
                <Ionicons name="close" size={24} color="#FFF" />
              </TouchableOpacity>
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Nombre *</Text>
              <TextInput
                style={styles.input}
                placeholder="Nombre del cliente"
                placeholderTextColor="#6B7280"
                value={newClient.name}
                onChangeText={(t) => setNewClient({...newClient, name: t})}
              />
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Teléfono</Text>
              <TextInput
                style={styles.input}
                placeholder="Número de teléfono"
                placeholderTextColor="#6B7280"
                value={newClient.phone}
                onChangeText={(t) => setNewClient({...newClient, phone: t})}
                keyboardType="phone-pad"
              />
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Dirección</Text>
              <TextInput
                style={[styles.input, { height: 80, textAlignVertical: 'top' }]}
                placeholder="Dirección completa"
                placeholderTextColor="#6B7280"
                value={newClient.address}
                onChangeText={(t) => setNewClient({...newClient, address: t})}
                multiline
              />
            </View>

            <TouchableOpacity
              style={styles.saveBtn}
              onPress={handleCreateClient}
              disabled={saving}
            >
              {saving ? (
                <ActivityIndicator color="#FFF" />
              ) : (
                <Text style={styles.saveBtnText}>Crear Cliente</Text>
              )}
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#111827',
  },
  loadingContainer: {
    flex: 1,
    backgroundColor: '#111827',
    justifyContent: 'center',
    alignItems: 'center',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: '#1F2937',
  },
  backBtn: {
    padding: 8,
  },
  headerContent: {
    marginLeft: 12,
  },
  headerTitle: {
    color: '#FFF',
    fontSize: 20,
    fontWeight: '700',
  },
  headerSubtitle: {
    color: '#9CA3AF',
    fontSize: 13,
    marginTop: 2,
  },
  steps: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 16,
    backgroundColor: '#1F2937',
  },
  stepDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: '#374151',
  },
  stepDotActive: {
    backgroundColor: '#3B82F6',
  },
  stepLine: {
    width: 60,
    height: 2,
    backgroundColor: '#374151',
    marginHorizontal: 8,
  },
  content: {
    flex: 1,
    padding: 16,
  },
  searchInput: {
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 14,
    color: '#FFF',
    fontSize: 15,
    marginBottom: 12,
  },
  newClientBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(59, 130, 246, 0.15)',
    padding: 14,
    borderRadius: 12,
    marginBottom: 20,
    gap: 8,
  },
  newClientBtnText: {
    color: '#3B82F6',
    fontSize: 15,
    fontWeight: '600',
  },
  sectionTitle: {
    color: '#9CA3AF',
    fontSize: 13,
    fontWeight: '600',
    textTransform: 'uppercase',
    marginBottom: 12,
    marginTop: 8,
  },
  clientCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
  },
  clientCardSelected: {
    borderColor: '#3B82F6',
    borderWidth: 2,
  },
  clientIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: 'rgba(59, 130, 246, 0.15)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  clientInfo: {
    flex: 1,
    marginLeft: 12,
  },
  clientName: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '600',
  },
  clientPhone: {
    color: '#9CA3AF',
    fontSize: 13,
    marginTop: 2,
  },
  clientAddress: {
    color: '#6B7280',
    fontSize: 12,
    marginTop: 2,
  },
  emptyText: {
    color: '#6B7280',
    fontSize: 14,
    textAlign: 'center',
    marginTop: 20,
  },
  selectedClientCard: {
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 14,
    marginBottom: 16,
    borderLeftWidth: 4,
    borderLeftColor: '#10B981',
  },
  selectedClientHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  selectedClientName: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '600',
    flex: 1,
  },
  changeText: {
    color: '#3B82F6',
    fontSize: 13,
    fontWeight: '600',
  },
  selectedClientDetail: {
    color: '#9CA3AF',
    fontSize: 13,
    marginTop: 6,
    marginLeft: 28,
  },
  servicesList: {
    backgroundColor: '#1F2937',
    borderRadius: 12,
    overflow: 'hidden',
    marginBottom: 16,
  },
  serviceItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#374151',
  },
  serviceItemSelected: {
    backgroundColor: 'rgba(59, 130, 246, 0.1)',
  },
  serviceName: {
    color: '#D1D5DB',
    fontSize: 15,
  },
  checkbox: {
    width: 24,
    height: 24,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: '#4B5563',
    justifyContent: 'center',
    alignItems: 'center',
  },
  checkboxSelected: {
    backgroundColor: '#3B82F6',
    borderColor: '#3B82F6',
  },
  techList: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    marginBottom: 16,
  },
  techCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1F2937',
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 10,
    gap: 8,
  },
  techCardSelected: {
    backgroundColor: '#3B82F6',
  },
  techAvatar: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#374151',
    justifyContent: 'center',
    alignItems: 'center',
  },
  techAvatarSelected: {
    backgroundColor: 'rgba(255,255,255,0.2)',
  },
  techName: {
    color: '#9CA3AF',
    fontSize: 14,
    fontWeight: '500',
  },
  techNameSelected: {
    color: '#FFF',
  },
  notesInput: {
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 14,
    color: '#FFF',
    fontSize: 15,
    height: 100,
    textAlignVertical: 'top',
    marginBottom: 20,
  },
  createBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#10B981',
    paddingVertical: 16,
    borderRadius: 12,
    gap: 10,
  },
  createBtnDisabled: {
    backgroundColor: '#374151',
    opacity: 0.6,
  },
  createBtnText: {
    color: '#FFF',
    fontSize: 17,
    fontWeight: '700',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#1F2937',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: 20,
    paddingBottom: 40,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 20,
  },
  modalTitle: {
    color: '#FFF',
    fontSize: 20,
    fontWeight: '700',
  },
  inputGroup: {
    marginBottom: 16,
  },
  inputLabel: {
    color: '#9CA3AF',
    fontSize: 13,
    marginBottom: 8,
  },
  input: {
    backgroundColor: '#374151',
    borderRadius: 10,
    padding: 14,
    color: '#FFF',
    fontSize: 15,
  },
  saveBtn: {
    backgroundColor: '#3B82F6',
    paddingVertical: 16,
    borderRadius: 12,
    alignItems: 'center',
    marginTop: 10,
  },
  saveBtnText: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '700',
  },
});
