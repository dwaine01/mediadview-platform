import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  RefreshControl,
  Modal,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { useFocusEffect, router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getCreditReport, createPayment, updatePayment, getWorkshop } from '../../src/services/api';
import { useAuthStore } from '../../src/store/authStore';
import * as Print from 'expo-print';
import * as Sharing from 'expo-sharing';

interface CreditOrder {
  id: string;
  vehicle: string;
  vin: string;
  services: string[];
  status: string;
  created_at: string;
  total: number;
  payment_status: string;
  payment_id?: string;
}

interface CreditClient {
  client: {
    id: string;
    name: string;
    phone?: string;
    email?: string;
    has_credit: boolean;
  };
  pending_orders: CreditOrder[];
  total_pending: number;
  total_paid: number;
  total_orders: number;
}

export default function CreditScreen() {
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';
  const [creditData, setCreditData] = useState<CreditClient[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [selectedClient, setSelectedClient] = useState<CreditClient | null>(null);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [paymentModalVisible, setPaymentModalVisible] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState<CreditOrder | null>(null);
  const [paymentMethod, setPaymentMethod] = useState('cash');
  const [generatingPdf, setGeneratingPdf] = useState(false);

  const loadData = async () => {
    try {
      const data = await getCreditReport();
      setCreditData(data);
    } catch (error) {
      console.error('Error loading credit data:', error);
    } finally {
      setLoading(false);
    }
  };

  useFocusEffect(
    useCallback(() => {
      loadData();
    }, [])
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
  };

  const openClientDetail = (client: CreditClient) => {
    setSelectedClient(client);
    setDetailModalVisible(true);
  };

  const openPaymentModal = (order: CreditOrder) => {
    setSelectedOrder(order);
    setPaymentMethod('cash');
    setPaymentModalVisible(true);
  };

  const handleMarkAsPaid = async () => {
    if (!selectedOrder) return;

    setUpdating(true);
    try {
      // If order has no payment, create one first
      if (selectedOrder.payment_status === 'sin_pago') {
        await createPayment({
          work_order_id: selectedOrder.id,
          method: paymentMethod,
          payment_status: 'pagado',
          subtotal: selectedOrder.total,
          tax: 0,
          discount: 0,
          total: selectedOrder.total,
          paid_amount: selectedOrder.total,
        });
      } else if (selectedOrder.payment_id) {
        // Update existing payment
        await updatePayment(selectedOrder.payment_id, {
          payment_status: 'pagado',
          paid_amount: selectedOrder.total,
          method: paymentMethod,
        });
      }

      Alert.alert('Éxito', 'Pago registrado correctamente');
      setPaymentModalVisible(false);
      setSelectedOrder(null);
      
      // Reload data
      await loadData();
      
      // Update selected client data
      if (selectedClient) {
        const updatedClient = creditData.find(c => c.client.id === selectedClient.client.id);
        if (updatedClient) {
          setSelectedClient(updatedClient);
        }
      }
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Error al registrar pago');
    } finally {
      setUpdating(false);
    }
  };

  const getTotalPending = () => {
    return creditData.reduce((sum, c) => sum + c.total_pending, 0);
  };

  const getTotalClients = () => {
    return creditData.filter(c => c.total_pending > 0).length;
  };

  const getTotalPendingOrders = () => {
    return creditData.reduce((sum, c) => sum + c.pending_orders.length, 0);
  };

  const generateCreditPdf = async () => {
    setGeneratingPdf(true);
    try {
      // Get workshop info
      let workshopName = 'Ohio Airbag Light Reset';
      try {
        const workshop = await getWorkshop();
        workshopName = workshop?.name || workshopName;
      } catch (e) {}

      const today = new Date().toLocaleDateString('es-ES', {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      });

      const totalPending = getTotalPending();
      const totalClients = getTotalClients();
      const totalOrders = getTotalPendingOrders();

      // Generate HTML for PDF
      const html = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: Arial, sans-serif; padding: 20px; color: #333; font-size: 12px; }
    .header { text-align: center; margin-bottom: 25px; border-bottom: 3px solid #F59E0B; padding-bottom: 15px; }
    .header h1 { font-size: 22px; color: #1F2937; margin-bottom: 5px; }
    .header h2 { font-size: 14px; color: #6B7280; font-weight: normal; }
    .header .date { font-size: 12px; color: #F59E0B; margin-top: 8px; }
    
    .summary { display: flex; justify-content: space-around; margin-bottom: 25px; }
    .summary-box { text-align: center; padding: 12px 20px; background: #FEF3C7; border-radius: 8px; border: 1px solid #F59E0B; }
    .summary-box .value { font-size: 24px; font-weight: 700; color: #D97706; }
    .summary-box .label { font-size: 11px; color: #92400E; margin-top: 4px; }
    
    .client-section { margin-bottom: 20px; page-break-inside: avoid; }
    .client-header { background: #1F2937; color: #FFF; padding: 10px 15px; border-radius: 8px 8px 0 0; display: flex; justify-content: space-between; align-items: center; }
    .client-name { font-size: 14px; font-weight: 700; }
    .client-phone { font-size: 11px; opacity: 0.8; }
    .client-total { font-size: 16px; font-weight: 700; color: #F59E0B; }
    
    .orders-table { width: 100%; border-collapse: collapse; background: #F9FAFB; }
    .orders-table th { background: #E5E7EB; padding: 8px; text-align: left; font-size: 10px; color: #374151; text-transform: uppercase; }
    .orders-table td { padding: 8px; border-bottom: 1px solid #E5E7EB; font-size: 11px; }
    .orders-table tr:last-child td { border-bottom: none; }
    .text-right { text-align: right; }
    .status-pending { color: #D97706; font-weight: 600; }
    
    .client-footer { background: #FEF3C7; padding: 10px 15px; border-radius: 0 0 8px 8px; text-align: right; }
    .client-footer span { font-size: 12px; color: #92400E; }
    .client-footer strong { font-size: 14px; color: #D97706; margin-left: 10px; }
    
    .footer { margin-top: 30px; text-align: center; padding-top: 15px; border-top: 1px solid #E5E7EB; }
    .footer p { font-size: 10px; color: #9CA3AF; }
    
    .no-data { text-align: center; padding: 40px; color: #6B7280; }
  </style>
</head>
<body>
  <div class="header">
    <h1>${workshopName}</h1>
    <h2>Reporte de Cuentas de Crédito</h2>
    <div class="date">${today}</div>
  </div>

  <div class="summary">
    <div class="summary-box">
      <div class="value">${totalClients}</div>
      <div class="label">Clientes con Saldo</div>
    </div>
    <div class="summary-box">
      <div class="value">${totalOrders}</div>
      <div class="label">Órdenes Pendientes</div>
    </div>
    <div class="summary-box">
      <div class="value">$${totalPending.toFixed(2)}</div>
      <div class="label">Total Adeudado</div>
    </div>
  </div>

  ${creditData.filter(c => c.total_pending > 0).length === 0 ? `
    <div class="no-data">
      <p>No hay cuentas de crédito pendientes</p>
    </div>
  ` : creditData.filter(c => c.total_pending > 0).map(clientData => `
    <div class="client-section">
      <div class="client-header">
        <div>
          <div class="client-name">${clientData.client.name}</div>
          ${clientData.client.phone ? `<div class="client-phone">📱 ${clientData.client.phone}</div>` : ''}
        </div>
        <div class="client-total">$${clientData.total_pending.toFixed(2)}</div>
      </div>
      
      <table class="orders-table">
        <thead>
          <tr>
            <th>Fecha</th>
            <th>Vehículo</th>
            <th>VIN</th>
            <th>Servicios</th>
            <th class="text-right">Monto</th>
            <th>Estado</th>
          </tr>
        </thead>
        <tbody>
          ${clientData.pending_orders.map(order => `
            <tr>
              <td>${new Date(order.created_at).toLocaleDateString('es-ES')}</td>
              <td>${order.vehicle}</td>
              <td>***${order.vin.slice(-6)}</td>
              <td>${order.services.slice(0, 2).join(', ')}${order.services.length > 2 ? '...' : ''}</td>
              <td class="text-right">$${order.total.toFixed(2)}</td>
              <td class="status-pending">Pendiente</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
      
      <div class="client-footer">
        <span>Total Cliente:</span>
        <strong>$${clientData.total_pending.toFixed(2)}</strong>
      </div>
    </div>
  `).join('')}

  <div class="footer">
    <p>Reporte generado el ${new Date().toLocaleString('es-ES')}</p>
    <p>${workshopName} - Sistema de Gestión de Crédito</p>
  </div>
</body>
</html>
      `;

      const { uri } = await Print.printToFileAsync({ html });
      
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(uri, {
          mimeType: 'application/pdf',
          dialogTitle: 'Reporte de Crédito PDF',
          UTI: 'com.adobe.pdf',
        });
      } else {
        Alert.alert('Error', 'No se puede compartir el archivo en este dispositivo');
      }
    } catch (error) {
      console.error('Error generating PDF:', error);
      Alert.alert('Error', 'No se pudo generar el reporte PDF');
    } finally {
      setGeneratingPdf(false);
    }
  };

  if (!isAdmin) {
    return (
      <View style={styles.container}>
        <View style={styles.centered}>
          <Ionicons name="lock-closed" size={64} color="#4B5563" />
          <Text style={styles.noAccessText}>Solo para Administradores</Text>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <ScrollView
        style={styles.scrollView}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#3B82F6" />
        }
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.headerTitle}>Cuentas por Cobrar</Text>
          <Text style={styles.headerSubtitle}>Reporte de Clientes con Crédito</Text>
        </View>

        {/* PDF Button */}
        <TouchableOpacity
          style={styles.pdfButton}
          onPress={generateCreditPdf}
          disabled={generatingPdf}
        >
          {generatingPdf ? (
            <ActivityIndicator color="#FFF" size="small" />
          ) : (
            <>
              <Ionicons name="document-text" size={20} color="#FFF" />
              <Text style={styles.pdfButtonText}>Generar Reporte PDF</Text>
            </>
          )}
        </TouchableOpacity>

        {/* Total Summary */}
        <View style={styles.totalCard}>
          <Text style={styles.totalLabel}>Total Pendiente por Cobrar</Text>
          <Text style={styles.totalValue}>${getTotalPending().toFixed(2)}</Text>
          <View style={styles.totalStats}>
            <View style={styles.totalStatItem}>
              <Ionicons name="people" size={18} color="#9CA3AF" />
              <Text style={styles.totalStatText}>{getTotalClients()} clientes</Text>
            </View>
            <View style={styles.totalStatItem}>
              <Ionicons name="car" size={18} color="#9CA3AF" />
              <Text style={styles.totalStatText}>{getTotalPendingOrders()} carros</Text>
            </View>
          </View>
        </View>

        {/* Client List - Separated by Client */}
        <Text style={styles.sectionTitle}>Deuda por Cliente</Text>
        
        {creditData.length === 0 ? (
          <View style={styles.emptyState}>
            <Ionicons name="checkmark-circle" size={48} color="#10B981" />
            <Text style={styles.emptyText}>No hay cuentas pendientes</Text>
          </View>
        ) : (
          creditData.map((item, index) => (
            <View key={index} style={styles.clientSection}>
              {/* Client Header */}
              <View style={styles.clientHeader}>
                <View style={styles.clientAvatar}>
                  <Text style={styles.clientAvatarText}>
                    {item.client.name.charAt(0).toUpperCase()}
                  </Text>
                </View>
                <View style={styles.clientInfo}>
                  <Text style={styles.clientName}>{item.client.name}</Text>
                  <Text style={styles.clientPhone}>{item.client.phone || 'Sin teléfono'}</Text>
                </View>
                <View style={styles.clientDebt}>
                  <Text style={styles.debtLabel}>Adeuda:</Text>
                  <Text style={styles.debtAmount}>${item.total_pending.toFixed(2)}</Text>
                </View>
              </View>

              {/* Orders List */}
              {item.pending_orders.length > 0 ? (
                <View style={styles.ordersList}>
                  {item.pending_orders.map((order, orderIndex) => (
                    <View key={orderIndex} style={styles.orderItem}>
                      <View style={styles.orderInfo}>
                        <View style={styles.orderVehicleRow}>
                          <Ionicons name="car" size={16} color="#3B82F6" />
                          <Text style={styles.orderVehicle}>{order.vehicle}</Text>
                        </View>
                        <Text style={styles.orderDate}>
                          {new Date(order.created_at).toLocaleDateString('es-ES')}
                        </Text>
                        <View style={styles.orderServices}>
                          {order.services.slice(0, 2).map((service, i) => (
                            <Text key={i} style={styles.orderServiceText}>• {service}</Text>
                          ))}
                          {order.services.length > 2 && (
                            <Text style={styles.moreServices}>+{order.services.length - 2} más</Text>
                          )}
                        </View>
                      </View>
                      
                      <View style={styles.orderActions}>
                        <Text style={styles.orderAmount}>${order.total.toFixed(2)}</Text>
                        <TouchableOpacity
                          style={styles.payButton}
                          onPress={() => openPaymentModal(order)}
                        >
                          <Ionicons name="card" size={16} color="#FFF" />
                          <Text style={styles.payButtonText}>Pagar</Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                  ))}
                </View>
              ) : (
                <View style={styles.noPendingOrders}>
                  <Ionicons name="checkmark-circle" size={20} color="#10B981" />
                  <Text style={styles.noPendingText}>Sin pagos pendientes</Text>
                </View>
              )}

              {/* Pay All Button */}
              {item.pending_orders.length > 1 && (
                <TouchableOpacity
                  style={styles.payAllButton}
                  onPress={() => openClientDetail(item)}
                >
                  <Ionicons name="cash" size={18} color="#10B981" />
                  <Text style={styles.payAllText}>
                    Ver todos ({item.pending_orders.length}) - Total: ${item.total_pending.toFixed(2)}
                  </Text>
                </TouchableOpacity>
              )}
            </View>
          ))
        )}

        <View style={{ height: 40 }} />
      </ScrollView>

      {/* Payment Modal */}
      <Modal visible={paymentModalVisible} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.paymentModalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Registrar Pago</Text>
              <TouchableOpacity onPress={() => setPaymentModalVisible(false)}>
                <Ionicons name="close" size={24} color="#FFF" />
              </TouchableOpacity>
            </View>

            {selectedOrder && (
              <>
                <View style={styles.paymentOrderInfo}>
                  <Text style={styles.paymentVehicle}>{selectedOrder.vehicle}</Text>
                  <Text style={styles.paymentTotal}>${selectedOrder.total.toFixed(2)}</Text>
                </View>

                <Text style={styles.methodLabel}>Método de Pago</Text>
                <View style={styles.methodOptions}>
                  {[
                    { id: 'cash', label: 'Efectivo', icon: 'cash' },
                    { id: 'zelle', label: 'Zelle', icon: 'phone-portrait' },
                    { id: 'check', label: 'Cheque', icon: 'document' },
                    { id: 'transfer', label: 'Transfer', icon: 'swap-horizontal' },
                  ].map((method) => (
                    <TouchableOpacity
                      key={method.id}
                      style={[
                        styles.methodOption,
                        paymentMethod === method.id && styles.methodOptionActive,
                      ]}
                      onPress={() => setPaymentMethod(method.id)}
                    >
                      <Ionicons
                        name={method.icon as any}
                        size={24}
                        color={paymentMethod === method.id ? '#FFF' : '#9CA3AF'}
                      />
                      <Text
                        style={[
                          styles.methodOptionText,
                          paymentMethod === method.id && styles.methodOptionTextActive,
                        ]}
                      >
                        {method.label}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>

                <TouchableOpacity
                  style={[styles.confirmPayButton, updating && { opacity: 0.7 }]}
                  onPress={handleMarkAsPaid}
                  disabled={updating}
                >
                  {updating ? (
                    <ActivityIndicator color="#FFF" />
                  ) : (
                    <>
                      <Ionicons name="checkmark-circle" size={24} color="#FFF" />
                      <Text style={styles.confirmPayText}>Confirmar Pago</Text>
                    </>
                  )}
                </TouchableOpacity>

                <TouchableOpacity
                  style={styles.cancelButton}
                  onPress={() => setPaymentModalVisible(false)}
                >
                  <Text style={styles.cancelText}>Cancelar</Text>
                </TouchableOpacity>
              </>
            )}
          </View>
        </View>
      </Modal>

      {/* Client Detail Modal */}
      <Modal visible={detailModalVisible} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.detailModalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{selectedClient?.client.name}</Text>
              <TouchableOpacity onPress={() => setDetailModalVisible(false)}>
                <Ionicons name="close" size={24} color="#FFF" />
              </TouchableOpacity>
            </View>

            <ScrollView style={styles.modalScroll}>
              {/* Summary */}
              <View style={styles.detailSummary}>
                <View style={styles.detailSummaryItem}>
                  <Text style={styles.detailSummaryLabel}>Total Adeudado</Text>
                  <Text style={styles.detailSummaryValue}>
                    ${selectedClient?.total_pending.toFixed(2)}
                  </Text>
                </View>
                <View style={styles.detailSummaryItem}>
                  <Text style={styles.detailSummaryLabel}>Ya Pagado</Text>
                  <Text style={[styles.detailSummaryValue, { color: '#10B981' }]}>
                    ${selectedClient?.total_paid.toFixed(2)}
                  </Text>
                </View>
              </View>

              {/* Contact */}
              {selectedClient?.client.phone && (
                <View style={styles.contactRow}>
                  <Ionicons name="call" size={18} color="#3B82F6" />
                  <Text style={styles.contactText}>{selectedClient.client.phone}</Text>
                </View>
              )}

              {/* All Pending Orders */}
              <Text style={styles.detailSectionTitle}>
                Carros Pendientes ({selectedClient?.pending_orders.length})
              </Text>

              {selectedClient?.pending_orders.map((order, index) => (
                <View key={index} style={styles.detailOrderCard}>
                  <View style={styles.detailOrderHeader}>
                    <View>
                      <Text style={styles.detailOrderVehicle}>{order.vehicle}</Text>
                      <Text style={styles.detailOrderVin}>VIN: {order.vin}</Text>
                    </View>
                    <Text style={styles.detailOrderAmount}>${order.total.toFixed(2)}</Text>
                  </View>

                  <View style={styles.detailOrderServices}>
                    {order.services.map((service, i) => (
                      <Text key={i} style={styles.detailServiceText}>• {service}</Text>
                    ))}
                  </View>

                  <View style={styles.detailOrderFooter}>
                    <Text style={styles.detailOrderDate}>
                      {new Date(order.created_at).toLocaleDateString('es-ES')}
                    </Text>
                    <TouchableOpacity
                      style={styles.detailPayButton}
                      onPress={() => {
                        setDetailModalVisible(false);
                        setTimeout(() => openPaymentModal(order), 300);
                      }}
                    >
                      <Ionicons name="card" size={16} color="#FFF" />
                      <Text style={styles.detailPayButtonText}>Marcar Pagado</Text>
                    </TouchableOpacity>
                  </View>
                </View>
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
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  noAccessText: {
    color: '#6B7280',
    fontSize: 18,
    marginTop: 16,
  },
  header: {
    padding: 16,
    paddingTop: 20,
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: '700',
    color: '#FFF',
  },
  headerSubtitle: {
    fontSize: 14,
    color: '#9CA3AF',
    marginTop: 4,
  },
  
  pdfButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#F59E0B',
    marginHorizontal: 16,
    marginTop: 12,
    paddingVertical: 14,
    borderRadius: 12,
    gap: 10,
  },
  pdfButtonText: {
    color: '#FFF',
    fontSize: 15,
    fontWeight: '700',
  },
  
  // Total Card
  totalCard: {
    backgroundColor: '#DC2626',
    marginHorizontal: 16,
    borderRadius: 16,
    padding: 20,
    alignItems: 'center',
  },
  totalLabel: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.8)',
  },
  totalValue: {
    fontSize: 42,
    fontWeight: '700',
    color: '#FFF',
    marginTop: 4,
  },
  totalStats: {
    flexDirection: 'row',
    marginTop: 12,
    gap: 20,
  },
  totalStatItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  totalStatText: {
    color: 'rgba(255,255,255,0.7)',
    fontSize: 13,
  },
  
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#FFF',
    marginHorizontal: 16,
    marginTop: 24,
    marginBottom: 12,
  },
  
  emptyState: {
    alignItems: 'center',
    padding: 40,
  },
  emptyText: {
    color: '#10B981',
    fontSize: 16,
    marginTop: 12,
  },
  
  // Client Section
  clientSection: {
    backgroundColor: '#1F2937',
    marginHorizontal: 16,
    marginBottom: 16,
    borderRadius: 16,
    overflow: 'hidden',
  },
  clientHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#374151',
  },
  clientAvatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: '#7C3AED',
    justifyContent: 'center',
    alignItems: 'center',
  },
  clientAvatarText: {
    color: '#FFF',
    fontSize: 20,
    fontWeight: '700',
  },
  clientInfo: {
    flex: 1,
    marginLeft: 12,
  },
  clientName: {
    color: '#FFF',
    fontSize: 17,
    fontWeight: '600',
  },
  clientPhone: {
    color: '#9CA3AF',
    fontSize: 13,
    marginTop: 2,
  },
  clientDebt: {
    alignItems: 'flex-end',
  },
  debtLabel: {
    color: '#9CA3AF',
    fontSize: 11,
  },
  debtAmount: {
    color: '#F59E0B',
    fontSize: 22,
    fontWeight: '700',
  },
  
  // Orders List
  ordersList: {
    padding: 12,
  },
  orderItem: {
    flexDirection: 'row',
    backgroundColor: '#374151',
    borderRadius: 12,
    padding: 12,
    marginBottom: 8,
  },
  orderInfo: {
    flex: 1,
  },
  orderVehicleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  orderVehicle: {
    color: '#FFF',
    fontSize: 14,
    fontWeight: '600',
  },
  orderDate: {
    color: '#6B7280',
    fontSize: 11,
    marginTop: 4,
  },
  orderServices: {
    marginTop: 6,
  },
  orderServiceText: {
    color: '#9CA3AF',
    fontSize: 12,
  },
  moreServices: {
    color: '#6B7280',
    fontSize: 11,
    marginTop: 2,
  },
  orderActions: {
    alignItems: 'flex-end',
    justifyContent: 'space-between',
  },
  orderAmount: {
    color: '#F59E0B',
    fontSize: 16,
    fontWeight: '700',
  },
  payButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#10B981',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
    gap: 4,
    marginTop: 8,
  },
  payButtonText: {
    color: '#FFF',
    fontSize: 12,
    fontWeight: '600',
  },
  
  noPendingOrders: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
    gap: 8,
  },
  noPendingText: {
    color: '#10B981',
    fontSize: 14,
  },
  
  payAllButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 14,
    borderTopWidth: 1,
    borderTopColor: '#374151',
    gap: 8,
  },
  payAllText: {
    color: '#10B981',
    fontSize: 14,
    fontWeight: '600',
  },
  
  // Payment Modal
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.85)',
    justifyContent: 'flex-end',
  },
  paymentModalContent: {
    backgroundColor: '#1F2937',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
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
  },
  paymentOrderInfo: {
    backgroundColor: '#374151',
    borderRadius: 12,
    padding: 16,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 20,
  },
  paymentVehicle: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '600',
    flex: 1,
  },
  paymentTotal: {
    color: '#10B981',
    fontSize: 24,
    fontWeight: '700',
  },
  methodLabel: {
    color: '#9CA3AF',
    fontSize: 14,
    marginBottom: 12,
  },
  methodOptions: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 24,
  },
  methodOption: {
    flex: 1,
    alignItems: 'center',
    backgroundColor: '#374151',
    paddingVertical: 16,
    borderRadius: 12,
    gap: 6,
  },
  methodOptionActive: {
    backgroundColor: '#3B82F6',
  },
  methodOptionText: {
    color: '#9CA3AF',
    fontSize: 11,
    fontWeight: '600',
  },
  methodOptionTextActive: {
    color: '#FFF',
  },
  confirmPayButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#10B981',
    paddingVertical: 16,
    borderRadius: 12,
    gap: 10,
  },
  confirmPayText: {
    color: '#FFF',
    fontSize: 18,
    fontWeight: '700',
  },
  cancelButton: {
    alignItems: 'center',
    paddingVertical: 16,
    marginTop: 8,
  },
  cancelText: {
    color: '#9CA3AF',
    fontSize: 16,
  },
  
  // Detail Modal
  detailModalContent: {
    flex: 1,
    backgroundColor: '#1F2937',
    marginTop: 60,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
  },
  modalScroll: {
    flex: 1,
    padding: 16,
  },
  detailSummary: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 16,
  },
  detailSummaryItem: {
    flex: 1,
    backgroundColor: '#374151',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  detailSummaryLabel: {
    color: '#9CA3AF',
    fontSize: 12,
  },
  detailSummaryValue: {
    color: '#F59E0B',
    fontSize: 24,
    fontWeight: '700',
    marginTop: 4,
  },
  contactRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 20,
  },
  contactText: {
    color: '#D1D5DB',
    fontSize: 15,
  },
  detailSectionTitle: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 12,
  },
  detailOrderCard: {
    backgroundColor: '#374151',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  detailOrderHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  detailOrderVehicle: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '600',
  },
  detailOrderVin: {
    color: '#6B7280',
    fontSize: 11,
    marginTop: 2,
  },
  detailOrderAmount: {
    color: '#F59E0B',
    fontSize: 20,
    fontWeight: '700',
  },
  detailOrderServices: {
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#4B5563',
  },
  detailServiceText: {
    color: '#9CA3AF',
    fontSize: 13,
    marginBottom: 4,
  },
  detailOrderFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#4B5563',
  },
  detailOrderDate: {
    color: '#6B7280',
    fontSize: 12,
  },
  detailPayButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#10B981',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 10,
    gap: 6,
  },
  detailPayButtonText: {
    color: '#FFF',
    fontSize: 14,
    fontWeight: '600',
  },
});
