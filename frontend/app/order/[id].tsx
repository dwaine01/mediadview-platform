import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Alert,
  ActivityIndicator,
  TextInput,
  Modal,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { router, useLocalSearchParams, useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import {
  getWorkOrder,
  updateWorkOrder,
  createPayment,
  updatePayment,
  getWorkshop,
} from '../../src/services/api';
import { WorkOrder, Payment, Workshop } from '../../src/types';
import { StatusBadge } from '../../src/components/StatusBadge';
import { PaymentBadge } from '../../src/components/PaymentBadge';
import { useAuthStore } from '../../src/store/authStore';

export default function OrderDetailScreen() {
  const { id } = useLocalSearchParams();
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';
  const [order, setOrder] = useState<WorkOrder | null>(null);
  const [workshop, setWorkshop] = useState<Workshop | null>(null);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [paymentModalVisible, setPaymentModalVisible] = useState(false);
  const [paymentForm, setPaymentForm] = useState({
    method: 'cash',
    reference: '',
    discount: '',
  });

  // Status order for permission checking
  const statusOrder: Record<string, number> = { iniciado: 0, pendiente: 1, terminado: 2 };

  const canChangeToStatus = (newStatus: string): boolean => {
    if (!order) return false;
    if (isAdmin) return true; // Admin can change to any status
    // Technicians can only move forward
    return statusOrder[newStatus] > statusOrder[order.status];
  };

  const loadOrder = async () => {
    try {
      const [orderRes, workshopRes] = await Promise.all([
        getWorkOrder(id as string),
        getWorkshop(),
      ]);
      setOrder(orderRes);
      setWorkshop(workshopRes);
    } catch (error) {
      console.error('Error loading order:', error);
      Alert.alert('Error', 'No se pudo cargar la orden');
    } finally {
      setLoading(false);
    }
  };

  useFocusEffect(
    useCallback(() => {
      loadOrder();
    }, [id])
  );

  const handleStatusChange = async (newStatus: string) => {
    if (!order) return;

    Alert.alert(
      'Cambiar Estado',
      `¿Cambiar estado a "${newStatus}"?`,
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Confirmar',
          onPress: async () => {
            setUpdating(true);
            try {
              await updateWorkOrder(order.id, { status: newStatus });
              await loadOrder();
            } catch (error: any) {
              Alert.alert('Error', error.response?.data?.detail || 'Error al actualizar');
            } finally {
              setUpdating(false);
            }
          },
        },
      ]
    );
  };

  const calculatePayment = () => {
    if (!order || !workshop) return { subtotal: 0, tax: 0, total: 0 };

    const subtotal = order.services.reduce(
      (sum, s) => sum + s.price * s.quantity,
      0
    );
    const discount = parseFloat(paymentForm.discount) || 0;
    const taxableAmount = subtotal - discount;
    const tax = taxableAmount * (workshop.tax_rate / 100);
    const total = taxableAmount + tax;

    return { subtotal, tax, total, discount };
  };

  const handleCreatePayment = async () => {
    if (!order) return;

    const { subtotal, tax, total, discount } = calculatePayment();

    setUpdating(true);
    try {
      await createPayment({
        work_order_id: order.id,
        method: paymentForm.method,
        payment_status: 'pendiente',
        subtotal,
        tax,
        discount: discount || 0,
        total,
        paid_amount: 0,
        reference: paymentForm.reference || undefined,
      });
      setPaymentModalVisible(false);
      await loadOrder();
      Alert.alert('Éxito', 'Información de pago guardada');
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Error al guardar pago');
    } finally {
      setUpdating(false);
    }
  };

  const handlePaymentStatusChange = async () => {
    if (!order?.payment) return;

    const newStatus = order.payment.payment_status === 'pagado' ? 'pendiente' : 'pagado';
    const newPaidAmount = newStatus === 'pagado' ? order.payment.total : 0;

    Alert.alert(
      'Confirmar Pago',
      newStatus === 'pagado'
        ? `¿Marcar como pagado ($${order.payment.total.toFixed(2)})?`
        : '¿Marcar como pendiente?',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Confirmar',
          onPress: async () => {
            setUpdating(true);
            try {
              await updatePayment(order.payment!.id, {
                payment_status: newStatus,
                paid_amount: newPaidAmount,
              });
              await loadOrder();
            } catch (error: any) {
              Alert.alert('Error', error.response?.data?.detail || 'Error al actualizar');
            } finally {
              setUpdating(false);
            }
          },
        },
      ]
    );
  };

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#3B82F6" />
      </View>
    );
  }

  if (!order) {
    return (
      <View style={styles.loadingContainer}>
        <Text style={styles.errorText}>Orden no encontrada</Text>
      </View>
    );
  }

  const { subtotal, tax, total } = calculatePayment();

  return (
    <View style={styles.container}>
      <ScrollView style={styles.scrollView}>
        {/* Status Section */}
        <View style={styles.statusSection}>
          <View style={styles.statusHeader}>
            <Text style={styles.sectionTitle}>Estado de Trabajo</Text>
            <StatusBadge status={order.status} />
          </View>
          {!isAdmin && (
            <Text style={styles.permissionNote}>
              Solo puedes avanzar el estado
            </Text>
          )}
          <View style={styles.statusButtons}>
            {['iniciado', 'pendiente', 'terminado'].map((status) => {
              const canChange = canChangeToStatus(status);
              const isCurrentStatus = order.status === status;
              const isDisabled = isCurrentStatus || updating || !canChange;
              
              return (
                <TouchableOpacity
                  key={status}
                  style={[
                    styles.statusButton,
                    isCurrentStatus && styles.statusButtonActive,
                    !canChange && !isCurrentStatus && styles.statusButtonDisabled,
                  ]}
                  onPress={() => handleStatusChange(status)}
                  disabled={isDisabled}
                >
                  <Ionicons
                    name={
                      status === 'iniciado'
                        ? 'play'
                        : status === 'pendiente'
                        ? 'pause'
                        : 'checkmark'
                    }
                    size={20}
                    color={isCurrentStatus ? '#FFFFFF' : (!canChange ? '#4B5563' : '#9CA3AF')}
                  />
                  <Text
                    style={[
                      styles.statusButtonText,
                      isCurrentStatus && styles.statusButtonTextActive,
                      !canChange && !isCurrentStatus && styles.statusButtonTextDisabled,
                    ]}
                  >
                    {status.charAt(0).toUpperCase() + status.slice(1)}
                  </Text>
                  {!canChange && !isCurrentStatus && (
                    <Ionicons name="lock-closed" size={12} color="#4B5563" />
                  )}
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {/* Vehicle Info */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Ionicons name="car" size={24} color="#3B82F6" />
            <Text style={styles.cardTitle}>Vehículo</Text>
          </View>
          <View style={styles.cardContent}>
            <Text style={styles.vehicleName}>
              {order.vehicle?.year} {order.vehicle?.make} {order.vehicle?.model}
            </Text>
            <Text style={styles.vehicleDetail}>VIN: {order.vehicle?.vin}</Text>
            {order.vehicle?.trim && (
              <Text style={styles.vehicleDetail}>Trim: {order.vehicle.trim}</Text>
            )}
            {order.odometer && (
              <Text style={styles.vehicleDetail}>
                Odómetro: {order.odometer.toLocaleString()} mi
              </Text>
            )}
          </View>
        </View>

        {/* Client Info */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Ionicons name="person" size={24} color="#10B981" />
            <Text style={styles.cardTitle}>Cliente</Text>
          </View>
          <View style={styles.cardContent}>
            <Text style={styles.clientName}>{order.client?.name}</Text>
            {order.client?.phone && (
              <TouchableOpacity style={styles.contactRow}>
                <Ionicons name="call-outline" size={16} color="#6B7280" />
                <Text style={styles.contactText}>{order.client.phone}</Text>
              </TouchableOpacity>
            )}
            {order.client?.email && (
              <TouchableOpacity style={styles.contactRow}>
                <Ionicons name="mail-outline" size={16} color="#6B7280" />
                <Text style={styles.contactText}>{order.client.email}</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>

        {/* Services */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Ionicons name="construct" size={24} color="#F59E0B" />
            <Text style={styles.cardTitle}>Servicios</Text>
          </View>
          <View style={styles.servicesList}>
            {order.services.map((service, index) => (
              <View key={index} style={styles.serviceItem}>
                <View style={styles.serviceInfo}>
                  <Text style={styles.serviceName}>{service.service_name}</Text>
                  {service.side && (
                    <Text style={styles.serviceSide}>
                      ({service.side === 'left' ? 'Izq' : 'Der'})
                    </Text>
                  )}
                </View>
                <Text style={styles.servicePrice}>
                  ${(service.price * service.quantity).toFixed(2)}
                </Text>
              </View>
            ))}
          </View>
          <View style={styles.totalRow}>
            <Text style={styles.totalLabel}>Subtotal</Text>
            <Text style={styles.totalValue}>${subtotal.toFixed(2)}</Text>
          </View>
        </View>

        {/* Payment Section */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Ionicons name="card" size={24} color="#8B5CF6" />
            <Text style={styles.cardTitle}>Pago</Text>
            {order.payment && <PaymentBadge status={order.payment.payment_status} />}
          </View>

          {order.payment ? (
            <View style={styles.paymentInfo}>
              <View style={styles.paymentRow}>
                <Text style={styles.paymentLabel}>Método</Text>
                <Text style={styles.paymentValue}>
                  {order.payment.method === 'cash'
                    ? 'Efectivo'
                    : order.payment.method === 'zelle'
                    ? 'Zelle'
                    : order.payment.method === 'check'
                    ? 'Cheque'
                    : 'Otro'}
                </Text>
              </View>
              <View style={styles.paymentRow}>
                <Text style={styles.paymentLabel}>Subtotal</Text>
                <Text style={styles.paymentValue}>${order.payment.subtotal.toFixed(2)}</Text>
              </View>
              {order.payment.discount > 0 && (
                <View style={styles.paymentRow}>
                  <Text style={styles.paymentLabel}>Descuento</Text>
                  <Text style={[styles.paymentValue, { color: '#EF4444' }]}>
                    -${order.payment.discount.toFixed(2)}
                  </Text>
                </View>
              )}
              <View style={styles.paymentRow}>
                <Text style={styles.paymentLabel}>Impuesto ({workshop?.tax_rate || 0}%)</Text>
                <Text style={styles.paymentValue}>${order.payment.tax.toFixed(2)}</Text>
              </View>
              <View style={[styles.paymentRow, styles.paymentTotalRow]}>
                <Text style={styles.paymentTotalLabel}>Total</Text>
                <Text style={styles.paymentTotalValue}>${order.payment.total.toFixed(2)}</Text>
              </View>
              {order.payment.reference && (
                <View style={styles.paymentRow}>
                  <Text style={styles.paymentLabel}>Referencia</Text>
                  <Text style={styles.paymentValue}>{order.payment.reference}</Text>
                </View>
              )}

              <TouchableOpacity
                style={[
                  styles.paymentStatusButton,
                  order.payment.payment_status === 'pagado' && styles.paymentStatusButtonPaid,
                ]}
                onPress={handlePaymentStatusChange}
                disabled={updating}
              >
                <Ionicons
                  name={order.payment.payment_status === 'pagado' ? 'checkmark-circle' : 'card'}
                  size={24}
                  color="#FFFFFF"
                />
                <Text style={styles.paymentStatusButtonText}>
                  {order.payment.payment_status === 'pagado'
                    ? 'Pagado ✓'
                    : 'Marcar como Pagado'}
                </Text>
              </TouchableOpacity>
            </View>
          ) : (
            <TouchableOpacity
              style={styles.addPaymentButton}
              onPress={() => setPaymentModalVisible(true)}
            >
              <Ionicons name="add-circle" size={24} color="#3B82F6" />
              <Text style={styles.addPaymentText}>Agregar Información de Pago</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Notes */}
        {order.notes && (
          <View style={styles.card}>
            <View style={styles.cardHeader}>
              <Ionicons name="document-text" size={24} color="#6B7280" />
              <Text style={styles.cardTitle}>Notas</Text>
            </View>
            <Text style={styles.notesText}>{order.notes}</Text>
          </View>
        )}

        {/* Order Info */}
        <View style={styles.orderInfo}>
          <Text style={styles.orderInfoText}>
            Técnico: {order.tech_name}
          </Text>
          <Text style={styles.orderInfoText}>
            Creada: {new Date(order.created_at).toLocaleString('es-ES')}
          </Text>
          {order.completed_at && (
            <Text style={styles.orderInfoText}>
              Completada: {new Date(order.completed_at).toLocaleString('es-ES')}
            </Text>
          )}
        </View>
      </ScrollView>

      {/* Payment Modal */}
      <Modal
        visible={paymentModalVisible}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setPaymentModalVisible(false)}
      >
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.modalOverlay}
        >
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Información de Pago</Text>
              <TouchableOpacity onPress={() => setPaymentModalVisible(false)}>
                <Ionicons name="close" size={24} color="#FFFFFF" />
              </TouchableOpacity>
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Método de Pago</Text>
              <View style={styles.methodButtons}>
                {[
                  { id: 'cash', label: 'Efectivo', icon: 'cash' },
                  { id: 'zelle', label: 'Zelle', icon: 'phone-portrait' },
                  { id: 'check', label: 'Cheque', icon: 'document' },
                  { id: 'other', label: 'Otro', icon: 'ellipsis-horizontal' },
                ].map((method) => (
                  <TouchableOpacity
                    key={method.id}
                    style={[
                      styles.methodButton,
                      paymentForm.method === method.id && styles.methodButtonActive,
                    ]}
                    onPress={() => setPaymentForm({ ...paymentForm, method: method.id })}
                  >
                    <Ionicons
                      name={method.icon as any}
                      size={20}
                      color={paymentForm.method === method.id ? '#FFFFFF' : '#6B7280'}
                    />
                    <Text
                      style={[
                        styles.methodButtonText,
                        paymentForm.method === method.id && styles.methodButtonTextActive,
                      ]}
                    >
                      {method.label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Descuento (opcional)</Text>
              <TextInput
                style={styles.input}
                placeholder="0.00"
                placeholderTextColor="#6B7280"
                value={paymentForm.discount}
                onChangeText={(text) => setPaymentForm({ ...paymentForm, discount: text })}
                keyboardType="decimal-pad"
              />
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Referencia / # Transacción (opcional)</Text>
              <TextInput
                style={styles.input}
                placeholder="Ej: Zelle #12345"
                placeholderTextColor="#6B7280"
                value={paymentForm.reference}
                onChangeText={(text) => setPaymentForm({ ...paymentForm, reference: text })}
              />
            </View>

            {/* Payment Summary */}
            <View style={styles.paymentSummary}>
              <View style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>Subtotal</Text>
                <Text style={styles.summaryValue}>${subtotal.toFixed(2)}</Text>
              </View>
              {parseFloat(paymentForm.discount) > 0 && (
                <View style={styles.summaryRow}>
                  <Text style={styles.summaryLabel}>Descuento</Text>
                  <Text style={[styles.summaryValue, { color: '#EF4444' }]}>
                    -${parseFloat(paymentForm.discount).toFixed(2)}
                  </Text>
                </View>
              )}
              <View style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>Impuesto ({workshop?.tax_rate || 0}%)</Text>
                <Text style={styles.summaryValue}>${tax.toFixed(2)}</Text>
              </View>
              <View style={[styles.summaryRow, styles.summaryTotalRow]}>
                <Text style={styles.summaryTotalLabel}>Total</Text>
                <Text style={styles.summaryTotalValue}>${total.toFixed(2)}</Text>
              </View>
            </View>

            <TouchableOpacity
              style={[styles.saveButton, updating && styles.saveButtonDisabled]}
              onPress={handleCreatePayment}
              disabled={updating}
            >
              {updating ? (
                <ActivityIndicator color="#FFFFFF" />
              ) : (
                <Text style={styles.saveButtonText}>Guardar Pago</Text>
              )}
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Loading Overlay */}
      {updating && (
        <View style={styles.loadingOverlay}>
          <ActivityIndicator size="large" color="#3B82F6" />
        </View>
      )}
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
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#111827',
  },
  errorText: {
    fontSize: 16,
    color: '#EF4444',
  },
  statusSection: {
    backgroundColor: '#1F2937',
    margin: 16,
    borderRadius: 12,
    padding: 16,
  },
  statusHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  statusButtons: {
    flexDirection: 'row',
    gap: 8,
  },
  statusButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#374151',
    borderRadius: 12,
    padding: 12,
    gap: 6,
  },
  statusButtonActive: {
    backgroundColor: '#3B82F6',
  },
  statusButtonText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#9CA3AF',
  },
  statusButtonTextActive: {
    color: '#FFFFFF',
  },
  card: {
    backgroundColor: '#1F2937',
    marginHorizontal: 16,
    marginBottom: 12,
    borderRadius: 12,
    padding: 16,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
    gap: 12,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
    flex: 1,
  },
  cardContent: {},
  vehicleName: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  vehicleDetail: {
    fontSize: 14,
    color: '#9CA3AF',
    marginTop: 4,
  },
  clientName: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  contactRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 8,
    gap: 8,
  },
  contactText: {
    fontSize: 14,
    color: '#9CA3AF',
  },
  servicesList: {},
  serviceItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#374151',
  },
  serviceInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  serviceName: {
    fontSize: 14,
    color: '#FFFFFF',
  },
  serviceSide: {
    fontSize: 12,
    color: '#6B7280',
    marginLeft: 6,
  },
  servicePrice: {
    fontSize: 14,
    fontWeight: '600',
    color: '#10B981',
  },
  totalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#374151',
  },
  totalLabel: {
    fontSize: 16,
    fontWeight: '600',
    color: '#9CA3AF',
  },
  totalValue: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  paymentInfo: {},
  paymentRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 6,
  },
  paymentLabel: {
    fontSize: 14,
    color: '#9CA3AF',
  },
  paymentValue: {
    fontSize: 14,
    color: '#FFFFFF',
  },
  paymentTotalRow: {
    marginTop: 8,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#374151',
  },
  paymentTotalLabel: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  paymentTotalValue: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#10B981',
  },
  paymentStatusButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#3B82F6',
    borderRadius: 12,
    padding: 16,
    marginTop: 16,
    gap: 8,
  },
  paymentStatusButtonPaid: {
    backgroundColor: '#10B981',
  },
  paymentStatusButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  addPaymentButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
    backgroundColor: 'rgba(59, 130, 246, 0.1)',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#3B82F6',
    borderStyle: 'dashed',
    gap: 8,
  },
  addPaymentText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#3B82F6',
  },
  notesText: {
    fontSize: 14,
    color: '#9CA3AF',
    lineHeight: 20,
  },
  orderInfo: {
    padding: 16,
    gap: 4,
  },
  orderInfoText: {
    fontSize: 12,
    color: '#6B7280',
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
    maxHeight: '90%',
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
  methodButtons: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  methodButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#374151',
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 12,
    gap: 8,
  },
  methodButtonActive: {
    backgroundColor: '#3B82F6',
  },
  methodButtonText: {
    fontSize: 14,
    color: '#6B7280',
  },
  methodButtonTextActive: {
    color: '#FFFFFF',
    fontWeight: '600',
  },
  paymentSummary: {
    backgroundColor: '#374151',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
  },
  summaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 4,
  },
  summaryLabel: {
    fontSize: 14,
    color: '#9CA3AF',
  },
  summaryValue: {
    fontSize: 14,
    color: '#FFFFFF',
  },
  summaryTotalRow: {
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#4B5563',
  },
  summaryTotalLabel: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  summaryTotalValue: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#10B981',
  },
  saveButton: {
    backgroundColor: '#3B82F6',
    borderRadius: 12,
    height: 50,
    justifyContent: 'center',
    alignItems: 'center',
  },
  saveButtonDisabled: {
    opacity: 0.7,
  },
  saveButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
  loadingOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
});
