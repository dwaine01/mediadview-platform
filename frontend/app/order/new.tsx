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
import { createWorkOrder, getClient, getUsers } from '../../src/services/api';
import { Vehicle, User } from '../../src/types';
import { useAuthStore } from '../../src/store/authStore';

// Servicios predefinidos simplificados
const SERVICES = {
  srs: [
    { id: 'srs-reset', name: 'Reset módulo SRS' },
    { id: 'srs-techo', name: 'Bolsa de techo', hasSide: true },
    { id: 'srs-volante', name: 'Bolsa de volante' },
    { id: 'srs-asiento', name: 'Bolsa de asiento', hasSide: true },
    { id: 'srs-lateral', name: 'Bolsa lateral', hasSide: true },
    { id: 'srs-knee', name: 'Knee airbag', hasSide: true },
    { id: 'srs-cortina', name: 'Cortina', hasSide: true },
    { id: 'srs-sensor', name: 'Sensor ocupante' },
  ],
  cinturones: [
    { id: 'belt-conductor', name: 'Cinturón conductor' },
    { id: 'belt-pasajero', name: 'Cinturón pasajero' },
    { id: 'belt-trasero-izq', name: 'Cinturón trasero izq' },
    { id: 'belt-trasero-der', name: 'Cinturón trasero der' },
    { id: 'belt-trasero-centro', name: 'Cinturón trasero centro' },
    { id: 'belt-pretensioner', name: 'Pretensioner', hasSide: true },
  ],
  adas: [
    { id: 'adas-radar', name: 'Calibración radar frontal' },
    { id: 'adas-camara', name: 'Calibración cámara' },
    { id: 'adas-punto-ciego', name: 'Sensor punto ciego', hasSide: true },
  ],
};

