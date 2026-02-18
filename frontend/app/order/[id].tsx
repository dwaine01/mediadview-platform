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
  getClient,
} from '../../src/services/api';
import { WorkOrder, Workshop, Client } from '../../src/types';
import { StatusBadge } from '../../src/components/StatusBadge';
import { PaymentBadge } from '../../src/components/PaymentBadge';
import { useAuthStore } from '../../src/store/authStore';

export default function OrderDetailScreen() {
  const { id } = useLocalSearchParams();
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';
  const [order, setOrder] = useState<WorkOrder | null>(null);
  const [workshop, setWorkshop] = useState<Workshop | null>(null);
  const [clientData, setClientData] = useState<Client | null>(null);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [paymentModalVisible, setPaymentModalVisible] = useState(false);
  const [invoiceModalVisible, setInvoiceModalVisible] = useState(false);
  const [priceModalVisible, setPriceModalVisible] = useState(false);
  const [editPrice, setEditPrice] = useState('');
  const [notes, setNotes] = useState('');
  const [notesEdited, setNotesEdited] = useState(false);
  const [paymentForm, setPaymentForm] = useState({
    method: 'cash',
    reference: '',
    discount: '',
  });

  const statusOrder: Record<string, number> = { asignado: 0, iniciado: 1, pendiente: 2, terminado: 3 };
  
  const statusLabels: Record<string, string> = {
    asignado: 'Asignado',
    iniciado: 'Iniciado',
    pendiente: 'Pendiente',
    terminado: 'Terminado',
  };

  const canChangeToStatus = (newStatus: string): boolean => {
    if (!order) return false;
    if (isAdmin) return true;
    return statusOrder[newStatus] > statusOrder[order.status];
  };

  const canEditPrice = (): boolean => {
    if (!order || !user) return false;
    if (isAdmin) return true;
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
      setNotes(orderRes.notes || '');
      
      // Load client data to check credit status
      if (orderRes.client_id) {
        try {
          const clientRes = await getClient(orderRes.client_id);
          setClientData(clientRes);
        } catch (e) {
          console.log('Could not load client data');
        }
      }
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

  // Check if client has credit account
  const isClientCredit = clientData?.has_credit || false;
  
  // Technician should not see payment section for credit clients
  const canSeePaymentSection = () => {
    if (isAdmin) return true; // Admin always sees payment
    if (isClientCredit) return false; // Tech cannot see payment for credit clients
    return order?.status === 'terminado'; // Tech only sees payment when order is completed for non-credit
  };

  const calculateTotal = () => {
    if (!order) return 0;
    return order.services.reduce((sum, s) => sum + s.price * s.quantity, 0);
  };

  const handleStatusChange = async (newStatus: string) => {
    if (!order) return;

    Alert.alert(
      'Cambiar Estado',
      `¿Cambiar estado a "${statusLabels[newStatus]}"?`,
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

  const handleSaveNotes = async () => {
    if (!order || !notesEdited) return;
    
    setUpdating(true);
    try {
      await updateWorkOrder(order.id, { notes });
      setNotesEdited(false);
      Alert.alert('Éxito', 'Comentarios guardados');
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Error al guardar');
    } finally {
      setUpdating(false);
    }
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

  // Solo permite marcar como pagado, NO revertir
  const handleMarkAsPaid = async () => {
    if (!order?.payment) return;

    // Si ya está pagado, no hacer nada
    if (order.payment.payment_status === 'pagado') {
      return;
    }

    Alert.alert(
      'Confirmar Pago',
      `¿Marcar como PAGADO?\n\nTotal: $${order.payment.total.toFixed(2)}\n\n⚠️ Esta acción no se puede revertir.`,
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Confirmar Pago',
          style: 'default',
          onPress: async () => {
            setUpdating(true);
            try {
              await updatePayment(order.payment!.id, {
                payment_status: 'pagado',
                paid_amount: order.payment!.total,
              });
              await loadOrder();
              setTimeout(() => setInvoiceModalVisible(true), 500);
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
  const isPaid = order.payment?.payment_status === 'pagado';

  return (
    <View style={styles.container}>
      <ScrollView style={styles.scrollView}>
        {/* Status Section */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Text style={styles.cardTitle}>Estado del Trabajo</Text>
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
                  style={[
                    styles.statusBtn,
                    isCurrent && styles.statusBtnActive,
                    !canChange && !isCurrent && styles.statusBtnDisabled,
                  ]}
                  onPress={() => handleStatusChange(status)}
                  disabled={isCurrent || updating || !canChange}
                >
                  <Ionicons
                    name={
                      status === 'asignado' ? 'person-add' :
                      status === 'iniciado' ? 'play-circle' :
                      status === 'pendiente' ? 'pause-circle' : 'checkmark-circle'
                    }
                    size={18}
                    color={isCurrent ? '#FFF' : (!canChange ? '#4B5563' : '#9CA3AF')}
                  />
                  <Text style={[
                    styles.statusBtnText,
                    isCurrent && styles.statusBtnTextActive,
                    !canChange && !isCurrent && styles.statusBtnTextDisabled,
                  ]}>
                    {statusLabels[status]}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
          
          {!isAdmin && (
            <Text style={styles.statusHint}>
              Solo puede avanzar el estado hacia adelante
            </Text>
          )}
        </View>

        {/* Vehicle & Client */}
        <View style={styles.card}>
          <View style={styles.infoRow}>
            <Ionicons name="car" size={22} color="#3B82F6" />
            <View style={styles.infoContent}>
              <Text style={styles.infoTitle}>
                {order.vehicle?.year} {order.vehicle?.make} {order.vehicle?.model}
              </Text>
              <Text style={styles.infoSubtitle}>VIN: {order.vehicle?.vin}</Text>
            </View>
          </View>
          
          <View style={[styles.infoRow, { marginTop: 14 }]}>
            <Ionicons name="person" size={22} color="#10B981" />
            <View style={styles.infoContent}>
              <Text style={styles.infoTitle}>{order.client?.name}</Text>
              {order.client?.phone && (
                <Text style={styles.infoSubtitle}>📱 {order.client.phone}</Text>
              )}
            </View>
          </View>
        </View>

        {/* Services */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Servicios Realizados ({order.services.length})</Text>
          <View style={styles.servicesList}>
            {order.services.map((service, i) => (
              <View key={i} style={styles.serviceItem}>
                <Ionicons name="checkmark-circle" size={18} color="#10B981" />
                <Text style={styles.serviceText}>{service.service_name}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* Price Section */}
        <View style={styles.priceCard}>
          <View style={styles.priceHeader}>
            <Text style={styles.priceLabel}>Precio Total del Trabajo</Text>
            {canEditPrice() && order.status !== 'terminado' && (
              <TouchableOpacity style={styles.editPriceBtn} onPress={openPriceModal}>
                <Ionicons name="create-outline" size={18} color="#3B82F6" />
                <Text style={styles.editPriceBtnText}>
                  {isAdmin ? 'Editar' : 'Ajustar Precio'}
                </Text>
              </TouchableOpacity>
            )}
          </View>
          <Text style={styles.priceValue}>${currentTotal.toFixed(2)}</Text>
          {!isAdmin && order.status !== 'terminado' && (
            <Text style={styles.priceHint}>
              Puede ajustar el precio según el trabajo realizado antes de marcar como terminado
            </Text>
          )}
        </View>

        {/* Comments/Notes Section */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Comentarios / Notas</Text>
          <TextInput
            style={styles.notesInput}
            placeholder="Agregar comentarios sobre el trabajo..."
            placeholderTextColor="#6B7280"
            value={notes}
            onChangeText={(text) => {
              setNotes(text);
              setNotesEdited(true);
            }}
            multiline
            numberOfLines={4}
          />
          {notesEdited && (
            <TouchableOpacity
              style={styles.saveNotesBtn}
              onPress={handleSaveNotes}
              disabled={updating}
            >
              {updating ? (
                <ActivityIndicator color="#FFF" size="small" />
              ) : (
                <>
                  <Ionicons name="save" size={18} color="#FFF" />
                  <Text style={styles.saveNotesBtnText}>Guardar Comentarios</Text>
                </>
              )}
            </TouchableOpacity>
          )}
        </View>

        {/* Credit Client Notice - For Technicians */}
        {!isAdmin && isClientCredit && (
          <View style={styles.creditNotice}>
            <Ionicons name="card" size={24} color="#7C3AED" />
            <View style={styles.creditNoticeContent}>
              <Text style={styles.creditNoticeTitle}>Cliente con Cuenta de Crédito</Text>
              <Text style={styles.creditNoticeText}>
                Este cliente tiene cuenta de crédito. El pago será gestionado por el administrador.
              </Text>
            </View>
          </View>
        )}

        {/* Payment Section - Only shown based on canSeePaymentSection */}
        {canSeePaymentSection() && (
          <View style={styles.card}>
            <View style={styles.cardHeader}>
              <Text style={styles.cardTitle}>Pago</Text>
              {order.payment && <PaymentBadge status={order.payment.payment_status} />}
            </View>

            {order.payment ? (
              <>
                <View style={styles.paymentInfo}>
                  <Text style={styles.paymentLabel}>Método:</Text>
                  <Text style={styles.paymentValue}>
                    {order.payment.method === 'cash' ? 'Efectivo' : 
                     order.payment.method === 'zelle' ? 'Zelle' : 
                     order.payment.method === 'check' ? 'Cheque' : 'Otro'}
                  </Text>
                </View>
                
                {isAdmin && (
                  <View style={styles.paymentInfo}>
                    <Text style={styles.paymentLabel}>Total:</Text>
                    <Text style={styles.paymentTotal}>${order.payment.total.toFixed(2)}</Text>
                  </View>
                )}
                
                {/* Botón de pago - Solo si NO está pagado */}
                {!isPaid ? (
                  <TouchableOpacity
                    style={styles.payBtn}
                    onPress={handleMarkAsPaid}
                    disabled={updating}
                  >
                    <Ionicons name="card" size={20} color="#FFF" />
                    <Text style={styles.payBtnText}>Marcar como Pagado</Text>
                  </TouchableOpacity>
                ) : (
                  <View style={styles.paidBadge}>
                    <Ionicons name="checkmark-circle" size={24} color="#10B981" />
                    <Text style={styles.paidBadgeText}>PAGADO</Text>
                    <Text style={styles.paidNote}>El pago ha sido confirmado</Text>
                  </View>
                )}

                {/* Botón factura - Solo si está pagado */}
                {isPaid && (
                  <TouchableOpacity style={styles.invoiceBtn} onPress={() => setInvoiceModalVisible(true)}>
                    <Ionicons name="document-text" size={20} color="#3B82F6" />
                    <Text style={styles.invoiceBtnText}>Enviar Factura al Cliente</Text>
                  </TouchableOpacity>
                )}
              </>
            ) : (
              <TouchableOpacity style={styles.addPaymentBtn} onPress={() => setPaymentModalVisible(true)}>
                <Ionicons name="add-circle" size={22} color="#3B82F6" />
                <Text style={styles.addPaymentText}>Agregar Información de Pago</Text>
              </TouchableOpacity>
            )}
          </View>
        )}

        {/* Order Info */}
        <View style={styles.orderMeta}>
          <Text style={styles.metaText}>Técnico: {order.tech_name}</Text>
          <Text style={styles.metaText}>
            Creada: {new Date(order.created_at).toLocaleString('es-ES')}
          </Text>
        </View>

        <View style={{ height: 40 }} />
      </ScrollView>

      {/* Price Edit Modal */}
      <Modal visible={priceModalVisible} animationType="fade" transparent>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>
              {isAdmin ? 'Editar Precio' : 'Ajustar Precio'}
            </Text>
            <Text style={styles.modalSubtitle}>
              Ingrese el precio total del trabajo realizado
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
                  <Text style={styles.confirmBtnText}>Guardar</Text>
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
              {[
                { id: 'cash', label: 'Efectivo', icon: 'cash' },
                { id: 'zelle', label: 'Zelle', icon: 'phone-portrait' },
                { id: 'check', label: 'Cheque', icon: 'document' },
              ].map((method) => (
                <TouchableOpacity
                  key={method.id}
                  style={[styles.methodBtn, paymentForm.method === method.id && styles.methodBtnActive]}
                  onPress={() => setPaymentForm({ ...paymentForm, method: method.id })}
                >
                  <Ionicons 
                    name={method.icon as any} 
                    size={24} 
                    color={paymentForm.method === method.id ? '#FFF' : '#9CA3AF'} 
                  />
                  <Text style={[styles.methodBtnText, paymentForm.method === method.id && styles.methodBtnTextActive]}>
                    {method.label}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={styles.inputLabel}>Referencia / # Transacción (opcional)</Text>
            <TextInput
              style={styles.input}
              placeholder="Ej: Zelle #12345"
              placeholderTextColor="#6B7280"
              value={paymentForm.reference}
              onChangeText={(text) => setPaymentForm({ ...paymentForm, reference: text })}
            />

            {/* Botón Guardar Pago - Más visible */}
            <TouchableOpacity
              style={styles.savePaymentBtn}
              onPress={handleCreatePayment}
              disabled={updating}
            >
              {updating ? (
                <ActivityIndicator color="#FFF" />
              ) : (
                <>
                  <Ionicons name="checkmark-circle" size={24} color="#FFF" />
                  <Text style={styles.savePaymentBtnText}>Guardar Pago</Text>
                </>
              )}
            </TouchableOpacity>

            {/* Botón Cancelar */}
            <TouchableOpacity
              style={styles.cancelPaymentBtn}
              onPress={() => setPaymentModalVisible(false)}
            >
              <Text style={styles.cancelPaymentBtnText}>Cancelar</Text>
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Invoice Modal */}
      <Modal visible={invoiceModalVisible} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>Enviar Factura</Text>
            <Text style={styles.modalSubtitle}>Enviar a: {order.client?.name}</Text>
            {order.client?.phone && (
              <Text style={styles.modalPhone}>📱 {order.client.phone}</Text>
            )}

            <View style={styles.shareOptions}>
              <TouchableOpacity style={styles.whatsappBtn} onPress={sendWhatsApp}>
                <Ionicons name="logo-whatsapp" size={32} color="#FFF" />
                <Text style={styles.shareText}>WhatsApp</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.smsBtn} onPress={sendSMS}>
                <Ionicons name="chatbubble" size={32} color="#FFF" />
                <Text style={styles.shareText}>SMS</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.shareBtn} onPress={shareInvoice}>
                <Ionicons name="share-social" size={32} color="#FFF" />
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
    padding: 16,
    marginBottom: 12,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 14,
  },
  cardTitle: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '700',
  },
  
  statusButtons: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  statusBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#374151',
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 10,
    gap: 6,
    minWidth: '45%',
    flex: 1,
  },
  statusBtnActive: {
    backgroundColor: '#3B82F6',
  },
  statusBtnDisabled: {
    opacity: 0.5,
  },
  statusBtnText: {
    color: '#9CA3AF',
    fontSize: 13,
    fontWeight: '600',
  },
  statusBtnTextActive: {
    color: '#FFF',
  },
  statusBtnTextDisabled: {
    color: '#4B5563',
  },
  statusHint: {
    color: '#6B7280',
    fontSize: 12,
    marginTop: 12,
    fontStyle: 'italic',
    textAlign: 'center',
  },
  
  infoRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
  },
  infoContent: {
    flex: 1,
  },
  infoTitle: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '600',
  },
  infoSubtitle: {
    color: '#9CA3AF',
    fontSize: 13,
    marginTop: 2,
  },
  
  servicesList: {
    marginTop: 12,
  },
  serviceItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#374151',
  },
  serviceText: {
    color: '#D1D5DB',
    fontSize: 14,
    flex: 1,
  },
  
  priceCard: {
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    borderWidth: 2,
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
    gap: 6,
    backgroundColor: 'rgba(59,130,246,0.15)',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
  },
  editPriceBtnText: {
    color: '#3B82F6',
    fontSize: 13,
    fontWeight: '600',
  },
  priceValue: {
    color: '#10B981',
    fontSize: 36,
    fontWeight: '700',
    marginTop: 8,
  },
  priceHint: {
    color: '#6B7280',
    fontSize: 12,
    marginTop: 10,
    lineHeight: 18,
  },
  
  notesInput: {
    backgroundColor: '#374151',
    borderRadius: 10,
    padding: 14,
    color: '#FFF',
    fontSize: 14,
    minHeight: 100,
    textAlignVertical: 'top',
    marginTop: 10,
  },
  saveNotesBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#10B981',
    paddingVertical: 12,
    borderRadius: 10,
    marginTop: 12,
    gap: 8,
  },
  saveNotesBtnText: {
    color: '#FFF',
    fontSize: 14,
    fontWeight: '600',
  },
  
  paymentInfo: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  paymentLabel: {
    color: '#9CA3AF',
    fontSize: 14,
  },
  paymentValue: {
    color: '#FFF',
    fontSize: 14,
    fontWeight: '500',
  },
  paymentTotal: {
    color: '#10B981',
    fontSize: 18,
    fontWeight: '700',
  },
  payBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#3B82F6',
    paddingVertical: 14,
    borderRadius: 10,
    marginTop: 12,
    gap: 8,
  },
  payBtnText: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '600',
  },
  paidBadge: {
    alignItems: 'center',
    backgroundColor: 'rgba(16,185,129,0.1)',
    paddingVertical: 16,
    borderRadius: 10,
    marginTop: 12,
  },
  paidBadgeText: {
    color: '#10B981',
    fontSize: 20,
    fontWeight: '700',
    marginTop: 6,
  },
  paidNote: {
    color: '#6B7280',
    fontSize: 12,
    marginTop: 4,
  },
  invoiceBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    marginTop: 12,
    paddingVertical: 14,
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
    gap: 10,
    paddingVertical: 16,
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
  
  orderMeta: {
    paddingVertical: 12,
  },
  metaText: {
    color: '#6B7280',
    fontSize: 12,
    marginBottom: 4,
  },
  
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.85)',
    justifyContent: 'center',
    padding: 20,
  },
  modalContent: {
    backgroundColor: '#1F2937',
    borderRadius: 16,
    padding: 24,
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
    marginTop: 6,
  },
  modalPhone: {
    color: '#6B7280',
    fontSize: 14,
    textAlign: 'center',
    marginTop: 4,
    marginBottom: 16,
  },
  
  priceInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#374151',
    borderRadius: 12,
    paddingHorizontal: 16,
    marginVertical: 20,
  },
  dollarSign: {
    color: '#10B981',
    fontSize: 32,
    fontWeight: '700',
  },
  priceInput: {
    flex: 1,
    height: 70,
    color: '#FFF',
    fontSize: 32,
    fontWeight: '700',
    marginLeft: 8,
  },
  
  modalButtons: {
    flexDirection: 'row',
    gap: 12,
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
    marginBottom: 10,
    marginTop: 16,
  },
  input: {
    backgroundColor: '#374151',
    borderRadius: 10,
    paddingHorizontal: 14,
    height: 50,
    color: '#FFF',
    fontSize: 16,
  },
  methodRow: {
    flexDirection: 'row',
    gap: 8,
  },
  methodBtn: {
    flex: 1,
    alignItems: 'center',
    backgroundColor: '#374151',
    paddingVertical: 14,
    borderRadius: 10,
    gap: 6,
  },
  methodBtnActive: {
    backgroundColor: '#3B82F6',
  },
  methodBtnText: {
    color: '#9CA3AF',
    fontSize: 12,
    fontWeight: '600',
  },
  methodBtnTextActive: {
    color: '#FFF',
  },
  
  // Botones del modal de pago
  savePaymentBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#10B981',
    paddingVertical: 16,
    borderRadius: 12,
    marginTop: 24,
    gap: 10,
  },
  savePaymentBtnText: {
    color: '#FFF',
    fontSize: 18,
    fontWeight: '700',
  },
  cancelPaymentBtn: {
    alignItems: 'center',
    paddingVertical: 14,
    marginTop: 8,
  },
  cancelPaymentBtnText: {
    color: '#9CA3AF',
    fontSize: 15,
  },
  
  shareOptions: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    marginVertical: 24,
  },
  whatsappBtn: {
    backgroundColor: '#25D366',
    width: 80,
    height: 80,
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
  },
  smsBtn: {
    backgroundColor: '#3B82F6',
    width: 80,
    height: 80,
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
  },
  shareBtn: {
    backgroundColor: '#8B5CF6',
    width: 80,
    height: 80,
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
  },
  shareText: {
    color: '#FFF',
    fontSize: 11,
    marginTop: 6,
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
