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
import { router, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getServices, createWorkOrder, getClient, getUsers } from '../../src/services/api';
import { ServiceItem, Vehicle, WorkOrderService, User } from '../../src/types';
import { useAuthStore } from '../../src/store/authStore';

interface SelectedService extends WorkOrderService {
  key: string;
}

export default function NewOrderScreen() {
  const params = useLocalSearchParams();
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';
  const vehicleId = params.vehicleId as string;
  const clientId = params.clientId as string;
  const vehicleData: Vehicle = params.vehicleData ? JSON.parse(params.vehicleData as string) : null;

  const [services, setServices] = useState<ServiceItem[]>([]);
  const [selectedServices, setSelectedServices] = useState<Map<string, SelectedService>>(new Map());
  const [loading, setLoading] = useState(false);
  const [clientName, setClientName] = useState('');
  const [notes, setNotes] = useState('');
  const [odometer, setOdometer] = useState('');
  const [activeCategory, setActiveCategory] = useState('srs');
  
  // Price input modal
  const [priceModalVisible, setPriceModalVisible] = useState(false);
  const [currentService, setCurrentService] = useState<{service: ServiceItem, side?: string} | null>(null);
  const [priceInput, setPriceInput] = useState('');
  
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

  const openPriceModal = (service: ServiceItem, side?: string) => {
    const key = side ? `${service.id}-${side}` : service.id;
    
    // If already selected, remove it
    if (selectedServices.has(key)) {
      const newSelected = new Map(selectedServices);
      newSelected.delete(key);
      setSelectedServices(newSelected);
      return;
    }
    
    // Open modal to enter price
    setCurrentService({ service, side });
    setPriceInput('');
    setPriceModalVisible(true);
  };

  const confirmPrice = () => {
    if (!currentService) return;
    
    const price = parseFloat(priceInput);
    if (isNaN(price) || price < 0) {
      Alert.alert('Error', 'Ingrese un precio válido');
      return;
    }
    
    const { service, side } = currentService;
    const key = side ? `${service.id}-${side}` : service.id;
    const newSelected = new Map(selectedServices);
    
    newSelected.set(key, {
      key,
      service_id: service.id,
      service_name: service.name,
      quantity: 1,
      price: price,
      side: side as any,
    });
    
    setSelectedServices(newSelected);
    setPriceModalVisible(false);
    setCurrentService(null);
    setPriceInput('');
  };

  const updateServicePrice = (key: string, newPrice: string) => {
    const price = parseFloat(newPrice);
    if (isNaN(price)) return;
    
    const newSelected = new Map(selectedServices);
    const service = newSelected.get(key);
    if (service) {
      service.price = price;
      newSelected.set(key, service);
      setSelectedServices(newSelected);
    }
  };

  const removeService = (key: string) => {
    const newSelected = new Map(selectedServices);
    newSelected.delete(key);
    setSelectedServices(newSelected);
  };

  const isSelected = (serviceId: string, side?: string) => {
    const key = side ? `${serviceId}-${side}` : serviceId;
    return selectedServices.has(key);
  };

  const calculateTotal = () => {
    let total = 0;
    selectedServices.forEach((service) => {
      total += service.price * service.quantity;
    });
    return total;
  };

  const handleCreateOrder = async () => {
    if (selectedServices.size === 0) {
      Alert.alert('Error', 'Seleccione al menos un servicio');
      return;
    }

    // Validate all services have prices
    let hasInvalidPrice = false;
    selectedServices.forEach((service) => {
      if (service.price <= 0) {
        hasInvalidPrice = true;
      }
    });

    if (hasInvalidPrice) {
      Alert.alert('Error', 'Todos los servicios deben tener un precio mayor a $0');
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
      // Convert Map to array without the 'key' property
      const servicesArray = Array.from(selectedServices.values()).map(({ key, ...rest }) => rest);
      
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

  const renderService = (service: ServiceItem) => {
    const needsSide = service.name.toLowerCase().includes('izquierdo') ||
      service.name.toLowerCase().includes('derecho') ||
      service.name.toLowerCase().includes('asiento') ||
      service.name.toLowerCase().includes('knee') ||
      service.name.toLowerCase().includes('pretensioner') ||
      service.name.toLowerCase().includes('techo');

    if (!needsSide) {
      return (
        <TouchableOpacity
          key={service.id}
          style={[
            styles.serviceCard,
            isSelected(service.id) && styles.serviceCardSelected,
          ]}
          onPress={() => openPriceModal(service)}
        >
          <View style={styles.serviceInfo}>
            <Text style={styles.serviceName}>{service.name}</Text>
          </View>
          <View style={[
            styles.checkbox,
            isSelected(service.id) && styles.checkboxSelected,
          ]}>
            {isSelected(service.id) ? (
              <Ionicons name="checkmark" size={16} color="#FFFFFF" />
            ) : (
              <Ionicons name="add" size={16} color="#6B7280" />
            )}
          </View>
        </TouchableOpacity>
      );
    }

    return (
      <View key={service.id} style={styles.serviceCard}>
        <View style={styles.serviceInfo}>
          <Text style={styles.serviceName}>{service.name}</Text>
        </View>
        <View style={styles.sideButtons}>
          <TouchableOpacity
            style={[
              styles.sideButton,
              isSelected(service.id, 'left') && styles.sideButtonSelected,
            ]}
            onPress={() => openPriceModal(service, 'left')}
          >
            <Text style={[
              styles.sideButtonText,
              isSelected(service.id, 'left') && styles.sideButtonTextSelected,
            ]}>Izq</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[
              styles.sideButton,
              isSelected(service.id, 'right') && styles.sideButtonSelected,
            ]}
            onPress={() => openPriceModal(service, 'right')}
          >
            <Text style={[
              styles.sideButtonText,
              isSelected(service.id, 'right') && styles.sideButtonTextSelected,
            ]}>Der</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  };

  return (
    <View style={styles.container}>
      <ScrollView style={styles.scrollView}>
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
          <View style={styles.techSection}>
            <Text style={styles.techSectionTitle}>Asignar a Técnico</Text>
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
        <View style={styles.inputSection}>
          <Text style={styles.inputLabel}>Odómetro (opcional)</Text>
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
                size={20}
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
          <Text style={styles.servicesHint}>
            Toca un servicio para agregar y definir el precio
          </Text>
          {filteredServices.map(renderService)}
        </View>

        {/* Selected Services with Prices */}
        {selectedServices.size > 0 && (
          <View style={styles.selectedSection}>
            <Text style={styles.selectedTitle}>
              Servicios Seleccionados ({selectedServices.size})
            </Text>
            {Array.from(selectedServices.values()).map((service) => (
              <View key={service.key} style={styles.selectedItem}>
                <View style={styles.selectedInfo}>
                  <Text style={styles.selectedName}>
                    {service.service_name}
                    {service.side && ` (${service.side === 'left' ? 'Izq' : 'Der'})`}
                  </Text>
                </View>
                <View style={styles.priceInputContainer}>
                  <Text style={styles.dollarSign}>$</Text>
                  <TextInput
                    style={styles.priceInput}
                    value={service.price.toString()}
                    onChangeText={(text) => updateServicePrice(service.key, text)}
                    keyboardType="decimal-pad"
                    selectTextOnFocus
                  />
                </View>
                <TouchableOpacity
                  style={styles.removeButton}
                  onPress={() => removeService(service.key)}
                >
                  <Ionicons name="trash" size={18} color="#EF4444" />
                </TouchableOpacity>
              </View>
            ))}
          </View>
        )}

        {/* Notes */}
        <View style={styles.inputSection}>
          <Text style={styles.inputLabel}>Notas (opcional)</Text>
          <TextInput
            style={[styles.input, styles.textArea]}
            placeholder="Notas adicionales..."
            placeholderTextColor="#6B7280"
            value={notes}
            onChangeText={setNotes}
            multiline
            numberOfLines={3}
          />
        </View>
      </ScrollView>

      {/* Bottom Bar */}
      <View style={styles.bottomBar}>
        <View style={styles.totalInfo}>
          <Text style={styles.totalLabel}>Total Estimado</Text>
          <Text style={styles.totalValue}>${calculateTotal().toFixed(2)}</Text>
          <Text style={styles.servicesCount}>
            {selectedServices.size} servicio{selectedServices.size !== 1 ? 's' : ''}
          </Text>
        </View>
        <TouchableOpacity
          style={[styles.createButton, loading && styles.createButtonDisabled]}
          onPress={handleCreateOrder}
          disabled={loading}
        >
          {loading ? (
            <ActivityIndicator color="#FFFFFF" />
          ) : (
            <>
              <Ionicons name="checkmark-circle" size={24} color="#FFFFFF" />
              <Text style={styles.createButtonText}>Crear Orden</Text>
            </>
          )}
        </TouchableOpacity>
      </View>

      {/* Price Input Modal */}
      <Modal
        visible={priceModalVisible}
        animationType="fade"
        transparent={true}
        onRequestClose={() => setPriceModalVisible(false)}
      >
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.priceModalOverlay}
        >
          <View style={styles.priceModalContent}>
            <Text style={styles.priceModalTitle}>Agregar Servicio</Text>
            <Text style={styles.priceModalService}>
              {currentService?.service.name}
              {currentService?.side && ` (${currentService.side === 'left' ? 'Izquierdo' : 'Derecho'})`}
            </Text>
            
            <Text style={styles.priceModalLabel}>Precio del servicio</Text>
            <View style={styles.priceModalInputContainer}>
              <Text style={styles.priceModalDollar}>$</Text>
              <TextInput
                style={styles.priceModalInput}
                placeholder="0.00"
                placeholderTextColor="#6B7280"
                value={priceInput}
                onChangeText={setPriceInput}
                keyboardType="decimal-pad"
                autoFocus
              />
            </View>

            <View style={styles.priceModalButtons}>
              <TouchableOpacity
                style={styles.priceModalCancel}
                onPress={() => {
                  setPriceModalVisible(false);
                  setCurrentService(null);
                  setPriceInput('');
                }}
              >
                <Text style={styles.priceModalCancelText}>Cancelar</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.priceModalConfirm}
                onPress={confirmPrice}
              >
                <Text style={styles.priceModalConfirmText}>Agregar</Text>
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

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
  inputSection: {
    paddingHorizontal: 16,
    marginBottom: 16,
  },
  inputLabel: {
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
    borderRadius: 12,
    padding: 12,
    gap: 6,
  },
  categoryTabActive: {
    backgroundColor: '#3B82F6',
  },
  categoryTabText: {
    fontSize: 12,
    color: '#6B7280',
    fontWeight: '600',
  },
  categoryTabTextActive: {
    color: '#FFFFFF',
  },
  servicesList: {
    paddingHorizontal: 16,
  },
  servicesHint: {
    fontSize: 12,
    color: '#6B7280',
    marginBottom: 12,
    fontStyle: 'italic',
  },
  serviceCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 16,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#374151',
  },
  serviceCardSelected: {
    borderColor: '#3B82F6',
    backgroundColor: 'rgba(59, 130, 246, 0.1)',
  },
  serviceInfo: {
    flex: 1,
  },
  serviceName: {
    fontSize: 14,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  checkbox: {
    width: 28,
    height: 28,
    borderRadius: 8,
    borderWidth: 2,
    borderColor: '#374151',
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#374151',
  },
  checkboxSelected: {
    backgroundColor: '#3B82F6',
    borderColor: '#3B82F6',
  },
  sideButtons: {
    flexDirection: 'row',
    gap: 8,
  },
  sideButton: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: '#374151',
  },
  sideButtonSelected: {
    backgroundColor: '#3B82F6',
  },
  sideButtonText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#9CA3AF',
  },
  sideButtonTextSelected: {
    color: '#FFFFFF',
  },
  // Selected Services Section
  selectedSection: {
    backgroundColor: '#1F2937',
    margin: 16,
    borderRadius: 12,
    padding: 16,
  },
  selectedTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 16,
  },
  selectedItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#374151',
    borderRadius: 10,
    padding: 12,
    marginBottom: 8,
  },
  selectedInfo: {
    flex: 1,
  },
  selectedName: {
    fontSize: 14,
    color: '#FFFFFF',
    fontWeight: '500',
  },
  priceInputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1F2937',
    borderRadius: 8,
    paddingHorizontal: 10,
    marginRight: 8,
  },
  dollarSign: {
    fontSize: 16,
    color: '#10B981',
    fontWeight: '600',
  },
  priceInput: {
    width: 70,
    height: 36,
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
    textAlign: 'right',
  },
  removeButton: {
    padding: 8,
  },
  bottomBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#1F2937',
    padding: 16,
    borderTopWidth: 1,
    borderTopColor: '#374151',
  },
  totalInfo: {
    flex: 1,
  },
  totalLabel: {
    fontSize: 12,
    color: '#9CA3AF',
  },
  totalValue: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  servicesCount: {
    fontSize: 12,
    color: '#6B7280',
  },
  createButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#3B82F6',
    paddingHorizontal: 24,
    paddingVertical: 16,
    borderRadius: 12,
    gap: 8,
  },
  createButtonDisabled: {
    opacity: 0.7,
  },
  createButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  // Price Modal
  priceModalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.8)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  priceModalContent: {
    backgroundColor: '#1F2937',
    borderRadius: 16,
    padding: 24,
    width: '100%',
    maxWidth: 340,
  },
  priceModalTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#FFFFFF',
    textAlign: 'center',
    marginBottom: 8,
  },
  priceModalService: {
    fontSize: 14,
    color: '#9CA3AF',
    textAlign: 'center',
    marginBottom: 24,
  },
  priceModalLabel: {
    fontSize: 14,
    color: '#9CA3AF',
    marginBottom: 8,
  },
  priceModalInputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#374151',
    borderRadius: 12,
    paddingHorizontal: 16,
    marginBottom: 24,
  },
  priceModalDollar: {
    fontSize: 24,
    color: '#10B981',
    fontWeight: '700',
    marginRight: 8,
  },
  priceModalInput: {
    flex: 1,
    height: 56,
    color: '#FFFFFF',
    fontSize: 24,
    fontWeight: '700',
  },
  priceModalButtons: {
    flexDirection: 'row',
    gap: 12,
  },
  priceModalCancel: {
    flex: 1,
    backgroundColor: '#374151',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  priceModalCancelText: {
    fontSize: 16,
    color: '#9CA3AF',
    fontWeight: '600',
  },
  priceModalConfirm: {
    flex: 1,
    backgroundColor: '#3B82F6',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  priceModalConfirmText: {
    fontSize: 16,
    color: '#FFFFFF',
    fontWeight: '600',
  },
  // Tech Section Styles
  techSection: {
    backgroundColor: '#1F2937',
    marginHorizontal: 16,
    marginBottom: 16,
    borderRadius: 12,
    padding: 16,
  },
  techSectionTitle: {
    fontSize: 14,
    color: '#9CA3AF',
    marginBottom: 12,
  },
  techSelector: {
    backgroundColor: '#374151',
    borderRadius: 10,
    padding: 12,
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
  // Modal Styles
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
