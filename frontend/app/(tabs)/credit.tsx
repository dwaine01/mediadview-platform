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
} from 'react-native';
import { useFocusEffect, router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getCreditReport } from '../../src/services/api';
import { useAuthStore } from '../../src/store/authStore';

interface CreditOrder {
  id: string;
  vehicle: string;
  vin: string;
  services: string[];
  status: string;
  created_at: string;
  total: number;
  payment_status: string;
}

interface CreditClient {
  client: {
    id: string;
    name: string;
    phone?: string;
    email?: string;
    has_credit: boolean;
    credit_limit?: number;
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
  const [selectedClient, setSelectedClient] = useState<CreditClient | null>(null);
  const [detailModalVisible, setDetailModalVisible] = useState(false);

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

  const getTotalPending = () => {
    return creditData.reduce((sum, c) => sum + c.total_pending, 0);
  };

  const getTotalClients = () => {
    return creditData.length;
  };

  const getTotalPendingOrders = () => {
    return creditData.reduce((sum, c) => sum + c.pending_orders.length, 0);
  };

  // Only admin can see this screen
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
          <Text style={styles.headerSubtitle}>Clientes con Crédito</Text>
        </View>

        {/* Summary Cards */}
        <View style={styles.summaryRow}>
          <View style={[styles.summaryCard, { backgroundColor: '#7C3AED' }]}>
            <Ionicons name="people" size={28} color="#FFF" />
            <Text style={styles.summaryValue}>{getTotalClients()}</Text>
            <Text style={styles.summaryLabel}>Clientes</Text>
          </View>
          <View style={[styles.summaryCard, { backgroundColor: '#F59E0B' }]}>
            <Ionicons name="car" size={28} color="#FFF" />
            <Text style={styles.summaryValue}>{getTotalPendingOrders()}</Text>
            <Text style={styles.summaryLabel}>Carros Pend.</Text>
          </View>
        </View>

        {/* Total Pending */}
        <View style={styles.totalPendingCard}>
          <Text style={styles.totalPendingLabel}>Total Pendiente por Cobrar</Text>
          <Text style={styles.totalPendingValue}>${getTotalPending().toFixed(2)}</Text>
        </View>

        {/* Client List */}
        <Text style={styles.sectionTitle}>Clientes con Crédito</Text>
        
        {creditData.length === 0 ? (
          <View style={styles.emptyState}>
            <Ionicons name="card-outline" size={48} color="#4B5563" />
            <Text style={styles.emptyText}>No hay clientes con cuenta de crédito</Text>
            <Text style={styles.emptySubtext}>
              Puede activar crédito a un cliente desde la pantalla de Clientes
            </Text>
          </View>
        ) : (
          creditData.map((item, index) => (
            <TouchableOpacity
              key={index}
              style={styles.clientCard}
              onPress={() => openClientDetail(item)}
            >
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
                <View style={styles.clientStats}>
                  <Text style={styles.pendingAmount}>${item.total_pending.toFixed(2)}</Text>
                  <Text style={styles.pendingCount}>
                    {item.pending_orders.length} pendiente{item.pending_orders.length !== 1 ? 's' : ''}
                  </Text>
                </View>
              </View>
              
              {item.pending_orders.length > 0 && (
                <View style={styles.ordersPreview}>
                  {item.pending_orders.slice(0, 2).map((order, i) => (
                    <View key={i} style={styles.orderPreviewItem}>
                      <Ionicons name="car" size={14} color="#6B7280" />
                      <Text style={styles.orderPreviewText} numberOfLines={1}>
                        {order.vehicle}
                      </Text>
                      <Text style={styles.orderPreviewPrice}>${order.total.toFixed(2)}</Text>
                    </View>
                  ))}
                  {item.pending_orders.length > 2 && (
                    <Text style={styles.moreOrders}>
                      +{item.pending_orders.length - 2} más...
                    </Text>
                  )}
                </View>
              )}
              
              <View style={styles.viewDetailBtn}>
                <Text style={styles.viewDetailText}>Ver Detalle</Text>
                <Ionicons name="chevron-forward" size={18} color="#3B82F6" />
              </View>
            </TouchableOpacity>
          ))
        )}

        <View style={{ height: 40 }} />
      </ScrollView>

      {/* Client Detail Modal */}
      <Modal visible={detailModalVisible} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>
                {selectedClient?.client.name}
              </Text>
              <TouchableOpacity onPress={() => setDetailModalVisible(false)}>
                <Ionicons name="close" size={24} color="#FFF" />
              </TouchableOpacity>
            </View>

            <ScrollView style={styles.modalScroll}>
              {/* Client Summary */}
              <View style={styles.modalSummary}>
                <View style={styles.modalSummaryItem}>
                  <Text style={styles.modalSummaryLabel}>Total Pendiente</Text>
                  <Text style={styles.modalSummaryValue}>
                    ${selectedClient?.total_pending.toFixed(2)}
                  </Text>
                </View>
                <View style={styles.modalSummaryItem}>
                  <Text style={styles.modalSummaryLabel}>Total Pagado</Text>
                  <Text style={[styles.modalSummaryValue, { color: '#10B981' }]}>
                    ${selectedClient?.total_paid.toFixed(2)}
                  </Text>
                </View>
              </View>

              {/* Orders List */}
              <Text style={styles.modalSectionTitle}>
                Carros Pendientes de Pago ({selectedClient?.pending_orders.length})
              </Text>

              {selectedClient?.pending_orders.map((order, index) => (
                <TouchableOpacity
                  key={index}
                  style={styles.orderCard}
                  onPress={() => {
                    setDetailModalVisible(false);
                    router.push(`/order/${order.id}`);
                  }}
                >
                  <View style={styles.orderHeader}>
                    <Ionicons name="car" size={20} color="#3B82F6" />
                    <Text style={styles.orderVehicle}>{order.vehicle}</Text>
                  </View>
                  <Text style={styles.orderVin}>VIN: {order.vin}</Text>
                  
                  <View style={styles.orderServices}>
                    {order.services.slice(0, 3).map((service, i) => (
                      <View key={i} style={styles.serviceChip}>
                        <Text style={styles.serviceChipText}>{service}</Text>
                      </View>
                    ))}
                    {order.services.length > 3 && (
                      <Text style={styles.moreServices}>+{order.services.length - 3}</Text>
                    )}
                  </View>

                  <View style={styles.orderFooter}>
                    <Text style={styles.orderDate}>
                      {new Date(order.created_at).toLocaleDateString('es-ES')}
                    </Text>
                    <Text style={styles.orderTotal}>${order.total.toFixed(2)}</Text>
                  </View>
                </TouchableOpacity>
              ))}

              {selectedClient?.pending_orders.length === 0 && (
                <View style={styles.noOrdersMessage}>
                  <Ionicons name="checkmark-circle" size={40} color="#10B981" />
                  <Text style={styles.noOrdersText}>Sin pagos pendientes</Text>
                </View>
              )}
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
  summaryRow: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    gap: 12,
  },
  summaryCard: {
    flex: 1,
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  summaryValue: {
    fontSize: 28,
    fontWeight: '700',
    color: '#FFF',
    marginTop: 8,
  },
  summaryLabel: {
    fontSize: 12,
    color: 'rgba(255,255,255,0.8)',
    marginTop: 2,
  },
  totalPendingCard: {
    backgroundColor: '#DC2626',
    marginHorizontal: 16,
    marginTop: 12,
    borderRadius: 12,
    padding: 20,
    alignItems: 'center',
  },
  totalPendingLabel: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.8)',
  },
  totalPendingValue: {
    fontSize: 36,
    fontWeight: '700',
    color: '#FFF',
    marginTop: 4,
  },
  sectionTitle: {
    fontSize: 16,
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
    color: '#9CA3AF',
    fontSize: 16,
    marginTop: 16,
  },
  emptySubtext: {
    color: '#6B7280',
    fontSize: 13,
    marginTop: 8,
    textAlign: 'center',
    paddingHorizontal: 20,
  },
  clientCard: {
    backgroundColor: '#1F2937',
    marginHorizontal: 16,
    marginBottom: 12,
    borderRadius: 12,
    padding: 16,
  },
  clientHeader: {
    flexDirection: 'row',
    alignItems: 'center',
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
    fontSize: 16,
    fontWeight: '600',
  },
  clientPhone: {
    color: '#9CA3AF',
    fontSize: 13,
    marginTop: 2,
  },
  clientStats: {
    alignItems: 'flex-end',
  },
  pendingAmount: {
    color: '#F59E0B',
    fontSize: 18,
    fontWeight: '700',
  },
  pendingCount: {
    color: '#9CA3AF',
    fontSize: 12,
    marginTop: 2,
  },
  ordersPreview: {
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#374151',
  },
  orderPreviewItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 6,
    gap: 8,
  },
  orderPreviewText: {
    flex: 1,
    color: '#D1D5DB',
    fontSize: 13,
  },
  orderPreviewPrice: {
    color: '#F59E0B',
    fontSize: 13,
    fontWeight: '600',
  },
  moreOrders: {
    color: '#6B7280',
    fontSize: 12,
    marginTop: 4,
  },
  viewDetailBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#374151',
    gap: 4,
  },
  viewDetailText: {
    color: '#3B82F6',
    fontSize: 14,
    fontWeight: '600',
  },
  // Modal
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.85)',
  },
  modalContent: {
    flex: 1,
    backgroundColor: '#1F2937',
    marginTop: 60,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#374151',
  },
  modalTitle: {
    color: '#FFF',
    fontSize: 20,
    fontWeight: '700',
  },
  modalScroll: {
    flex: 1,
    padding: 16,
  },
  modalSummary: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 20,
  },
  modalSummaryItem: {
    flex: 1,
    backgroundColor: '#374151',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  modalSummaryLabel: {
    color: '#9CA3AF',
    fontSize: 12,
  },
  modalSummaryValue: {
    color: '#F59E0B',
    fontSize: 22,
    fontWeight: '700',
    marginTop: 4,
  },
  modalSectionTitle: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 12,
  },
  orderCard: {
    backgroundColor: '#374151',
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
  },
  orderHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  orderVehicle: {
    color: '#FFF',
    fontSize: 15,
    fontWeight: '600',
    flex: 1,
  },
  orderVin: {
    color: '#6B7280',
    fontSize: 11,
    marginTop: 4,
    marginLeft: 28,
  },
  orderServices: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: 10,
    gap: 6,
  },
  serviceChip: {
    backgroundColor: '#1F2937',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 6,
  },
  serviceChipText: {
    color: '#9CA3AF',
    fontSize: 11,
  },
  moreServices: {
    color: '#6B7280',
    fontSize: 11,
    alignSelf: 'center',
  },
  orderFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#4B5563',
  },
  orderDate: {
    color: '#6B7280',
    fontSize: 12,
  },
  orderTotal: {
    color: '#F59E0B',
    fontSize: 18,
    fontWeight: '700',
  },
  noOrdersMessage: {
    alignItems: 'center',
    padding: 40,
  },
  noOrdersText: {
    color: '#10B981',
    fontSize: 16,
    marginTop: 12,
  },
});
