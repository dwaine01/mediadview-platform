import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  useWindowDimensions,
  ActivityIndicator,
  TextInput,
  Linking,
  Platform,
} from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getWorkOrders, getClients, getUsers, getDailyReport } from '../../src/services/api';
import { useAuthStore } from '../../src/store/authStore';

export default function OfficePanel() {
  const { user } = useAuthStore();
  const { width } = useWindowDimensions();
  const isDesktop = width > 768;
  
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [orders, setOrders] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [technicians, setTechnicians] = useState<any[]>([]);
  const [report, setReport] = useState<any>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const today = new Date().toISOString().split('T')[0];
      const [ordersRes, clientsRes, usersRes, reportRes] = await Promise.all([
        getWorkOrders(),
        getClients(),
        getUsers(),
        getDailyReport(today),
      ]);
      
      setOrders(ordersRes || []);
      setClients(clientsRes || []);
      setTechnicians(usersRes?.filter((u: any) => u.role === 'tech') || []);
      setReport(reportRes);
    } catch (error) {
      console.error('Error loading data:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useFocusEffect(
    useCallback(() => {
      loadData();
    }, [])
  );

  const onRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const filteredOrders = orders.filter(order => {
    const matchesSearch = !searchQuery || 
      order.client?.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      order.vehicle?.make?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      order.vehicle?.vin?.toLowerCase().includes(searchQuery.toLowerCase());
    
    const matchesStatus = !statusFilter || order.status === statusFilter;
    
    return matchesSearch && matchesStatus;
  });

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'asignado': return '#6366F1';
      case 'iniciado': return '#3B82F6';
      case 'pendiente': return '#F59E0B';
      case 'terminado': return '#10B981';
      default: return '#6B7280';
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'asignado': return 'Asignado';
      case 'iniciado': return 'Iniciado';
      case 'pendiente': return 'Pendiente';
      case 'terminado': return 'Terminado';
      default: return status;
    }
  };

  const openMaps = (address: string) => {
    const url = `https://maps.google.com/maps?q=${encodeURIComponent(address)}`;
    Linking.openURL(url);
  };

  const callPhone = (phone: string) => {
    Linking.openURL(`tel:${phone}`);
  };

  if (!user || user.role !== 'admin') {
    return (
      <View style={styles.container}>
        <View style={styles.accessDenied}>
          <Ionicons name="lock-closed" size={64} color="#EF4444" />
          <Text style={styles.accessDeniedTitle}>Acceso Denegado</Text>
          <Text style={styles.accessDeniedText}>Solo administradores pueden acceder al panel de oficina</Text>
          <TouchableOpacity style={styles.backBtn} onPress={() => router.back()}>
            <Text style={styles.backBtnText}>Volver</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  if (loading) {
    return (
      <View style={[styles.container, styles.centered]}>
        <ActivityIndicator size="large" color="#3B82F6" />
        <Text style={styles.loadingText}>Cargando panel...</Text>
      </View>
    );
  }

  return (
    <ScrollView 
      style={styles.container}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#3B82F6" />}
    >
      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.headerTitle}>Panel de Oficina</Text>
          <Text style={styles.headerSubtitle}>Ohio Airbag Light Reset</Text>
        </View>
        <TouchableOpacity style={styles.newOrderBtn} onPress={() => router.push('/order/assign')}>
          <Ionicons name="add" size={20} color="#FFF" />
          <Text style={styles.newOrderBtnText}>Nueva Orden</Text>
        </TouchableOpacity>
      </View>

      {/* Stats Cards */}
      <View style={[styles.statsGrid, isDesktop && styles.statsGridDesktop]}>
        <View style={[styles.statCard, { backgroundColor: '#3B82F6' }]}>
          <Ionicons name="car" size={32} color="#FFF" />
          <Text style={styles.statValue}>{report?.total_orders || 0}</Text>
          <Text style={styles.statLabel}>Órdenes Hoy</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: '#10B981' }]}>
          <Ionicons name="checkmark-circle" size={32} color="#FFF" />
          <Text style={styles.statValue}>${report?.total_paid?.toFixed(2) || '0.00'}</Text>
          <Text style={styles.statLabel}>Cobrado</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: '#F59E0B' }]}>
          <Ionicons name="time" size={32} color="#FFF" />
          <Text style={styles.statValue}>${report?.total_pending?.toFixed(2) || '0.00'}</Text>
          <Text style={styles.statLabel}>Pendiente</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: '#8B5CF6' }]}>
          <Ionicons name="people" size={32} color="#FFF" />
          <Text style={styles.statValue}>{technicians.length}</Text>
          <Text style={styles.statLabel}>Técnicos</Text>
        </View>
      </View>

      {/* Technicians Status */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Estado de Técnicos</Text>
        <View style={[styles.techGrid, isDesktop && styles.techGridDesktop]}>
          {technicians.map(tech => {
            const techOrders = orders.filter(o => o.tech_id === tech.id && o.status !== 'terminado');
            const activeOrder = techOrders[0];
            return (
              <View key={tech.id} style={styles.techCard}>
                <View style={styles.techHeader}>
                  <View style={[styles.techAvatar, { backgroundColor: techOrders.length > 0 ? '#10B981' : '#6B7280' }]}>
                    <Ionicons name="person" size={20} color="#FFF" />
                  </View>
                  <View style={styles.techInfo}>
                    <Text style={styles.techName}>{tech.name}</Text>
                    <Text style={styles.techStatus}>
                      {techOrders.length > 0 ? `${techOrders.length} orden(es) activa(s)` : 'Disponible'}
                    </Text>
                  </View>
                </View>
                {activeOrder && (
                  <View style={styles.techCurrentOrder}>
                    <Text style={styles.techOrderVehicle}>
                      {activeOrder.vehicle?.year} {activeOrder.vehicle?.make} {activeOrder.vehicle?.model}
                    </Text>
                    <Text style={styles.techOrderClient}>{activeOrder.client?.name}</Text>
                    {activeOrder.client?.address && (
                      <TouchableOpacity onPress={() => openMaps(activeOrder.client.address)}>
                        <Text style={styles.techOrderAddress}>📍 {activeOrder.client.address}</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                )}
              </View>
            );
          })}
        </View>
      </View>

      {/* Orders Table */}
      <View style={styles.section}>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Órdenes de Trabajo</Text>
          <TextInput
            style={styles.searchInput}
            placeholder="Buscar cliente, vehículo, VIN..."
            placeholderTextColor="#6B7280"
            value={searchQuery}
            onChangeText={setSearchQuery}
          />
        </View>

        {/* Status Filters */}
        <View style={styles.filters}>
          <TouchableOpacity 
            style={[styles.filterBtn, !statusFilter && styles.filterBtnActive]}
            onPress={() => setStatusFilter(null)}
          >
            <Text style={[styles.filterText, !statusFilter && styles.filterTextActive]}>Todas</Text>
          </TouchableOpacity>
          {['asignado', 'iniciado', 'pendiente', 'terminado'].map(status => (
            <TouchableOpacity 
              key={status}
              style={[styles.filterBtn, statusFilter === status && styles.filterBtnActive]}
              onPress={() => setStatusFilter(status)}
            >
              <Text style={[styles.filterText, statusFilter === status && styles.filterTextActive]}>
                {getStatusLabel(status)}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Table Header - Desktop */}
        {isDesktop && (
          <View style={styles.tableHeader}>
            <Text style={[styles.tableHeaderCell, { flex: 2 }]}>Cliente</Text>
            <Text style={[styles.tableHeaderCell, { flex: 2 }]}>Vehículo</Text>
            <Text style={[styles.tableHeaderCell, { flex: 1 }]}>VIN</Text>
            <Text style={[styles.tableHeaderCell, { flex: 1 }]}>Técnico</Text>
            <Text style={[styles.tableHeaderCell, { flex: 1 }]}>Estado</Text>
            <Text style={[styles.tableHeaderCell, { flex: 1 }]}>Acciones</Text>
          </View>
        )}

        {/* Orders List */}
        {filteredOrders.map(order => (
          <TouchableOpacity 
            key={order.id} 
            style={[styles.orderRow, isDesktop && styles.orderRowDesktop]}
            onPress={() => router.push(`/order/${order.id}`)}
          >
            {isDesktop ? (
              <>
                <View style={[styles.tableCell, { flex: 2 }]}>
                  <Text style={styles.cellTitle}>{order.client?.name || 'Sin cliente'}</Text>
                  {order.client?.phone && (
                    <TouchableOpacity onPress={() => callPhone(order.client.phone)}>
                      <Text style={styles.cellLink}>📞 {order.client.phone}</Text>
                    </TouchableOpacity>
                  )}
                </View>
                <View style={[styles.tableCell, { flex: 2 }]}>
                  <Text style={styles.cellText}>
                    {order.vehicle?.year} {order.vehicle?.make} {order.vehicle?.model}
                  </Text>
                </View>
                <View style={[styles.tableCell, { flex: 1 }]}>
                  <Text style={styles.cellTextSmall}>
                    {order.vehicle?.vin ? `...${order.vehicle.vin.slice(-6)}` : 'Sin VIN'}
                  </Text>
                </View>
                <View style={[styles.tableCell, { flex: 1 }]}>
                  <Text style={styles.cellText}>{order.tech_name || 'Sin asignar'}</Text>
                </View>
                <View style={[styles.tableCell, { flex: 1 }]}>
                  <View style={[styles.statusBadge, { backgroundColor: getStatusColor(order.status) }]}>
                    <Text style={styles.statusText}>{getStatusLabel(order.status)}</Text>
                  </View>
                </View>
                <View style={[styles.tableCell, { flex: 1 }]}>
                  <TouchableOpacity style={styles.actionBtn}>
                    <Ionicons name="eye" size={18} color="#3B82F6" />
                  </TouchableOpacity>
                </View>
              </>
            ) : (
              <View style={styles.orderCard}>
                <View style={styles.orderCardHeader}>
                  <Text style={styles.orderCardClient}>{order.client?.name || 'Sin cliente'}</Text>
                  <View style={[styles.statusBadge, { backgroundColor: getStatusColor(order.status) }]}>
                    <Text style={styles.statusText}>{getStatusLabel(order.status)}</Text>
                  </View>
                </View>
                <Text style={styles.orderCardVehicle}>
                  {order.vehicle?.year} {order.vehicle?.make} {order.vehicle?.model}
                </Text>
                <Text style={styles.orderCardTech}>👷 {order.tech_name || 'Sin asignar'}</Text>
              </View>
            )}
          </TouchableOpacity>
        ))}

        {filteredOrders.length === 0 && (
          <View style={styles.emptyState}>
            <Ionicons name="document-text-outline" size={48} color="#6B7280" />
            <Text style={styles.emptyText}>No hay órdenes</Text>
          </View>
        )}
      </View>

      {/* Quick Actions */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Acciones Rápidas</Text>
        <View style={[styles.actionsGrid, isDesktop && styles.actionsGridDesktop]}>
          <TouchableOpacity style={styles.actionCard} onPress={() => router.push('/order/assign')}>
            <Ionicons name="add-circle" size={32} color="#3B82F6" />
            <Text style={styles.actionCardText}>Nueva Orden</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.actionCard} onPress={() => router.push('/(tabs)/clients')}>
            <Ionicons name="people" size={32} color="#10B981" />
            <Text style={styles.actionCardText}>Clientes</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.actionCard} onPress={() => router.push('/(tabs)/reports')}>
            <Ionicons name="bar-chart" size={32} color="#F59E0B" />
            <Text style={styles.actionCardText}>Reportes</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.actionCard} onPress={() => router.push('/(tabs)/credit')}>
            <Ionicons name="card" size={32} color="#8B5CF6" />
            <Text style={styles.actionCardText}>Créditos</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.actionCard} onPress={() => router.push('/(tabs)/settings')}>
            <Ionicons name="settings" size={32} color="#6B7280" />
            <Text style={styles.actionCardText}>Ajustes</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#111827',
  },
  centered: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    color: '#9CA3AF',
    marginTop: 12,
  },
  accessDenied: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  accessDeniedTitle: {
    color: '#EF4444',
    fontSize: 24,
    fontWeight: '700',
    marginTop: 16,
  },
  accessDeniedText: {
    color: '#9CA3AF',
    fontSize: 15,
    marginTop: 8,
    textAlign: 'center',
  },
  backBtn: {
    backgroundColor: '#374151',
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 8,
    marginTop: 24,
  },
  backBtnText: {
    color: '#FFF',
    fontSize: 15,
    fontWeight: '600',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 20,
    paddingTop: 50,
    backgroundColor: '#1F2937',
  },
  headerTitle: {
    color: '#FFF',
    fontSize: 24,
    fontWeight: '700',
  },
  headerSubtitle: {
    color: '#9CA3AF',
    fontSize: 14,
    marginTop: 4,
  },
  newOrderBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#3B82F6',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 8,
    gap: 6,
  },
  newOrderBtnText: {
    color: '#FFF',
    fontSize: 14,
    fontWeight: '600',
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    padding: 12,
    gap: 12,
  },
  statsGridDesktop: {
    flexWrap: 'nowrap',
    padding: 20,
  },
  statCard: {
    flex: 1,
    minWidth: 140,
    padding: 16,
    borderRadius: 12,
    alignItems: 'center',
  },
  statValue: {
    color: '#FFF',
    fontSize: 24,
    fontWeight: '700',
    marginTop: 8,
  },
  statLabel: {
    color: 'rgba(255,255,255,0.8)',
    fontSize: 12,
    marginTop: 4,
  },
  section: {
    padding: 16,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
    flexWrap: 'wrap',
    gap: 12,
  },
  sectionTitle: {
    color: '#FFF',
    fontSize: 18,
    fontWeight: '600',
  },
  searchInput: {
    backgroundColor: '#374151',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    color: '#FFF',
    minWidth: 200,
    flex: 1,
    maxWidth: 300,
  },
  filters: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 16,
  },
  filterBtn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    backgroundColor: '#374151',
  },
  filterBtnActive: {
    backgroundColor: '#3B82F6',
  },
  filterText: {
    color: '#9CA3AF',
    fontSize: 13,
  },
  filterTextActive: {
    color: '#FFF',
  },
  techGrid: {
    gap: 12,
  },
  techGridDesktop: {
    flexDirection: 'row',
    flexWrap: 'wrap',
  },
  techCard: {
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 14,
    flex: 1,
    minWidth: 280,
  },
  techHeader: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  techAvatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
  },
  techInfo: {
    marginLeft: 12,
  },
  techName: {
    color: '#FFF',
    fontSize: 15,
    fontWeight: '600',
  },
  techStatus: {
    color: '#9CA3AF',
    fontSize: 12,
    marginTop: 2,
  },
  techCurrentOrder: {
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#374151',
  },
  techOrderVehicle: {
    color: '#D1D5DB',
    fontSize: 13,
  },
  techOrderClient: {
    color: '#9CA3AF',
    fontSize: 12,
    marginTop: 4,
  },
  techOrderAddress: {
    color: '#3B82F6',
    fontSize: 12,
    marginTop: 4,
  },
  tableHeader: {
    flexDirection: 'row',
    backgroundColor: '#374151',
    padding: 12,
    borderRadius: 8,
    marginBottom: 8,
  },
  tableHeaderCell: {
    color: '#9CA3AF',
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'uppercase',
  },
  orderRow: {
    marginBottom: 8,
  },
  orderRowDesktop: {
    flexDirection: 'row',
    backgroundColor: '#1F2937',
    padding: 12,
    borderRadius: 8,
    alignItems: 'center',
  },
  tableCell: {
    paddingHorizontal: 4,
  },
  cellTitle: {
    color: '#FFF',
    fontSize: 14,
    fontWeight: '500',
  },
  cellText: {
    color: '#D1D5DB',
    fontSize: 13,
  },
  cellTextSmall: {
    color: '#9CA3AF',
    fontSize: 12,
  },
  cellLink: {
    color: '#3B82F6',
    fontSize: 12,
    marginTop: 2,
  },
  statusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusText: {
    color: '#FFF',
    fontSize: 11,
    fontWeight: '600',
  },
  actionBtn: {
    padding: 8,
  },
  orderCard: {
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 14,
  },
  orderCardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  orderCardClient: {
    color: '#FFF',
    fontSize: 15,
    fontWeight: '600',
  },
  orderCardVehicle: {
    color: '#D1D5DB',
    fontSize: 13,
    marginTop: 8,
  },
  orderCardTech: {
    color: '#9CA3AF',
    fontSize: 12,
    marginTop: 4,
  },
  emptyState: {
    alignItems: 'center',
    padding: 40,
  },
  emptyText: {
    color: '#6B7280',
    marginTop: 12,
  },
  actionsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  actionsGridDesktop: {
    flexWrap: 'nowrap',
  },
  actionCard: {
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 20,
    alignItems: 'center',
    flex: 1,
    minWidth: 100,
  },
  actionCardText: {
    color: '#D1D5DB',
    fontSize: 12,
    marginTop: 8,
    textAlign: 'center',
  },
});
