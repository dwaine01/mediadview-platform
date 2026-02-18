import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  RefreshControl,
  Alert,
} from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuthStore } from '../../src/store/authStore';
import { getWorkOrders, getDailyReport } from '../../src/services/api';
import { WorkOrder, DailyReport } from '../../src/types';
import { StatusBadge } from '../../src/components/StatusBadge';

export default function HomeScreen() {
  const { user } = useAuthStore();
  const [todayOrders, setTodayOrders] = useState<WorkOrder[]>([]);
  const [report, setReport] = useState<DailyReport | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadData = async () => {
    try {
      const today = new Date().toISOString().split('T')[0];
      const [ordersRes, reportRes] = await Promise.all([
        getWorkOrders({ date: today }),
        getDailyReport(today),
      ]);
      setTodayOrders(ordersRes);
      setReport(reportRes);
    } catch (error) {
      console.error('Error loading data:', error);
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

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#3B82F6" />
      }
    >
      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.greeting}>Hola, {user?.name}</Text>
          <Text style={styles.role}>
            {user?.role === 'admin' ? 'Administrador' : 'Técnico'}
          </Text>
        </View>
        <View style={styles.dateContainer}>
          <Ionicons name="calendar-outline" size={16} color="#9CA3AF" />
          <Text style={styles.date}>
            {new Date().toLocaleDateString('es-ES', {
              weekday: 'long',
              day: 'numeric',
              month: 'long',
            })}
          </Text>
        </View>
      </View>

      {/* Quick Actions */}
      <View style={styles.quickActions}>
        <TouchableOpacity
          style={styles.mainAction}
          onPress={() => router.push('/order/scan')}
        >
          <View style={styles.mainActionIcon}>
            <Ionicons name="scan" size={32} color="#FFFFFF" />
          </View>
          <Text style={styles.mainActionText}>Nueva Orden</Text>
          <Text style={styles.mainActionSubtext}>Escanear VIN</Text>
        </TouchableOpacity>
      </View>

      {/* Today's Stats */}
      {report && (
        <View style={styles.statsContainer}>
          <Text style={styles.sectionTitle}>Resumen del Día</Text>
          <View style={styles.statsGrid}>
            <View style={styles.statCard}>
              <Ionicons name="car" size={24} color="#3B82F6" />
              <Text style={styles.statValue}>{report.total_orders}</Text>
              <Text style={styles.statLabel}>Carros</Text>
            </View>
            <View style={styles.statCard}>
              <Ionicons name="cash" size={24} color="#10B981" />
              <Text style={styles.statValue}>${report.total_paid.toFixed(0)}</Text>
              <Text style={styles.statLabel}>Pagado</Text>
            </View>
            <View style={styles.statCard}>
              <Ionicons name="time" size={24} color="#F59E0B" />
              <Text style={styles.statValue}>${report.total_pending.toFixed(0)}</Text>
              <Text style={styles.statLabel}>Pendiente</Text>
            </View>
          </View>
        </View>
      )}

      {/* Status Summary */}
      {report && (
        <View style={styles.statusSummary}>
          <View style={styles.statusItem}>
            <View style={[styles.statusDot, { backgroundColor: '#3B82F6' }]} />
            <Text style={styles.statusText}>Iniciados: {report.by_status.iniciado}</Text>
          </View>
          <View style={styles.statusItem}>
            <View style={[styles.statusDot, { backgroundColor: '#F59E0B' }]} />
            <Text style={styles.statusText}>Pendientes: {report.by_status.pendiente}</Text>
          </View>
          <View style={styles.statusItem}>
            <View style={[styles.statusDot, { backgroundColor: '#10B981' }]} />
            <Text style={styles.statusText}>Terminados: {report.by_status.terminado}</Text>
          </View>
        </View>
      )}

      {/* Recent Orders */}
      <View style={styles.recentOrders}>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Órdenes de Hoy</Text>
          <TouchableOpacity onPress={() => router.push('/(tabs)/orders')}>
            <Text style={styles.seeAll}>Ver todas</Text>
          </TouchableOpacity>
        </View>

        {todayOrders.length === 0 ? (
          <View style={styles.emptyState}>
            <Ionicons name="document-text-outline" size={48} color="#4B5563" />
            <Text style={styles.emptyText}>No hay órdenes hoy</Text>
            <Text style={styles.emptySubtext}>Presiona "Nueva Orden" para comenzar</Text>
          </View>
        ) : (
          todayOrders.slice(0, 5).map((order) => (
            <TouchableOpacity
              key={order.id}
              style={styles.orderCard}
              onPress={() => router.push(`/order/${order.id}`)}
            >
              <View style={styles.orderInfo}>
                <Text style={styles.orderVehicle}>
                  {order.vehicle?.year} {order.vehicle?.make} {order.vehicle?.model}
                </Text>
                <Text style={styles.orderClient}>{order.client?.name}</Text>
                <Text style={styles.orderVin}>VIN: {order.vehicle?.vin?.slice(-6)}</Text>
              </View>
              <View style={styles.orderStatus}>
                <StatusBadge status={order.status} />
              </View>
            </TouchableOpacity>
          ))
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#111827',
  },
  header: {
    padding: 20,
    paddingTop: 10,
  },
  greeting: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  role: {
    fontSize: 14,
    color: '#9CA3AF',
    marginTop: 4,
  },
  dateContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 8,
  },
  date: {
    fontSize: 14,
    color: '#9CA3AF',
    marginLeft: 6,
    textTransform: 'capitalize',
  },
  quickActions: {
    paddingHorizontal: 20,
  },
  mainAction: {
    backgroundColor: '#3B82F6',
    borderRadius: 16,
    padding: 24,
    alignItems: 'center',
  },
  mainActionIcon: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: 'rgba(255,255,255,0.2)',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 12,
  },
  mainActionText: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  mainActionSubtext: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.8)',
    marginTop: 4,
  },
  statsContainer: {
    padding: 20,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 16,
  },
  statsGrid: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  statCard: {
    flex: 1,
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 16,
    marginHorizontal: 4,
    alignItems: 'center',
  },
  statValue: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginTop: 8,
  },
  statLabel: {
    fontSize: 12,
    color: '#9CA3AF',
    marginTop: 4,
  },
  statusSummary: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    paddingHorizontal: 20,
    marginBottom: 20,
  },
  statusItem: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 6,
  },
  statusText: {
    fontSize: 12,
    color: '#9CA3AF',
  },
  recentOrders: {
    padding: 20,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  seeAll: {
    fontSize: 14,
    color: '#3B82F6',
  },
  emptyState: {
    alignItems: 'center',
    padding: 40,
    backgroundColor: '#1F2937',
    borderRadius: 12,
  },
  emptyText: {
    fontSize: 16,
    color: '#FFFFFF',
    marginTop: 16,
  },
  emptySubtext: {
    fontSize: 14,
    color: '#6B7280',
    marginTop: 4,
  },
  orderCard: {
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  orderInfo: {
    flex: 1,
  },
  orderVehicle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  orderClient: {
    fontSize: 14,
    color: '#9CA3AF',
    marginTop: 4,
  },
  orderVin: {
    fontSize: 12,
    color: '#6B7280',
    marginTop: 2,
  },
  orderStatus: {
    marginLeft: 12,
  },
});
