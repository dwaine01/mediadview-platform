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

// Versículos bíblicos para mostrar diariamente
const biblicalVerses = [
  { verse: "Todo lo puedo en Cristo que me fortalece.", ref: "Filipenses 4:13" },
  { verse: "Confía en el Señor con todo tu corazón.", ref: "Proverbios 3:5" },
  { verse: "El Señor es mi pastor, nada me faltará.", ref: "Salmos 23:1" },
  { verse: "Porque yo sé los planes que tengo para ustedes.", ref: "Jeremías 29:11" },
  { verse: "Esfuérzate y sé valiente, no temas.", ref: "Josué 1:9" },
  { verse: "El amor es paciente, es bondadoso.", ref: "1 Corintios 13:4" },
  { verse: "Dad gracias en todo, porque esta es la voluntad de Dios.", ref: "1 Tesalonicenses 5:18" },
  { verse: "Busquen primero el reino de Dios y su justicia.", ref: "Mateo 6:33" },
  { verse: "Yo soy el camino, la verdad y la vida.", ref: "Juan 14:6" },
  { verse: "El que comenzó la buena obra, la perfeccionará.", ref: "Filipenses 1:6" },
  { verse: "Vengan a mí todos los que están cansados.", ref: "Mateo 11:28" },
  { verse: "No temas, porque yo estoy contigo.", ref: "Isaías 41:10" },
  { verse: "Jehová es mi luz y mi salvación.", ref: "Salmos 27:1" },
  { verse: "Por fe andamos, no por vista.", ref: "2 Corintios 5:7" },
  { verse: "La paz os dejo, mi paz os doy.", ref: "Juan 14:27" },
  { verse: "Pedid, y se os dará; buscad, y hallaréis.", ref: "Mateo 7:7" },
  { verse: "En el principio era el Verbo.", ref: "Juan 1:1" },
  { verse: "Sean fuertes y valientes, no tengan miedo.", ref: "Deuteronomio 31:6" },
  { verse: "El gozo del Señor es nuestra fortaleza.", ref: "Nehemías 8:10" },
  { verse: "Porque de tal manera amó Dios al mundo.", ref: "Juan 3:16" },
  { verse: "Encomienda al Señor tu camino.", ref: "Salmos 37:5" },
  { verse: "Clama a mí, y yo te responderé.", ref: "Jeremías 33:3" },
  { verse: "Lámpara es a mis pies tu palabra.", ref: "Salmos 119:105" },
  { verse: "Más vale confiar en el Señor que en el hombre.", ref: "Salmos 118:8" },
  { verse: "Grande es tu fidelidad.", ref: "Lamentaciones 3:23" },
  { verse: "El Señor peleará por ustedes.", ref: "Éxodo 14:14" },
  { verse: "Bienaventurados los de limpio corazón.", ref: "Mateo 5:8" },
  { verse: "Jehová es bueno, fortaleza en el día de la angustia.", ref: "Nahúm 1:7" },
  { verse: "Yo estoy con ustedes todos los días.", ref: "Mateo 28:20" },
  { verse: "Dios es nuestro amparo y fortaleza.", ref: "Salmos 46:1" },
  { verse: "Sean hacedores de la palabra, no solo oidores.", ref: "Santiago 1:22" },
];

// Obtener versículo del día basado en la fecha
const getDailyVerse = () => {
  const today = new Date();
  const dayOfYear = Math.floor((today.getTime() - new Date(today.getFullYear(), 0, 0).getTime()) / 86400000);
  return biblicalVerses[dayOfYear % biblicalVerses.length];
};

export default function HomeScreen() {
  const { user } = useAuthStore();
  const [todayOrders, setTodayOrders] = useState<WorkOrder[]>([]);
  const [report, setReport] = useState<DailyReport | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const dailyVerse = getDailyVerse();

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

      {/* Daily Bible Verse */}
      <View style={styles.verseContainer}>
        <Ionicons name="book" size={16} color="#D4A017" />
        <View style={styles.verseContent}>
          <Text style={styles.verseText}>"{dailyVerse.verse}"</Text>
          <Text style={styles.verseRef}>{dailyVerse.ref}</Text>
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

      {/* Today's Stats - Different for Admin vs Tech */}
      {report && (
        <View style={styles.statsContainer}>
          <Text style={styles.sectionTitle}>Resumen del Día</Text>
          {user?.role === 'admin' ? (
            // Admin sees financial stats
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
          ) : (
            // Technician sees only car counts by status
            <View style={styles.statsGrid}>
              <View style={styles.statCard}>
                <Ionicons name="person-add" size={24} color="#8B5CF6" />
                <Text style={styles.statValue}>{report.by_status.asignado || 0}</Text>
                <Text style={styles.statLabel}>Asignados</Text>
              </View>
              <View style={styles.statCard}>
                <Ionicons name="play" size={24} color="#3B82F6" />
                <Text style={styles.statValue}>{report.by_status.iniciado || 0}</Text>
                <Text style={styles.statLabel}>Iniciados</Text>
              </View>
              <View style={styles.statCard}>
                <Ionicons name="pause" size={24} color="#F59E0B" />
                <Text style={styles.statValue}>{report.by_status.pendiente || 0}</Text>
                <Text style={styles.statLabel}>Pendientes</Text>
              </View>
              <View style={styles.statCard}>
                <Ionicons name="checkmark-circle" size={24} color="#10B981" />
                <Text style={styles.statValue}>{report.by_status.terminado || 0}</Text>
                <Text style={styles.statLabel}>Terminados</Text>
              </View>
            </View>
          )}
        </View>
      )}

      {/* Status Summary - Only for Admin */}
      {report && user?.role === 'admin' && (
        <View style={styles.statusSummary}>
          <View style={styles.statusItem}>
            <View style={[styles.statusDot, { backgroundColor: '#8B5CF6' }]} />
            <Text style={styles.statusText}>Asignados: {report.by_status.asignado || 0}</Text>
          </View>
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
  verseContainer: {
    backgroundColor: '#1F2937',
    margin: 20,
    marginTop: 10,
    padding: 16,
    borderRadius: 12,
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  verseContent: {
    flex: 1,
    marginLeft: 12,
  },
  verseText: {
    fontSize: 14,
    color: '#FFFFFF',
    fontStyle: 'italic',
    lineHeight: 20,
  },
  verseRef: {
    fontSize: 12,
    color: '#D4A017',
    marginTop: 8,
    fontWeight: '600',
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
