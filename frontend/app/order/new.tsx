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
} from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getServices, createWorkOrder, getClient, getUsers } from '../../src/services/api';
import { ServiceItem, Vehicle, User } from '../../src/types';
import { useAuthStore } from '../../src/store/authStore';

export default function NewOrderScreen() {
  const params = useLocalSearchParams();
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';
  const vehicleId = params.vehicleId as string;
  const clientId = params.clientId as string;
  const vehicleData: Vehicle = params.vehicleData ? JSON.parse(params.vehicleData as string) : null;

  const [services, setServices] = useState<ServiceItem[]>([]);
  const [selectedServices, setSelectedServices] = useState<Set<string>>(new Set());
  const [selectedSides, setSelectedSides] = useState<Map<string, string>>(new Map()); // For services that need side selection
  const [loading, setLoading] = useState(false);
  const [clientName, setClientName] = useState('');
  const [notes, setNotes] = useState('');
  const [odometer, setOdometer] = useState('');
  const [totalPrice, setTotalPrice] = useState('');
  const [activeCategory, setActiveCategory] = useState('srs');
  
  // Tech assignment (admin only)
  const [technicians, setTechnicians] = useState<User[]>([]);
  const [selectedTech, setSelectedTech] = useState<User | null>(null);
  const [techModalVisible, setTechModalVisible] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [servicesRes, clientRes] = await Promise.all([
        getServices(),
        getClient(clientId),
      ]);
      setServices(servicesRes);
      setClientName(clientRes.name);
      
      // Load technicians if admin
      if (isAdmin) {
        const usersRes = await getUsers();
        const techs = usersRes.filter((u: User) => u.role === 'tech' && u.active !== false);
        setTechnicians(techs);
      }
    } catch (error) {
      console.error('Error loading data:', error);
    }
  };

  const toggleService = (serviceId: string, side?: string) => {
    const key = side ? `${serviceId}-${side}` : serviceId;
    const newSelected = new Set(selectedServices);
    
    if (newSelected.has(key)) {
      newSelected.delete(key);
      if (side) {
        const newSides = new Map(selectedSides);
        newSides.delete(key);
        setSelectedSides(newSides);
      }
    } else {
      newSelected.add(key);
      if (side) {
        const newSides = new Map(selectedSides);
        newSides.set(key, side);
        setSelectedSides(newSides);
      }
    }
    
    setSelectedServices(newSelected);
  };

  const isSelected = (serviceId: string, side?: string) => {
    const key = side ? `${serviceId}-${side}` : serviceId;
    return selectedServices.has(key);
  };

  const handleCreateOrder = async () => {
    if (selectedServices.size === 0) {
      Alert.alert('Error', 'Seleccione al menos un servicio');
      return;
    }

    const price = parseFloat(totalPrice);
    if (isNaN(price) || price <= 0) {
      Alert.alert('Error', 'Ingrese el precio total del trabajo');
      return;
    }

    // If admin and no tech selected, show warning
    if (isAdmin && !selectedTech) {
      Alert.alert(
        'Asignar Técnico',
        '¿Desea asignarse la orden a usted mismo o seleccionar un técnico?',
        [
          {
            text: 'A mí mismo',
            onPress: () => submitOrder(undefined),
          },
          {
            text: 'Seleccionar técnico',
            onPress: () => setTechModalVisible(true),
          },
        ]
      );
      return;
    }

    submitOrder(selectedTech?.id);
  };

  const submitOrder = async (techId?: string) => {
    setLoading(true);
    try {
      // Build services array - distribute price equally or assign to first service
      const servicesArray: Array<{
        service_id: string;
        service_name: string;
        quantity: number;
        price: number;
        side?: string;
      }> = [];
      
      const totalServicePrice = parseFloat(totalPrice);
      const pricePerService = selectedServices.size > 0 ? totalServicePrice / selectedServices.size : 0;
      
      selectedServices.forEach((key) => {
        const [serviceId, side] = key.includes('-') ? key.split('-') : [key, undefined];
        const service = services.find(s => s.id === serviceId);
        if (service) {
          servicesArray.push({
            service_id: service.id,
            service_name: service.name,
            quantity: 1,
            price: pricePerService,
            side: side as any,
          });
        }
      });
      
      const order = await createWorkOrder({
        vehicle_id: vehicleId,
        client_id: clientId,
        tech_id: techId,
        services: servicesArray,
        odometer: odometer ? parseInt(odometer) : undefined,
        notes: notes || undefined,
      });

      const message = techId && selectedTech 
        ? `Orden asignada a ${selectedTech.name}` 
        : 'Orden creada correctamente';

      Alert.alert('Éxito', message, [
        {
          text: 'Ver Orden',
          onPress: () => router.replace(`/order/${order.id}`),
        },
      ]);
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Error al crear orden');
    } finally {
      setLoading(false);
    }
  };

  const categories = [
    { id: 'srs', name: 'SRS / Airbag', icon: 'shield' },
    { id: 'cinturones', name: 'Cinturones', icon: 'body' },
    { id: 'adas', name: 'ADAS / Radar', icon: 'radio' },
  ];

  const filteredServices = services.filter((s) => s.category === activeCategory);

  const needsSideSelection = (service: ServiceItem) => {
    const name = service.name.toLowerCase();
    return name.includes('asiento') ||
      name.includes('knee') ||
      name.includes('pretensioner') ||
      name.includes('techo') ||
      name.includes('lateral') ||
      name.includes('cortina');
  };

  const renderService = (service: ServiceItem) => {
    const hasSides = needsSideSelection(service);

    if (!hasSides) {
      const selected = isSelected(service.id);
      return (
        <TouchableOpacity
          key={service.id}
          style={[styles.serviceCard, selected && styles.serviceCardSelected]}
          onPress={() => toggleService(service.id)}
          activeOpacity={0.7}
        >
          <View style={[styles.checkbox, selected && styles.checkboxSelected]}>
            {selected && <Ionicons name="checkmark" size={18} color="#FFFFFF" />}
          </View>
          <Text style={[styles.serviceName, selected && styles.serviceNameSelected]}>
            {service.name}
          </Text>
        </TouchableOpacity>
      );
    }

    // Service with side selection
    const leftSelected = isSelected(service.id, 'left');
    const rightSelected = isSelected(service.id, 'right');
    const anySelected = leftSelected || rightSelected;

    return (
      <View key={service.id} style={[styles.serviceCard, anySelected && styles.serviceCardSelected]}>
        <Text style={[styles.serviceName, anySelected && styles.serviceNameSelected, { flex: 1 }]}>
          {service.name}
        </Text>
        <View style={styles.sideButtons}>
          <TouchableOpacity
            style={[styles.sideButton, leftSelected && styles.sideButtonSelected]}
            onPress={() => toggleService(service.id, 'left')}
          >
            <View style={[styles.miniCheckbox, leftSelected && styles.miniCheckboxSelected]}>
              {leftSelected && <Ionicons name="checkmark" size={12} color="#FFFFFF" />}
            </View>
            <Text style={[styles.sideButtonText, leftSelected && styles.sideButtonTextSelected]}>
              Izq
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.sideButton, rightSelected && styles.sideButtonSelected]}
            onPress={() => toggleService(service.id, 'right')}
          >
            <View style={[styles.miniCheckbox, rightSelected && styles.miniCheckboxSelected]}>
              {rightSelected && <Ionicons name="checkmark" size={12} color="#FFFFFF" />}
            </View>
            <Text style={[styles.sideButtonText, rightSelected && styles.sideButtonTextSelected]}>
              Der
            </Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  };

  // Get selected service names for summary
  const getSelectedServiceNames = () => {
    const names: string[] = [];
    selectedServices.forEach((key) => {
      const [serviceId, side] = key.includes('-') ? key.split('-') : [key, undefined];
      const service = services.find(s => s.id === serviceId);
      if (service) {
        const sideName = side === 'left' ? ' (Izq)' : side === 'right' ? ' (Der)' : '';
        names.push(service.name + sideName);
      }
    });
    return names;
  };

  return (
    <View style={styles.container}>
      <ScrollView style={styles.scrollView} showsVerticalScrollIndicator={false}>
        {/* Vehicle Info */}
        <View style={styles.infoCard}>
          <View style={styles.infoRow}>
            <Ionicons name="car" size={24} color="#3B82F6" />
            <View style={styles.infoText}>
              <Text style={styles.infoTitle}>
                {vehicleData?.year} {vehicleData?.make} {vehicleData?.model}
              </Text>
              <Text style={styles.infoSubtitle}>VIN: {vehicleData?.vin}</Text>
            </View>
          </View>
          <View style={styles.infoRow}>
            <Ionicons name="person" size={24} color="#10B981" />
            <View style={styles.infoText}>
              <Text style={styles.infoTitle}>{clientName}</Text>
              <Text style={styles.infoSubtitle}>Cliente</Text>
            </View>
          </View>
        </View>

        {/* Tech Assignment (Admin only) */}
        {isAdmin && technicians.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Asignar a Técnico</Text>
            <TouchableOpacity
              style={styles.techSelector}
              onPress={() => setTechModalVisible(true)}
            >
              {selectedTech ? (
                <View style={styles.selectedTechRow}>
                  <View style={styles.techAvatar}>
                    <Text style={styles.techAvatarText}>
                      {selectedTech.name.charAt(0).toUpperCase()}
                    </Text>
                  </View>
                  <Text style={styles.selectedTechName}>{selectedTech.name}</Text>
                  <Ionicons name="checkmark-circle" size={20} color="#10B981" />
                </View>
              ) : (
                <View style={styles.selectTechRow}>
                  <Ionicons name="person-add" size={24} color="#6B7280" />
                  <Text style={styles.selectTechText}>Seleccionar técnico (opcional)</Text>
                  <Ionicons name="chevron-forward" size={20} color="#6B7280" />
                </View>
              )}
            </TouchableOpacity>
            {selectedTech && (
              <TouchableOpacity
                style={styles.clearTechButton}
                onPress={() => setSelectedTech(null)}
              >
                <Ionicons name="close-circle" size={16} color="#EF4444" />
                <Text style={styles.clearTechText}>Asignarme a mí</Text>
              </TouchableOpacity>
            )}
          </View>
        )}

        {/* Odometer */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Odómetro (opcional)</Text>
          <TextInput
            style={styles.input}
            placeholder="Ej: 45000"
            placeholderTextColor="#6B7280"
            value={odometer}
            onChangeText={setOdometer}
            keyboardType="numeric"
          />
        </View>

        {/* Category Tabs */}
        <Text style={styles.mainTitle}>Servicios a Realizar</Text>
        <View style={styles.categoryTabs}>
          {categories.map((cat) => (
            <TouchableOpacity
              key={cat.id}
              style={[
                styles.categoryTab,
                activeCategory === cat.id && styles.categoryTabActive,
              ]}
              onPress={() => setActiveCategory(cat.id)}
            >
              <Ionicons
                name={cat.icon as any}
                size={18}
                color={activeCategory === cat.id ? '#FFFFFF' : '#6B7280'}
              />
              <Text style={[
                styles.categoryTabText,
                activeCategory === cat.id && styles.categoryTabTextActive,
              ]}>{cat.name}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Services List */}
        <View style={styles.servicesList}>
          {filteredServices.map(renderService)}
        </View>

        {/* Selected Services Summary */}
        {selectedServices.size > 0 && (
          <View style={styles.summarySection}>
            <Text style={styles.summaryTitle}>
              Servicios Seleccionados ({selectedServices.size})
            </Text>
            {getSelectedServiceNames().map((name, index) => (
              <View key={index} style={styles.summaryItem}>
                <Ionicons name="checkmark-circle" size={16} color="#10B981" />
                <Text style={styles.summaryItemText}>{name}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Total Price Input */}
        <View style={styles.priceSection}>
          <Text style={styles.priceLabel}>Precio Total del Trabajo</Text>
          <View style={styles.priceInputContainer}>
            <Text style={styles.dollarSign}>$</Text>
            <TextInput
              style={styles.priceInput}
              placeholder="0.00"
              placeholderTextColor="#6B7280"
              value={totalPrice}
              onChangeText={setTotalPrice}
              keyboardType="decimal-pad"
            />
          </View>
        </View>

        {/* Notes */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Notas (opcional)</Text>
          <TextInput
            style={[styles.input, styles.textArea]}
            placeholder="Notas adicionales sobre el trabajo..."
            placeholderTextColor="#6B7280"
            value={notes}
            onChangeText={setNotes}
            multiline
            numberOfLines={3}
          />
        </View>

        {/* Spacer for bottom bar */}
        <View style={{ height: 100 }} />
      </ScrollView>

      {/* Bottom Bar */}
      <View style={styles.bottomBar}>
        <View style={styles.bottomInfo}>
          <Text style={styles.bottomLabel}>{selectedServices.size} servicio(s)</Text>
          <Text style={styles.bottomPrice}>
            ${totalPrice ? parseFloat(totalPrice).toFixed(2) : '0.00'}
          </Text>
        </View>
        <TouchableOpacity
          style={[
            styles.createButton,
            (loading || selectedServices.size === 0) && styles.createButtonDisabled
          ]}
          onPress={handleCreateOrder}
          disabled={loading || selectedServices.size === 0}
        >
          {loading ? (
            <ActivityIndicator color="#FFFFFF" />
          ) : (
            <>
              <Ionicons name="checkmark-circle" size={22} color="#FFFFFF" />
              <Text style={styles.createButtonText}>Crear Orden</Text>
            </>
          )}
        </TouchableOpacity>
      </View>

      {/* Tech Selection Modal */}
      <Modal
        visible={techModalVisible}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setTechModalVisible(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Seleccionar Técnico</Text>
              <TouchableOpacity onPress={() => setTechModalVisible(false)}>
                <Ionicons name="close" size={24} color="#FFFFFF" />
              </TouchableOpacity>
            </View>

            <ScrollView style={styles.techList}>
              {technicians.map((tech) => (
                <TouchableOpacity
                  key={tech.id}
                  style={[
                    styles.techItem,
                    selectedTech?.id === tech.id && styles.techItemSelected,
                  ]}
                  onPress={() => {
                    setSelectedTech(tech);
                    setTechModalVisible(false);
                  }}
                >
                  <View style={styles.techItemAvatar}>
                    <Text style={styles.techItemAvatarText}>
                      {tech.name.charAt(0).toUpperCase()}
                    </Text>
                  </View>
                  <View style={styles.techItemInfo}>
                    <Text style={styles.techItemName}>{tech.name}</Text>
                    <Text style={styles.techItemEmail}>{tech.email}</Text>
                  </View>
                  {selectedTech?.id === tech.id && (
                    <Ionicons name="checkmark-circle" size={24} color="#10B981" />
                  )}
                </TouchableOpacity>
              ))}
            </ScrollView>
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
  scrollView: {
    flex: 1,
  },
  infoCard: {
    backgroundColor: '#1F2937',
    margin: 16,
    borderRadius: 12,
    padding: 16,
  },
  infoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  infoText: {
    marginLeft: 12,
    flex: 1,
  },
  infoTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  infoSubtitle: {
    fontSize: 13,
    color: '#9CA3AF',
  },
  section: {
    paddingHorizontal: 16,
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 14,
    color: '#9CA3AF',
    marginBottom: 8,
  },
  input: {
    backgroundColor: '#1F2937',
    borderRadius: 12,
    paddingHorizontal: 16,
    height: 48,
    color: '#FFFFFF',
    fontSize: 16,
    borderWidth: 1,
    borderColor: '#374151',
  },
  textArea: {
    height: 80,
    paddingTop: 12,
    textAlignVertical: 'top',
  },
  mainTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#FFFFFF',
    marginHorizontal: 16,
    marginBottom: 12,
  },
  categoryTabs: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    gap: 8,
    marginBottom: 16,
  },
  categoryTab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#1F2937',
    borderRadius: 10,
    paddingVertical: 10,
    gap: 6,
  },
  categoryTabActive: {
    backgroundColor: '#3B82F6',
  },
  categoryTabText: {
    fontSize: 11,
    color: '#6B7280',
    fontWeight: '600',
  },
  categoryTabTextActive: {
    color: '#FFFFFF',
  },
  servicesList: {
    paddingHorizontal: 16,
  },
  serviceCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 14,
    marginBottom: 8,
    borderWidth: 2,
    borderColor: 'transparent',
  },
  serviceCardSelected: {
    borderColor: '#3B82F6',
    backgroundColor: 'rgba(59, 130, 246, 0.1)',
  },
  checkbox: {
    width: 26,
    height: 26,
    borderRadius: 8,
    borderWidth: 2,
    borderColor: '#4B5563',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
    backgroundColor: '#374151',
  },
  checkboxSelected: {
    backgroundColor: '#3B82F6',
    borderColor: '#3B82F6',
  },
  serviceName: {
    fontSize: 14,
    fontWeight: '500',
    color: '#D1D5DB',
  },
  serviceNameSelected: {
    color: '#FFFFFF',
    fontWeight: '600',
  },
  sideButtons: {
    flexDirection: 'row',
    gap: 8,
  },
  sideButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: '#374151',
    gap: 6,
  },
  sideButtonSelected: {
    backgroundColor: '#3B82F6',
  },
  miniCheckbox: {
    width: 18,
    height: 18,
    borderRadius: 4,
    borderWidth: 1.5,
    borderColor: '#6B7280',
    justifyContent: 'center',
    alignItems: 'center',
  },
  miniCheckboxSelected: {
    backgroundColor: '#FFFFFF',
    borderColor: '#FFFFFF',
  },
  sideButtonText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#9CA3AF',
  },
  sideButtonTextSelected: {
    color: '#FFFFFF',
  },
  // Summary Section
  summarySection: {
    backgroundColor: '#1F2937',
    marginHorizontal: 16,
    marginTop: 16,
    borderRadius: 12,
    padding: 16,
  },
  summaryTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 12,
  },
  summaryItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
    gap: 8,
  },
  summaryItemText: {
    fontSize: 13,
    color: '#D1D5DB',
  },
  // Price Section
  priceSection: {
    backgroundColor: '#1F2937',
    marginHorizontal: 16,
    marginTop: 16,
    borderRadius: 12,
    padding: 16,
  },
  priceLabel: {
    fontSize: 14,
    color: '#9CA3AF',
    marginBottom: 12,
  },
  priceInputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#374151',
    borderRadius: 12,
    paddingHorizontal: 16,
  },
  dollarSign: {
    fontSize: 28,
    color: '#10B981',
    fontWeight: '700',
    marginRight: 8,
  },
  priceInput: {
    flex: 1,
    height: 60,
    color: '#FFFFFF',
    fontSize: 28,
    fontWeight: '700',
  },
  // Bottom Bar
  bottomBar: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#1F2937',
    padding: 16,
    borderTopWidth: 1,
    borderTopColor: '#374151',
  },
  bottomInfo: {
    flex: 1,
  },
  bottomLabel: {
    fontSize: 12,
    color: '#9CA3AF',
  },
  bottomPrice: {
    fontSize: 22,
    fontWeight: '700',
    color: '#10B981',
  },
  createButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#3B82F6',
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderRadius: 12,
    gap: 8,
  },
  createButtonDisabled: {
    backgroundColor: '#374151',
    opacity: 0.7,
  },
  createButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  // Tech Section
  techSelector: {
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: '#374151',
  },
  selectedTechRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  techAvatar: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#3B82F6',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  techAvatarText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
  selectedTechName: {
    flex: 1,
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '500',
  },
  selectTechRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  selectTechText: {
    flex: 1,
    color: '#9CA3AF',
    fontSize: 14,
    marginLeft: 12,
  },
  clearTechButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 12,
    padding: 8,
  },
  clearTechText: {
    color: '#EF4444',
    fontSize: 13,
    marginLeft: 6,
  },
  // Modal
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#1F2937',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    maxHeight: '70%',
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#374151',
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  techList: {
    padding: 16,
  },
  techItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#374151',
    borderRadius: 12,
    padding: 16,
    marginBottom: 8,
  },
  techItemSelected: {
    borderColor: '#10B981',
    borderWidth: 2,
    backgroundColor: 'rgba(16, 185, 129, 0.1)',
  },
  techItemAvatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#3B82F6',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  techItemAvatarText: {
    color: '#FFFFFF',
    fontSize: 18,
    fontWeight: '600',
  },
  techItemInfo: {
    flex: 1,
  },
  techItemName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  techItemEmail: {
    fontSize: 13,
    color: '#9CA3AF',
    marginTop: 2,
  },
});
