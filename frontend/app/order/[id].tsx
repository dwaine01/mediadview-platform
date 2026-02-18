import React, { useState, useCallback } from 'react';
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
  Linking,
  Share,
} from 'react-native';
import { useLocalSearchParams, useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import {
  getWorkOrder,
  updateWorkOrder,
  createPayment,
  updatePayment,
  getWorkshop,
} from '../../src/services/api';
import { WorkOrder, Workshop } from '../../src/types';
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
  const [invoiceModalVisible, setInvoiceModalVisible] = useState(false);
  const [priceModalVisible, setPriceModalVisible] = useState(false);
  const [editPrice, setEditPrice] = useState('');
  const [paymentForm, setPaymentForm] = useState({
    method: 'cash',
    reference: '',
    discount: '',
  });

  const statusOrder: Record<string, number> = { asignado: 0, iniciado: 1, pendiente: 2, terminado: 3 };

  const canChangeToStatus = (newStatus: string): boolean => {
    if (!order) return false;
    if (isAdmin) return true;
    return statusOrder[newStatus] > statusOrder[order.status];
  };

  // Check if tech can edit price (assigned to them and not completed)
  const canEditPrice = (): boolean => {
    if (!order || !user) return false;
    if (isAdmin) return true;
    // Tech can edit if order is assigned to them and not completed
    return order.tech_id === user.id && order.status !== 'terminado';
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

  // Calculate current total from services
  const calculateTotal = () => {
    if (!order) return 0;
    return order.services.reduce((sum, s) => sum + s.price * s.quantity, 0);
  };

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

  const openPriceModal = () => {
    setEditPrice(calculateTotal().toString());
    setPriceModalVisible(true);
  };

  const handleUpdatePrice = async () => {
    if (!order) return;
    
    const newPrice = parseFloat(editPrice);
    if (isNaN(newPrice) || newPrice < 0) {
      Alert.alert('Error', 'Ingrese un precio válido');
      return;
    }

    setUpdating(true);
    try {
      // Update all services with distributed price
      const pricePerService = order.services.length > 0 ? newPrice / order.services.length : 0;
      const updatedServices = order.services.map(s => ({
        ...s,
        price: pricePerService,
      }));

      await updateWorkOrder(order.id, { services: updatedServices });
      setPriceModalVisible(false);
      await loadOrder();
      Alert.alert('Éxito', 'Precio actualizado');
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Error al actualizar precio');
    } finally {
      setUpdating(false);
    }
  };

  const handleCreatePayment = async () => {
    if (!order || !workshop) return;

    const subtotal = calculateTotal();
    const discount = parseFloat(paymentForm.discount) || 0;
    const taxableAmount = subtotal - discount;
    const tax = taxableAmount * (workshop.tax_rate / 100);
    const total = taxableAmount + tax;

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
              
              if (newStatus === 'pagado') {
                setTimeout(() => setInvoiceModalVisible(true), 500);
              }
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

  const generateInvoiceText = () => {
    if (!order || !workshop || !order.payment) return '';
    
    const date = new Date().toLocaleDateString('es-ES', {
      day: '2-digit', month: '2-digit', year: 'numeric',
    });
    
    let invoice = `🔧 *${workshop.name}*\n`;
    invoice += `📅 Fecha: ${date}\n\n`;
    invoice += `🚗 *Vehículo:*\n`;
    invoice += `${order.vehicle?.year} ${order.vehicle?.make} ${order.vehicle?.model}\n`;
    invoice += `VIN: ${order.vehicle?.vin}\n\n`;
    invoice += `👤 *Cliente:* ${order.client?.name}\n\n`;
    invoice += `📋 *Servicios:*\n`;
    
    order.services.forEach((service, i) => {
      invoice += `${i + 1}. ${service.service_name}\n`;
    });
    
    invoice += `\n💰 *Total: $${order.payment.total.toFixed(2)}*\n`;
    invoice += `✅ PAGADO - ${order.payment.method === 'cash' ? 'Efectivo' : order.payment.method === 'zelle' ? 'Zelle' : 'Otro'}\n`;
    invoice += `\n¡Gracias por su preferencia! 🙏`;
    
    return invoice;
  };

  const sendWhatsApp = async () => {
    if (!order?.client?.phone) {
      Alert.alert('Error', 'El cliente no tiene número de teléfono');
      return;
    }
    
    const invoice = generateInvoiceText().replace(/\*/g, '');
    const phone = order.client.phone.replace(/\D/g, '');
    const phoneWithCode = phone.length === 10 ? `1${phone}` : phone;
    
    try {
      await Linking.openURL(`whatsapp://send?phone=${phoneWithCode}&text=${encodeURIComponent(invoice)}`);
      setInvoiceModalVisible(false);
    } catch {
      Alert.alert('Error', 'No se pudo abrir WhatsApp');
    }
  };

  const sendSMS = async () => {
    if (!order?.client?.phone) {
      Alert.alert('Error', 'El cliente no tiene número de teléfono');
      return;
    }
    
    const invoice = generateInvoiceText().replace(/\*/g, '').replace(/[🔧📅🚗👤📋💰✅🙏]/g, '');
    const phone = order.client.phone.replace(/\D/g, '');
    
    const url = Platform.select({
      ios: `sms:${phone}&body=${encodeURIComponent(invoice)}`,
      android: `sms:${phone}?body=${encodeURIComponent(invoice)}`,
    });
    
    try {
      if (url) await Linking.openURL(url);
      setInvoiceModalVisible(false);
    } catch {
      Alert.alert('Error', 'No se pudo abrir mensajes');
    }
  };

  const shareInvoice = async () => {
    try {
      await Share.share({ message: generateInvoiceText().replace(/\*/g, '') });
      setInvoiceModalVisible(false);
    } catch {
      Alert.alert('Error', 'No se pudo compartir');
    }
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#3B82F6" />
      </View>
    );
  }

  if (!order) {
    return (
      <View style={styles.centered}>
        <Text style={styles.errorText}>Orden no encontrada</Text>
      </View>
    );
  }

  const currentTotal = calculateTotal();

  return (
    <View style={styles.container}>
      <ScrollView style={styles.scrollView}>
        {/* Status Section */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Text style={styles.cardTitle}>Estado</Text>
            <StatusBadge status={order.status} />
          </View>
          
          <View style={styles.statusButtons}>
            {['asignado', 'iniciado', 'pendiente', 'terminado'].map((status) => {
              const canChange = canChangeToStatus(status);
              const isCurrent = order.status === status;
              
              if (status === 'asignado' && !isAdmin && order.status !== 'asignado') return null;
              
              return (
                <TouchableOpacity
                  key={status}
                  style={[styles.statusBtn, isCurrent && styles.statusBtnActive]}
                  onPress={() => handleStatusChange(status)}
                  disabled={isCurrent || updating || !canChange}
                >
                  <Text style={[styles.statusBtnText, isCurrent && styles.statusBtnTextActive]}>
                    {status === 'asignado' ? 'Asig' : status.charAt(0).toUpperCase() + status.slice(1, 4)}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {/* Vehicle & Client */}
        <View style={styles.card}>
          <View style={styles.infoRow}>
            <Ionicons name="car" size={20} color="#3B82F6" />
            <Text style={styles.infoText}>
              {order.vehicle?.year} {order.vehicle?.make} {order.vehicle?.model}
            </Text>
          </View>
          <Text style={styles.vinText}>VIN: {order.vehicle?.vin}</Text>
          <View style={[styles.infoRow, { marginTop: 12 }]}>
            <Ionicons name="person" size={20} color="#10B981" />
            <Text style={styles.infoText}>{order.client?.name}</Text>
          </View>
          {order.client?.phone && (
            <Text style={styles.phoneText}>📱 {order.client.phone}</Text>
          )}
        </View>

        {/* Services */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Servicios ({order.services.length})</Text>
          {order.services.map((service, i) => (
            <View key={i} style={styles.serviceRow}>
              <Ionicons name="checkmark-circle" size={16} color="#10B981" />
              <Text style={styles.serviceText}>{service.service_name}</Text>
            </View>
          ))}
        </View>

        {/* Price Section - Editable by Tech */}
        <View style={styles.priceCard}>
          <View style={styles.priceHeader}>
            <Text style={styles.priceLabel}>Precio Total</Text>
            {canEditPrice() && order.status !== 'terminado' && (
              <TouchableOpacity style={styles.editPriceBtn} onPress={openPriceModal}>
                <Ionicons name="pencil" size={16} color="#3B82F6" />
                <Text style={styles.editPriceBtnText}>
                  {isAdmin ? 'Editar' : 'Confirmar/Ajustar'}
                </Text>
              </TouchableOpacity>
            )}
          </View>
          <Text style={styles.priceValue}>${currentTotal.toFixed(2)}</Text>
          {!isAdmin && order.status !== 'terminado' && (
            <Text style={styles.priceHint}>
              Puede ajustar el precio según el trabajo realizado
            </Text>
          )}
        </View>

        {/* Payment Section */}
        {(isAdmin || order.status === 'terminado') && (
          <View style={styles.card}>
            <View style={styles.cardHeader}>
              <Text style={styles.cardTitle}>Pago</Text>
              {order.payment && <PaymentBadge status={order.payment.payment_status} />}
            </View>

            {order.payment ? (
              <>
                <Text style={styles.paymentMethod}>
                  Método: {order.payment.method === 'cash' ? 'Efectivo' : order.payment.method === 'zelle' ? 'Zelle' : 'Otro'}
                </Text>
                {isAdmin && (
                  <Text style={styles.paymentTotal}>Total: ${order.payment.total.toFixed(2)}</Text>
                )}
                
                <TouchableOpacity
                  style={[styles.payBtn, order.payment.payment_status === 'pagado' && styles.payBtnPaid]}
                  onPress={handlePaymentStatusChange}
                  disabled={updating}
                >
                  <Text style={styles.payBtnText}>
                    {order.payment.payment_status === 'pagado' ? '✓ Pagado' : 'Marcar Pagado'}
                  </Text>
                </TouchableOpacity>

                {order.payment.payment_status === 'pagado' && (
                  <TouchableOpacity style={styles.invoiceBtn} onPress={() => setInvoiceModalVisible(true)}>
                    <Ionicons name="document-text" size={20} color="#3B82F6" />
                    <Text style={styles.invoiceBtnText}>Enviar Factura</Text>
                  </TouchableOpacity>
                )}
              </>
            ) : (
              <TouchableOpacity style={styles.addPaymentBtn} onPress={() => setPaymentModalVisible(true)}>
                <Ionicons name="add-circle" size={20} color="#3B82F6" />
                <Text style={styles.addPaymentText}>Agregar Pago</Text>
              </TouchableOpacity>
            )}
          </View>
        )}

        {/* Notes */}
        {order.notes && (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Notas</Text>
            <Text style={styles.notesText}>{order.notes}</Text>
          </View>
        )}

        <View style={{ height: 40 }} />
      </ScrollView>

      {/* Price Edit Modal */}
      <Modal visible={priceModalVisible} animationType="fade" transparent>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>
              {isAdmin ? 'Editar Precio' : 'Confirmar Precio'}
            </Text>
            <Text style={styles.modalSubtitle}>
              {isAdmin ? 'Modifique el precio total del trabajo' : 'Confirme o ajuste el precio según el trabajo realizado'}
            </Text>
            
            <View style={styles.priceInputRow}>
              <Text style={styles.dollarSign}>$</Text>
              <TextInput
                style={styles.priceInput}
                value={editPrice}
                onChangeText={setEditPrice}
                keyboardType="decimal-pad"
                autoFocus
              />
            </View>

            <View style={styles.modalButtons}>
              <TouchableOpacity style={styles.cancelBtn} onPress={() => setPriceModalVisible(false)}>
                <Text style={styles.cancelBtnText}>Cancelar</Text>
              </TouchableOpacity>
              <TouchableOpacity 
                style={[styles.confirmBtn, updating && { opacity: 0.7 }]} 
                onPress={handleUpdatePrice}
                disabled={updating}
              >
                {updating ? (
                  <ActivityIndicator color="#FFF" size="small" />
                ) : (
                  <Text style={styles.confirmBtnText}>Confirmar</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Payment Modal */}
      <Modal visible={paymentModalVisible} animationType="slide" transparent>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Información de Pago</Text>
              <TouchableOpacity onPress={() => setPaymentModalVisible(false)}>
                <Ionicons name="close" size={24} color="#FFF" />
              </TouchableOpacity>
            </View>

            <Text style={styles.inputLabel}>Método de Pago</Text>
            <View style={styles.methodRow}>
              {['cash', 'zelle', 'check'].map((method) => (
                <TouchableOpacity
                  key={method}
                  style={[styles.methodBtn, paymentForm.method === method && styles.methodBtnActive]}
                  onPress={() => setPaymentForm({ ...paymentForm, method })}
                >
                  <Text style={[styles.methodBtnText, paymentForm.method === method && styles.methodBtnTextActive]}>
                    {method === 'cash' ? 'Efectivo' : method === 'zelle' ? 'Zelle' : 'Cheque'}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={styles.inputLabel}>Referencia (opcional)</Text>
            <TextInput
              style={styles.input}
              placeholder="# Transacción"
              placeholderTextColor="#6B7280"
              value={paymentForm.reference}
              onChangeText={(text) => setPaymentForm({ ...paymentForm, reference: text })}
            />

            <TouchableOpacity
              style={[styles.confirmBtn, { marginTop: 20 }]}
              onPress={handleCreatePayment}
              disabled={updating}
            >
              {updating ? <ActivityIndicator color="#FFF" /> : <Text style={styles.confirmBtnText}>Guardar</Text>}
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Invoice Modal */}
      <Modal visible={invoiceModalVisible} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>Enviar Factura</Text>
            <Text style={styles.modalSubtitle}>a {order.client?.name}</Text>

            <View style={styles.shareOptions}>
              <TouchableOpacity style={styles.whatsappBtn} onPress={sendWhatsApp}>
                <Ionicons name="logo-whatsapp" size={28} color="#FFF" />
                <Text style={styles.shareText}>WhatsApp</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.smsBtn} onPress={sendSMS}>
                <Ionicons name="chatbubble" size={28} color="#FFF" />
                <Text style={styles.shareText}>SMS</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.shareBtn} onPress={shareInvoice}>
                <Ionicons name="share-social" size={28} color="#FFF" />
                <Text style={styles.shareText}>Otro</Text>
              </TouchableOpacity>
            </View>

            <TouchableOpacity style={styles.closeModalBtn} onPress={() => setInvoiceModalVisible(false)}>
              <Text style={styles.closeModalText}>Cerrar</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {updating && (
        <View style={styles.loadingOverlay}>
          <ActivityIndicator size="large" color="#3B82F6" />
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#111827' },
  scrollView: { flex: 1, padding: 12 },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#111827' },
  errorText: { color: '#EF4444', fontSize: 16 },
  
  card: {
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  cardTitle: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '600',
  },
  
  statusButtons: {
    flexDirection: 'row',
    gap: 6,
  },
  statusBtn: {
    flex: 1,
    backgroundColor: '#374151',
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: 'center',
  },
  statusBtnActive: {
    backgroundColor: '#3B82F6',
  },
  statusBtnText: {
    color: '#9CA3AF',
    fontSize: 12,
    fontWeight: '600',
  },
  statusBtnTextActive: {
    color: '#FFF',
  },
  
  infoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  infoText: {
    color: '#FFF',
    fontSize: 15,
    fontWeight: '500',
  },
  vinText: {
    color: '#9CA3AF',
    fontSize: 12,
    marginLeft: 30,
    marginTop: 2,
  },
  phoneText: {
    color: '#9CA3AF',
    fontSize: 13,
    marginLeft: 30,
    marginTop: 2,
  },
  
  serviceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 8,
  },
  serviceText: {
    color: '#D1D5DB',
    fontSize: 14,
  },
  
  priceCard: {
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: '#3B82F6',
  },
  priceHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  priceLabel: {
    color: '#9CA3AF',
    fontSize: 14,
  },
  editPriceBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: 'rgba(59,130,246,0.2)',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
  },
  editPriceBtnText: {
    color: '#3B82F6',
    fontSize: 12,
    fontWeight: '600',
  },
  priceValue: {
    color: '#10B981',
    fontSize: 32,
    fontWeight: '700',
    marginTop: 8,
  },
  priceHint: {
    color: '#6B7280',
    fontSize: 12,
    marginTop: 8,
    fontStyle: 'italic',
  },
  
  paymentMethod: {
    color: '#D1D5DB',
    fontSize: 14,
  },
  paymentTotal: {
    color: '#10B981',
    fontSize: 18,
    fontWeight: '700',
    marginTop: 4,
  },
  payBtn: {
    backgroundColor: '#3B82F6',
    paddingVertical: 12,
    borderRadius: 10,
    alignItems: 'center',
    marginTop: 12,
  },
  payBtnPaid: {
    backgroundColor: '#10B981',
  },
  payBtnText: {
    color: '#FFF',
    fontSize: 15,
    fontWeight: '600',
  },
  invoiceBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    marginTop: 10,
    paddingVertical: 12,
    borderWidth: 1,
    borderColor: '#3B82F6',
    borderRadius: 10,
  },
  invoiceBtnText: {
    color: '#3B82F6',
    fontSize: 15,
    fontWeight: '600',
  },
  addPaymentBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: 14,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: '#3B82F6',
    borderRadius: 10,
  },
  addPaymentText: {
    color: '#3B82F6',
    fontSize: 15,
    fontWeight: '600',
  },
  
  notesText: {
    color: '#9CA3AF',
    fontSize: 14,
    marginTop: 8,
    lineHeight: 20,
  },
  
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.8)',
    justifyContent: 'center',
    padding: 20,
  },
  modalContent: {
    backgroundColor: '#1F2937',
    borderRadius: 16,
    padding: 20,
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
    textAlign: 'center',
  },
  modalSubtitle: {
    color: '#9CA3AF',
    fontSize: 14,
    textAlign: 'center',
    marginTop: 4,
    marginBottom: 20,
  },
  
  priceInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#374151',
    borderRadius: 12,
    paddingHorizontal: 16,
    marginBottom: 20,
  },
  dollarSign: {
    color: '#10B981',
    fontSize: 28,
    fontWeight: '700',
  },
  priceInput: {
    flex: 1,
    height: 60,
    color: '#FFF',
    fontSize: 28,
    fontWeight: '700',
    marginLeft: 8,
  },
  
  modalButtons: {
    flexDirection: 'row',
    gap: 10,
  },
  cancelBtn: {
    flex: 1,
    backgroundColor: '#374151',
    paddingVertical: 14,
    borderRadius: 10,
    alignItems: 'center',
  },
  cancelBtnText: {
    color: '#9CA3AF',
    fontSize: 16,
    fontWeight: '600',
  },
  confirmBtn: {
    flex: 1,
    backgroundColor: '#3B82F6',
    paddingVertical: 14,
    borderRadius: 10,
    alignItems: 'center',
  },
  confirmBtnText: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '600',
  },
  
  inputLabel: {
    color: '#9CA3AF',
    fontSize: 14,
    marginBottom: 8,
    marginTop: 12,
  },
  input: {
    backgroundColor: '#374151',
    borderRadius: 10,
    paddingHorizontal: 14,
    height: 48,
    color: '#FFF',
    fontSize: 16,
  },
  methodRow: {
    flexDirection: 'row',
    gap: 8,
  },
  methodBtn: {
    flex: 1,
    backgroundColor: '#374151',
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: 'center',
  },
  methodBtnActive: {
    backgroundColor: '#3B82F6',
  },
  methodBtnText: {
    color: '#9CA3AF',
    fontSize: 13,
    fontWeight: '600',
  },
  methodBtnTextActive: {
    color: '#FFF',
  },
  
  shareOptions: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    marginVertical: 20,
  },
  whatsappBtn: {
    backgroundColor: '#25D366',
    width: 70,
    height: 70,
    borderRadius: 14,
    justifyContent: 'center',
    alignItems: 'center',
  },
  smsBtn: {
    backgroundColor: '#3B82F6',
    width: 70,
    height: 70,
    borderRadius: 14,
    justifyContent: 'center',
    alignItems: 'center',
  },
  shareBtn: {
    backgroundColor: '#8B5CF6',
    width: 70,
    height: 70,
    borderRadius: 14,
    justifyContent: 'center',
    alignItems: 'center',
  },
  shareText: {
    color: '#FFF',
    fontSize: 10,
    marginTop: 4,
    fontWeight: '600',
  },
  closeModalBtn: {
    alignItems: 'center',
    paddingVertical: 14,
  },
  closeModalText: {
    color: '#9CA3AF',
    fontSize: 16,
  },
  
  loadingOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
});
