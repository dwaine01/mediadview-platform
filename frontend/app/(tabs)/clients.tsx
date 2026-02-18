import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  FlatList,
  RefreshControl,
  TextInput,
  Alert,
  Modal,
  KeyboardAvoidingView,
  Platform,
  Switch,
} from 'react-native';
import { useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getClients, createClient, updateClient } from '../../src/services/api';
import { Client } from '../../src/types';
import { useAuthStore } from '../../src/store/authStore';

export default function ClientsScreen() {
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';
  const [clients, setClients] = useState<Client[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [modalVisible, setModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [selectedClient, setSelectedClient] = useState<Client | null>(null);
  const [newClient, setNewClient] = useState({
    name: '',
    phone: '',
    email: '',
    address: '',
    notes: '',
    has_credit: false,
  });

  const loadClients = async (search?: string) => {
    try {
      const data = await getClients(search);
      setClients(data);
    } catch (error) {
      console.error('Error loading clients:', error);
    }
  };

  useFocusEffect(
    useCallback(() => {
      loadClients();
    }, [])
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await loadClients(searchQuery);
    setRefreshing(false);
  };

  const handleSearch = () => {
    loadClients(searchQuery);
  };

  const handleCreateClient = async () => {
    if (!newClient.name.trim()) {
      Alert.alert('Error', 'El nombre es requerido');
      return;
    }

    try {
      await createClient(newClient);
      setModalVisible(false);
      setNewClient({ name: '', phone: '', email: '', address: '', notes: '', has_credit: false });
      loadClients();
      Alert.alert('Éxito', 'Cliente creado correctamente');
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Error al crear cliente');
    }
  };

  const openEditModal = (client: Client) => {
    setSelectedClient(client);
    setEditModalVisible(true);
  };

  const handleUpdateCredit = async (hasCredit: boolean) => {
    if (!selectedClient) return;
    
    try {
      await updateClient(selectedClient.id, { has_credit: hasCredit });
      setSelectedClient({ ...selectedClient, has_credit: hasCredit });
      loadClients();
      Alert.alert(
        'Éxito',
        hasCredit 
          ? 'Cuenta de crédito activada' 
          : 'Cuenta de crédito desactivada'
      );
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Error al actualizar');
    }
  };

  const renderClient = ({ item }: { item: Client }) => (
    <TouchableOpacity 
      style={styles.clientCard}
      onPress={() => openEditModal(item)}
    >
      <View style={[styles.avatar, item.has_credit && styles.avatarCredit]}>
        <Text style={styles.avatarText}>
          {item.name.charAt(0).toUpperCase()}
        </Text>
        {item.has_credit && (
          <View style={styles.creditBadge}>
            <Ionicons name="card" size={10} color="#FFF" />
          </View>
        )}
      </View>
      <View style={styles.clientInfo}>
        <View style={styles.nameRow}>
          <Text style={styles.clientName}>{item.name}</Text>
          {item.has_credit && (
            <View style={styles.creditTag}>
              <Text style={styles.creditTagText}>CRÉDITO</Text>
            </View>
          )}
        </View>
        {item.phone && (
          <View style={styles.infoRow}>
            <Ionicons name="call-outline" size={14} color="#6B7280" />
            <Text style={styles.infoText}>{item.phone}</Text>
          </View>
        )}
        {item.email && (
          <View style={styles.infoRow}>
            <Ionicons name="mail-outline" size={14} color="#6B7280" />
            <Text style={styles.infoText}>{item.email}</Text>
          </View>
        )}
      </View>
      <Ionicons name="chevron-forward" size={20} color="#6B7280" />
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      {/* Search */}
      <View style={styles.searchContainer}>
        <View style={styles.searchInputContainer}>
          <Ionicons name="search" size={20} color="#6B7280" />
          <TextInput
            style={styles.searchInput}
            placeholder="Buscar por nombre, teléfono o email"
            placeholderTextColor="#6B7280"
            value={searchQuery}
            onChangeText={setSearchQuery}
            onSubmitEditing={handleSearch}
            returnKeyType="search"
          />
          {searchQuery.length > 0 && (
            <TouchableOpacity onPress={() => { setSearchQuery(''); loadClients(); }}>
              <Ionicons name="close-circle" size={20} color="#6B7280" />
            </TouchableOpacity>
          )}
        </View>
      </View>

      {/* Clients List */}
      <FlatList
        data={clients}
        renderItem={renderClient}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#3B82F6" />
        }
        ListEmptyComponent={
          <View style={styles.emptyState}>
            <Ionicons name="people-outline" size={64} color="#4B5563" />
            <Text style={styles.emptyText}>No hay clientes</Text>
          </View>
        }
      />

      {/* FAB */}
      <TouchableOpacity
        style={styles.fab}
        onPress={() => setModalVisible(true)}
      >
        <Ionicons name="add" size={28} color="#FFFFFF" />
      </TouchableOpacity>

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
                placeholder="(555) 123-4567"
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
                placeholder="email@ejemplo.com"
                placeholderTextColor="#6B7280"
                value={newClient.email}
                onChangeText={(text) => setNewClient({ ...newClient, email: text })}
                keyboardType="email-address"
                autoCapitalize="none"
              />
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Dirección</Text>
              <TextInput
                style={styles.input}
                placeholder="Dirección"
                placeholderTextColor="#6B7280"
                value={newClient.address}
                onChangeText={(text) => setNewClient({ ...newClient, address: text })}
              />
            </View>

            {/* Credit Toggle */}
            {isAdmin && (
              <View style={styles.creditToggle}>
                <View style={styles.creditToggleInfo}>
                  <Ionicons name="card" size={24} color="#7C3AED" />
                  <View style={styles.creditToggleText}>
                    <Text style={styles.creditToggleTitle}>Cuenta de Crédito</Text>
                    <Text style={styles.creditToggleDesc}>El cliente puede pagar después</Text>
                  </View>
                </View>
                <Switch
                  value={newClient.has_credit}
                  onValueChange={(value) => setNewClient({ ...newClient, has_credit: value })}
                  trackColor={{ false: '#374151', true: '#7C3AED' }}
                  thumbColor={newClient.has_credit ? '#FFF' : '#9CA3AF'}
                />
              </View>
            )}

            <TouchableOpacity style={styles.createButton} onPress={handleCreateClient}>
              <Text style={styles.createButtonText}>Crear Cliente</Text>
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Edit Client Modal */}
      <Modal
        visible={editModalVisible}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setEditModalVisible(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.editModalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{selectedClient?.name}</Text>
              <TouchableOpacity onPress={() => setEditModalVisible(false)}>
                <Ionicons name="close" size={24} color="#FFFFFF" />
              </TouchableOpacity>
            </View>

            {/* Client Info */}
            <View style={styles.editClientInfo}>
              {selectedClient?.phone && (
                <View style={styles.editInfoRow}>
                  <Ionicons name="call" size={20} color="#3B82F6" />
                  <Text style={styles.editInfoText}>{selectedClient.phone}</Text>
                </View>
              )}
              {selectedClient?.email && (
                <View style={styles.editInfoRow}>
                  <Ionicons name="mail" size={20} color="#3B82F6" />
                  <Text style={styles.editInfoText}>{selectedClient.email}</Text>
                </View>
              )}
              {selectedClient?.address && (
                <View style={styles.editInfoRow}>
                  <Ionicons name="location" size={20} color="#3B82F6" />
                  <Text style={styles.editInfoText}>{selectedClient.address}</Text>
                </View>
              )}
            </View>

            {/* Credit Section - Admin Only */}
            {isAdmin && (
              <View style={styles.creditSection}>
                <Text style={styles.creditSectionTitle}>Configuración de Crédito</Text>
                
                <View style={styles.creditOption}>
                  <View style={styles.creditOptionInfo}>
                    <Ionicons 
                      name={selectedClient?.has_credit ? "checkmark-circle" : "close-circle"} 
                      size={28} 
                      color={selectedClient?.has_credit ? "#10B981" : "#6B7280"} 
                    />
                    <View style={styles.creditOptionText}>
                      <Text style={styles.creditOptionTitle}>
                        {selectedClient?.has_credit ? 'Crédito Activo' : 'Sin Crédito'}
                      </Text>
                      <Text style={styles.creditOptionDesc}>
                        {selectedClient?.has_credit 
                          ? 'Este cliente puede pagar después' 
                          : 'Este cliente paga al contado'}
                      </Text>
                    </View>
                  </View>
                  <Switch
                    value={selectedClient?.has_credit || false}
                    onValueChange={handleUpdateCredit}
                    trackColor={{ false: '#374151', true: '#10B981' }}
                    thumbColor="#FFF"
                  />
                </View>

                {selectedClient?.has_credit && (
                  <View style={styles.creditActiveNote}>
                    <Ionicons name="information-circle" size={18} color="#7C3AED" />
                    <Text style={styles.creditActiveNoteText}>
                      Las órdenes de este cliente aparecerán en "Cuentas por Cobrar"
                    </Text>
                  </View>
                )}
              </View>
            )}

            <TouchableOpacity
              style={styles.closeButton}
              onPress={() => setEditModalVisible(false)}
            >
              <Text style={styles.closeButtonText}>Cerrar</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#111827',
  },
  searchContainer: {
    padding: 16,
    backgroundColor: '#1F2937',
  },
  searchInputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#374151',
    borderRadius: 12,
    paddingHorizontal: 16,
    height: 48,
    gap: 12,
  },
  searchInput: {
    flex: 1,
    color: '#FFFFFF',
    fontSize: 16,
  },
  list: {
    padding: 16,
    paddingBottom: 100,
  },
  clientCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  avatar: {
    width: 50,
    height: 50,
    borderRadius: 25,
    backgroundColor: '#3B82F6',
    justifyContent: 'center',
    alignItems: 'center',
    position: 'relative',
  },
  avatarCredit: {
    backgroundColor: '#7C3AED',
  },
  avatarText: {
    color: '#FFFFFF',
    fontSize: 20,
    fontWeight: 'bold',
  },
  creditBadge: {
    position: 'absolute',
    bottom: -2,
    right: -2,
    backgroundColor: '#10B981',
    borderRadius: 10,
    width: 18,
    height: 18,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: '#1F2937',
  },
  clientInfo: {
    flex: 1,
    marginLeft: 14,
  },
  nameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  clientName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  creditTag: {
    backgroundColor: '#7C3AED',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 6,
  },
  creditTagText: {
    color: '#FFF',
    fontSize: 10,
    fontWeight: '700',
  },
  infoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 4,
    gap: 8,
  },
  infoText: {
    color: '#9CA3AF',
    fontSize: 13,
  },
  emptyState: {
    alignItems: 'center',
    paddingVertical: 60,
  },
  emptyText: {
    color: '#9CA3AF',
    fontSize: 16,
    marginTop: 16,
  },
  fab: {
    position: 'absolute',
    bottom: 24,
    right: 24,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#3B82F6',
    justifyContent: 'center',
    alignItems: 'center',
    elevation: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.8)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#1F2937',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: 24,
    maxHeight: '90%',
  },
  editModalContent: {
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
    height: 50,
    color: '#FFFFFF',
    fontSize: 16,
  },
  creditToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#374151',
    borderRadius: 12,
    padding: 16,
    marginBottom: 20,
  },
  creditToggleInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    gap: 12,
  },
  creditToggleText: {
    flex: 1,
  },
  creditToggleTitle: {
    color: '#FFF',
    fontSize: 15,
    fontWeight: '600',
  },
  creditToggleDesc: {
    color: '#9CA3AF',
    fontSize: 12,
    marginTop: 2,
  },
  createButton: {
    backgroundColor: '#3B82F6',
    borderRadius: 12,
    height: 50,
    justifyContent: 'center',
    alignItems: 'center',
  },
  createButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
  // Edit Modal
  editClientInfo: {
    backgroundColor: '#374151',
    borderRadius: 12,
    padding: 16,
    marginBottom: 20,
  },
  editInfoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginBottom: 12,
  },
  editInfoText: {
    color: '#D1D5DB',
    fontSize: 15,
  },
  creditSection: {
    backgroundColor: '#374151',
    borderRadius: 12,
    padding: 16,
    marginBottom: 20,
  },
  creditSectionTitle: {
    color: '#9CA3AF',
    fontSize: 14,
    marginBottom: 16,
  },
  creditOption: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  creditOptionInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    gap: 12,
  },
  creditOptionText: {
    flex: 1,
  },
  creditOptionTitle: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '600',
  },
  creditOptionDesc: {
    color: '#9CA3AF',
    fontSize: 12,
    marginTop: 2,
  },
  creditActiveNote: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(124,58,237,0.2)',
    borderRadius: 8,
    padding: 12,
    marginTop: 16,
    gap: 10,
  },
  creditActiveNoteText: {
    color: '#C4B5FD',
    fontSize: 12,
    flex: 1,
  },
  closeButton: {
    backgroundColor: '#374151',
    borderRadius: 12,
    height: 50,
    justifyContent: 'center',
    alignItems: 'center',
  },
  closeButtonText: {
    color: '#9CA3AF',
    fontSize: 16,
  },
});
