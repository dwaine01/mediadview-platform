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
import { getServices, createWorkOrder, getClient, getWorkshop, getUsers } from '../../src/services/api';
import { ServiceItem, Vehicle, WorkOrderService, User } from '../../src/types';
import { useAuthStore } from '../../src/store/authStore';

export default function NewOrderScreen() {
  const params = useLocalSearchParams();
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';
  const vehicleId = params.vehicleId as string;
  const clientId = params.clientId as string;
  const vehicleData: Vehicle = params.vehicleData ? JSON.parse(params.vehicleData as string) : null;

  const [services, setServices] = useState<ServiceItem[]>([]);
  const [selectedServices, setSelectedServices] = useState<Map<string, WorkOrderService>>(new Map());
  const [loading, setLoading] = useState(false);
  const [clientName, setClientName] = useState('');
  const [notes, setNotes] = useState('');
  const [odometer, setOdometer] = useState('');
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

  const toggleService = (service: ServiceItem, side?: string) => {
    const key = side ? `${service.id}-${side}` : service.id;
    const newSelected = new Map(selectedServices);

    if (newSelected.has(key)) {
      newSelected.delete(key);
    } else {
      newSelected.set(key, {
        service_id: service.id,
        service_name: service.name,
        quantity: 1,
        price: service.default_price,
        side: side as any,
      });
    }

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
      const order = await createWorkOrder({
        vehicle_id: vehicleId,
        client_id: clientId,
        tech_id: techId,
        services: Array.from(selectedServices.values()),
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
          onPress={() => toggleService(service)}
        >
          <View style={styles.serviceInfo}>
            <Text style={styles.serviceName}>{service.name}</Text>
            <Text style={styles.servicePrice}>${service.default_price.toFixed(2)}</Text>
          </View>
          <View style={[
            styles.checkbox,
            isSelected(service.id) && styles.checkboxSelected,
          ]}>
            {isSelected(service.id) && (
              <Ionicons name="checkmark" size={16} color="#FFFFFF" />
            )}
          </View>
        </TouchableOpacity>
      );
    }

    return (
      <View key={service.id} style={styles.serviceCard}>
        <View style={styles.serviceInfo}>
          <Text style={styles.serviceName}>{service.name}</Text>
          <Text style={styles.servicePrice}>${service.default_price.toFixed(2)}</Text>
        </View>
        <View style={styles.sideButtons}>
          <TouchableOpacity
            style={[
              styles.sideButton,
              isSelected(service.id, 'left') && styles.sideButtonSelected,
            ]}
            onPress={() => toggleService(service, 'left')}
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
            onPress={() => toggleService(service, 'right')}
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

        {/* Odometer */}
        <View style={styles.inputSection}>
          <Text style={styles.inputLabel}>Odometro (opcional)</Text>
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
          {filteredServices.map(renderService)}
        </View>

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
  servicePrice: {
    fontSize: 14,
    color: '#10B981',
    marginTop: 4,
  },
  checkbox: {
    width: 24,
    height: 24,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: '#374151',
    justifyContent: 'center',
    alignItems: 'center',
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
});