export default function NewOrderScreen() {
  const params = useLocalSearchParams();
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';
  const vehicleId = params.vehicleId as string;
  const clientId = params.clientId as string;
  const vehicleData: Vehicle = params.vehicleData ? JSON.parse(params.vehicleData as string) : null;

  const [selectedServices, setSelectedServices] = useState<Set<string>>(new Set());
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
      const clientRes = await getClient(clientId);
      setClientName(clientRes.name);
      
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
    } else {
      newSelected.add(key);
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

    if (isAdmin && !selectedTech) {
      Alert.alert(
        'Asignar Técnico',
        '¿Desea asignarse la orden a usted mismo o seleccionar un técnico?',
        [
          { text: 'A mí mismo', onPress: () => submitOrder(undefined) },
          { text: 'Seleccionar técnico', onPress: () => setTechModalVisible(true) },
        ]
      );
      return;
    }

    submitOrder(selectedTech?.id);
  };

  const submitOrder = async (techId?: string) => {
    setLoading(true);
    try {
      const servicesArray: Array<{
        service_id: string;
        service_name: string;
        quantity: number;
        price: number;
        side?: string;
      }> = [];
      
      const totalServicePrice = parseFloat(totalPrice);
      const pricePerService = selectedServices.size > 0 ? totalServicePrice / selectedServices.size : 0;
      
      // Build services from selected items
      selectedServices.forEach((key) => {
        let serviceId = key;
        let side: string | undefined;
        
        if (key.includes('-izq')) {
          serviceId = key.replace('-izq', '');
          side = 'left';
        } else if (key.includes('-der')) {
          serviceId = key.replace('-der', '');
          side = 'right';
        }
        
        // Find service name
        let serviceName = '';
        Object.values(SERVICES).forEach(categoryServices => {
          const found = categoryServices.find(s => s.id === serviceId);
          if (found) serviceName = found.name;
        });
        
        if (serviceName) {
          servicesArray.push({
            service_id: serviceId,
            service_name: serviceName + (side === 'left' ? ' (Izq)' : side === 'right' ? ' (Der)' : ''),
            quantity: 1,
            price: pricePerService,
            side,
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
        { text: 'Ver Orden', onPress: () => router.replace(`/order/${order.id}`) },
      ]);
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Error al crear orden');
    } finally {
      setLoading(false);
    }
  };

  const categories = [
    { id: 'srs', name: 'SRS/Airbag', icon: 'shield' },
    { id: 'cinturones', name: 'Cinturones', icon: 'body' },
    { id: 'adas', name: 'ADAS', icon: 'radio' },
  ];

  const currentServices = SERVICES[activeCategory as keyof typeof SERVICES] || [];

  // Get selected service names for summary
  const getSelectedServiceNames = () => {
    const names: string[] = [];
    selectedServices.forEach((key) => {
      let serviceId = key;
      let sideName = '';
      
      if (key.includes('-izq')) {
        serviceId = key.replace('-izq', '');
        sideName = ' (Izq)';
      } else if (key.includes('-der')) {
        serviceId = key.replace('-der', '');
        sideName = ' (Der)';
      }
      
      Object.values(SERVICES).forEach(categoryServices => {
        const found = categoryServices.find(s => s.id === serviceId);
        if (found) names.push(found.name + sideName);
      });
    });
    return names;
  };

  const renderService = (service: { id: string; name: string; hasSide?: boolean }) => {
    if (service.hasSide) {
      const leftSelected = isSelected(service.id, 'izq');
      const rightSelected = isSelected(service.id, 'der');
      
      return (
        <View key={service.id} style={styles.serviceRow}>
          <Text style={styles.serviceName}>{service.name}</Text>
          <View style={styles.sideButtons}>
            <TouchableOpacity
              style={[styles.sideBtn, leftSelected && styles.sideBtnSelected]}
              onPress={() => toggleService(service.id, 'izq')}
            >
              <Text style={[styles.sideBtnText, leftSelected && styles.sideBtnTextSelected]}>I</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.sideBtn, rightSelected && styles.sideBtnSelected]}
              onPress={() => toggleService(service.id, 'der')}
            >
              <Text style={[styles.sideBtnText, rightSelected && styles.sideBtnTextSelected]}>D</Text>
            </TouchableOpacity>
          </View>
        </View>
      );
    }

    const selected = isSelected(service.id);
    return (
      <TouchableOpacity
        key={service.id}
        style={styles.serviceRow}
        onPress={() => toggleService(service.id)}
        activeOpacity={0.7}
      >
        <Text style={styles.serviceName}>{service.name}</Text>
        <View style={[styles.checkBox, selected && styles.checkBoxSelected]}>
          {selected && <Ionicons name="checkmark" size={14} color="#FFF" />}
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <View style={styles.container}>
      <ScrollView style={styles.scrollView} showsVerticalScrollIndicator={false}>
        {/* Vehicle & Client Info */}
        <View style={styles.infoCard}>
          <View style={styles.infoItem}>
            <Ionicons name="car" size={20} color="#3B82F6" />
            <Text style={styles.infoText}>
              {vehicleData?.year} {vehicleData?.make} {vehicleData?.model}
            </Text>
          </View>
          <View style={styles.infoItem}>
            <Ionicons name="person" size={20} color="#10B981" />
            <Text style={styles.infoText}>{clientName}</Text>
          </View>
        </View>

        {/* Tech Assignment (Admin only) */}
        {isAdmin && technicians.length > 0 && (
          <TouchableOpacity
            style={styles.techCard}
            onPress={() => setTechModalVisible(true)}
          >
            <Ionicons name="person-add" size={20} color="#6B7280" />
            <Text style={styles.techText}>
              {selectedTech ? selectedTech.name : 'Asignar técnico (opcional)'}
            </Text>
            {selectedTech && <Ionicons name="checkmark-circle" size={18} color="#10B981" />}
          </TouchableOpacity>
        )}

        {/* Odometer */}
        <View style={styles.odometerRow}>
          <Text style={styles.label}>Odómetro:</Text>
          <TextInput
            style={styles.odometerInput}
            placeholder="Millas"
            placeholderTextColor="#6B7280"
            value={odometer}
            onChangeText={setOdometer}
            keyboardType="numeric"
          />
        </View>

        {/* Category Tabs */}
        <View style={styles.tabs}>
          {categories.map((cat) => (
            <TouchableOpacity
              key={cat.id}
              style={[styles.tab, activeCategory === cat.id && styles.tabActive]}
              onPress={() => setActiveCategory(cat.id)}
            >
              <Text style={[styles.tabText, activeCategory === cat.id && styles.tabTextActive]}>
                {cat.name}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Services List - Compact */}
        <View style={styles.servicesList}>
          {currentServices.map(renderService)}
        </View>

        {/* Selected Summary */}
        {selectedServices.size > 0 && (
          <View style={styles.summaryCard}>
            <Text style={styles.summaryTitle}>Seleccionados ({selectedServices.size})</Text>
            <Text style={styles.summaryText}>
              {getSelectedServiceNames().join(' • ')}
            </Text>
          </View>
        )}

        {/* Total Price */}
        <View style={styles.priceCard}>
          <Text style={styles.priceLabel}>Precio Total</Text>
          <View style={styles.priceInputRow}>
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
        <TextInput
          style={styles.notesInput}
          placeholder="Notas adicionales (opcional)"
          placeholderTextColor="#6B7280"
          value={notes}
          onChangeText={setNotes}
          multiline
        />

        <View style={{ height: 90 }} />
      </ScrollView>

      {/* Bottom Bar */}
      <View style={styles.bottomBar}>
        <View>
          <Text style={styles.bottomCount}>{selectedServices.size} servicios</Text>
          <Text style={styles.bottomPrice}>
            ${totalPrice ? parseFloat(totalPrice).toFixed(2) : '0.00'}
          </Text>
        </View>
        <TouchableOpacity
          style={[styles.createBtn, (loading || selectedServices.size === 0) && styles.createBtnDisabled]}
          onPress={handleCreateOrder}
          disabled={loading || selectedServices.size === 0}
        >
          {loading ? (
            <ActivityIndicator color="#FFF" size="small" />
          ) : (
            <>
              <Ionicons name="checkmark" size={20} color="#FFF" />
              <Text style={styles.createBtnText}>Crear</Text>
            </>
          )}
        </TouchableOpacity>
      </View>

      {/* Tech Modal */}
      <Modal visible={techModalVisible} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Seleccionar Técnico</Text>
              <TouchableOpacity onPress={() => setTechModalVisible(false)}>
                <Ionicons name="close" size={24} color="#FFF" />
              </TouchableOpacity>
            </View>
            <ScrollView>
              {technicians.map((tech) => (
                <TouchableOpacity
                  key={tech.id}
                  style={[styles.techItem, selectedTech?.id === tech.id && styles.techItemSelected]}
                  onPress={() => {
                    setSelectedTech(tech);
                    setTechModalVisible(false);
                  }}
                >
                  <Text style={styles.techItemName}>{tech.name}</Text>
                  {selectedTech?.id === tech.id && (
                    <Ionicons name="checkmark-circle" size={22} color="#10B981" />
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
  container: { flex: 1, backgroundColor: '#111827' },
  scrollView: { flex: 1, padding: 12 },
  
  infoCard: {
    backgroundColor: '#1F2937',
    borderRadius: 10,
    padding: 12,
    marginBottom: 10,
  },
  infoItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 6,
  },
  infoText: {
    color: '#FFF',
    fontSize: 14,
    marginLeft: 10,
    fontWeight: '500',
  },
  
  techCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1F2937',
    borderRadius: 10,
    padding: 12,
    marginBottom: 10,
  },
  techText: {
    color: '#9CA3AF',
    fontSize: 14,
    marginLeft: 10,
    flex: 1,
  },
  
  odometerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  label: {
    color: '#9CA3AF',
    fontSize: 14,
    marginRight: 10,
  },
  odometerInput: {
    flex: 1,
    backgroundColor: '#1F2937',
    borderRadius: 8,
    paddingHorizontal: 12,
    height: 40,
    color: '#FFF',
    fontSize: 14,
  },
  
  tabs: {
    flexDirection: 'row',
    marginBottom: 10,
    gap: 6,
  },
  tab: {
    flex: 1,
    backgroundColor: '#1F2937',
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: 'center',
  },
  tabActive: {
    backgroundColor: '#3B82F6',
  },
  tabText: {
    color: '#6B7280',
    fontSize: 13,
    fontWeight: '600',
  },
  tabTextActive: {
    color: '#FFF',
  },
  
  servicesList: {
    backgroundColor: '#1F2937',
    borderRadius: 10,
    overflow: 'hidden',
  },
  serviceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#374151',
  },
  serviceName: {
    color: '#D1D5DB',
    fontSize: 15,
    flex: 1,
    marginRight: 12,
  },
  checkBox: {
    width: 26,
    height: 26,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: '#4B5563',
    justifyContent: 'center',
    alignItems: 'center',
    marginLeft: 8,
  },
  checkBoxSelected: {
    backgroundColor: '#3B82F6',
    borderColor: '#3B82F6',
  },
  sideButtons: {
    flexDirection: 'row',
    gap: 8,
    marginLeft: 8,
  },
  sideBtn: {
    width: 36,
    height: 36,
    borderRadius: 8,
    backgroundColor: '#374151',
    justifyContent: 'center',
    alignItems: 'center',
  },
  sideBtnSelected: {
    backgroundColor: '#3B82F6',
  },
  sideBtnText: {
    color: '#9CA3AF',
    fontSize: 15,
    fontWeight: '700',
  },
  sideBtnTextSelected: {
    color: '#FFF',
  },
  
  summaryCard: {
    backgroundColor: '#1F2937',
    borderRadius: 10,
    padding: 12,
    marginTop: 10,
  },
  summaryTitle: {
    color: '#FFF',
    fontSize: 13,
    fontWeight: '600',
    marginBottom: 6,
  },
  summaryText: {
    color: '#9CA3AF',
    fontSize: 12,
    lineHeight: 18,
  },
  
  priceCard: {
    backgroundColor: '#1F2937',
    borderRadius: 10,
    padding: 12,
    marginTop: 10,
  },
  priceLabel: {
    color: '#9CA3AF',
    fontSize: 13,
    marginBottom: 8,
  },
  priceInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#374151',
    borderRadius: 8,
    paddingHorizontal: 12,
  },
  dollarSign: {
    color: '#10B981',
    fontSize: 22,
    fontWeight: '700',
  },
  priceInput: {
    flex: 1,
    height: 50,
    color: '#FFF',
    fontSize: 22,
    fontWeight: '700',
    marginLeft: 8,
  },
  
  notesInput: {
    backgroundColor: '#1F2937',
    borderRadius: 10,
    padding: 12,
    marginTop: 10,
    color: '#FFF',
    fontSize: 14,
    minHeight: 60,
    textAlignVertical: 'top',
  },
  
  bottomBar: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#1F2937',
    padding: 12,
    borderTopWidth: 1,
    borderTopColor: '#374151',
  },
  bottomCount: {
    color: '#9CA3AF',
    fontSize: 12,
  },
  bottomPrice: {
    color: '#10B981',
    fontSize: 20,
    fontWeight: '700',
  },
  createBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#3B82F6',
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: 10,
    gap: 6,
  },
  createBtnDisabled: {
    backgroundColor: '#374151',
    opacity: 0.6,
  },
  createBtnText: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '600',
  },
  
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#1F2937',
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    maxHeight: '60%',
    padding: 16,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  modalTitle: {
    color: '#FFF',
    fontSize: 18,
    fontWeight: '600',
  },
  techItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#374151',
    borderRadius: 10,
    padding: 14,
    marginBottom: 8,
  },
  techItemSelected: {
    borderWidth: 2,
    borderColor: '#10B981',
  },
  techItemName: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '500',
  },
});
