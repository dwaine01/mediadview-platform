import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  RefreshControl,
} from 'react-native';
import { useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getDailyReport, getUsers } from '../../src/services/api';
import { useAuthStore } from '../../src/store/authStore';
import { DailyReport, User } from '../../src/types';

export default function ReportsScreen() {
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';
  const [report, setReport] = useState<DailyReport | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [techs, setTechs] = useState<User[]>([]);
  const [selectedTech, setSelectedTech] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const dateStr = selectedDate.toISOString().split('T')[0];
      const [reportRes, usersRes] = await Promise.all([
        getDailyReport(dateStr, selectedTech || undefined),
        isAdmin ? getUsers() : Promise.resolve([]),
      ]);
      setReport(reportRes);
      if (isAdmin) {
        setTechs(usersRes.filter((u: User) => u.role === 'tech'));
      }
    } catch (error) {
      console.error('Error loading report:', error);
    }
  };

  useFocusEffect(
    useCallback(() => {
      loadData();
    }, [selectedDate, selectedTech])
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
  };

  const changeDate = (days: number) => {
    const newDate = new Date(selectedDate);
    newDate.setDate(newDate.getDate() + days);
    setSelectedDate(newDate);
  };

  const isToday = selectedDate.toDateString() === new Date().toDateString();

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#3B82F6" />
      }
    >
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>
          {isAdmin ? 'Reportes Generales' : 'Mi Reporte de Trabajo'}
        </Text>
      </View>

      {/* Date Selector */}
      <View style={styles.dateSelector}>
        <TouchableOpacity style={styles.dateButton} onPress={() => changeDate(-1)}>
          <Ionicons name="chevron-back" size={24} color="#FFFFFF" />
        </TouchableOpacity>
        <View style={styles.dateDisplay}>
          <Text style={styles.dateText}>
            {selectedDate.toLocaleDateString('es-ES', {
              weekday: 'long',
              day: 'numeric',
              month: 'long',
            })}
          </Text>
          {isToday && <Text style={styles.todayBadge}>Hoy</Text>}
        </View>
        <TouchableOpacity
          style={[styles.dateButton, isToday && styles.dateButtonDisabled]}
          onPress={() => changeDate(1)}
          disabled={isToday}
        >
          <Ionicons name="chevron-forward" size={24} color={isToday ? '#4B5563' : '#FFFFFF'} />
        </TouchableOpacity>
      </View>

      {/* Tech Filter (Admin only) */}
      {isAdmin && techs.length > 0 && (
        <View style={styles.techFilter}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <TouchableOpacity
              style={[styles.techChip, !selectedTech && styles.techChipActive]}
              onPress={() => setSelectedTech(null)}
            >
              <Text style={[styles.techChipText, !selectedTech && styles.techChipTextActive]}>
                Todos
              </Text>
            </TouchableOpacity>
            {techs.map((tech) => (
              <TouchableOpacity
                key={tech.id}
                style={[styles.techChip, selectedTech === tech.id && styles.techChipActive]}
                onPress={() => setSelectedTech(tech.id)}
              >
                <Text
                  style={[styles.techChipText, selectedTech === tech.id && styles.techChipTextActive]}
                >
                  {tech.name}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      )}

      {report && (
        <>
          {/* ====== SECCIÓN PARA TÉCNICOS: Solo cantidad de carros ====== */}
          {!isAdmin && (
            <>
              {/* Total de Carros */}
              <View style={styles.mainStatCard}>
                <Ionicons name="car-sport" size={40} color="#3B82F6" />
                <Text style={styles.mainStatValue}>{report.total_orders}</Text>
                <Text style={styles.mainStatLabel}>Carros Trabajados</Text>
              </View>

              {/* Status de Carros */}
              <View style={styles.statusGrid}>
                <View style={[styles.statusCard, { borderLeftColor: '#8B5CF6' }]}>
                  <Ionicons name="person-add" size={24} color="#8B5CF6" />
                  <Text style={styles.statusValue}>{report.by_status.asignado || 0}</Text>
                  <Text style={styles.statusLabel}>Asignados</Text>
                </View>
                <View style={[styles.statusCard, { borderLeftColor: '#3B82F6' }]}>
                  <Ionicons name="play-circle" size={24} color="#3B82F6" />
                  <Text style={styles.statusValue}>{report.by_status.iniciado || 0}</Text>
                  <Text style={styles.statusLabel}>Iniciados</Text>
                </View>
                <View style={[styles.statusCard, { borderLeftColor: '#F59E0B' }]}>
                  <Ionicons name="pause-circle" size={24} color="#F59E0B" />
                  <Text style={styles.statusValue}>{report.by_status.pendiente || 0}</Text>
                  <Text style={styles.statusLabel}>Pendientes</Text>
                </View>
                <View style={[styles.statusCard, { borderLeftColor: '#10B981' }]}>
                  <Ionicons name="checkmark-circle" size={24} color="#10B981" />
                  <Text style={styles.statusValue}>{report.by_status.terminado || 0}</Text>
                  <Text style={styles.statusLabel}>Terminados</Text>
                </View>
              </View>
            </>
          )}

          {/* ====== SECCIÓN PARA ADMIN: Reportes Completos ====== */}
          {isAdmin && (
            <>
              {/* Main Stats */}
              <View style={styles.mainStats}>
                <View style={styles.bigStatCard}>
                  <Ionicons name="car" size={36} color="#3B82F6" />
                  <Text style={styles.bigStatValue}>{report.total_orders}</Text>
                  <Text style={styles.bigStatLabel}>Carros Atendidos</Text>
                </View>
              </View>

              {/* Financial Stats - SOLO ADMIN */}
              <Text style={styles.sectionTitle}>💰 Reporte Financiero</Text>
              <View style={styles.financialStats}>
                <View style={[styles.finStatCard, { backgroundColor: '#064E3B' }]}>
                  <Ionicons name="receipt" size={24} color="#10B981" />
                  <Text style={styles.finStatValue}>${report.total_billed.toFixed(2)}</Text>
                  <Text style={styles.finStatLabel}>Total Facturado</Text>
                </View>
                <View style={[styles.finStatCard, { backgroundColor: '#065F46' }]}>
                  <Ionicons name="checkmark-done-circle" size={24} color="#34D399" />
                  <Text style={styles.finStatValue}>${report.total_paid.toFixed(2)}</Text>
                  <Text style={styles.finStatLabel}>Total Pagado</Text>
                </View>
              </View>
              <View style={styles.pendingCard}>
                <Ionicons name="alert-circle" size={28} color="#F59E0B" />
                <View style={styles.pendingInfo}>
                  <Text style={styles.pendingLabel}>Pendiente por Cobrar</Text>
                  <Text style={styles.pendingValue}>${report.total_pending.toFixed(2)}</Text>
                </View>
              </View>

              {/* Status Breakdown */}
              <Text style={styles.sectionTitle}>📊 Estado de Órdenes</Text>
              <View style={styles.statusRow}>
                <View style={styles.statusItem}>
                  <View style={[styles.statusDot, { backgroundColor: '#8B5CF6' }]} />
                  <Text style={styles.statusText}>Asignados</Text>
                  <Text style={styles.statusNum}>{report.by_status.asignado || 0}</Text>
                </View>
                <View style={styles.statusItem}>
                  <View style={[styles.statusDot, { backgroundColor: '#3B82F6' }]} />
                  <Text style={styles.statusText}>Iniciados</Text>
                  <Text style={styles.statusNum}>{report.by_status.iniciado || 0}</Text>
                </View>
                <View style={styles.statusItem}>
                  <View style={[styles.statusDot, { backgroundColor: '#F59E0B' }]} />
                  <Text style={styles.statusText}>Pendientes</Text>
                  <Text style={styles.statusNum}>{report.by_status.pendiente || 0}</Text>
                </View>
                <View style={styles.statusItem}>
                  <View style={[styles.statusDot, { backgroundColor: '#10B981' }]} />
                  <Text style={styles.statusText}>Terminados</Text>
                  <Text style={styles.statusNum}>{report.by_status.terminado || 0}</Text>
                </View>
              </View>

              {/* By Tech - SOLO ADMIN */}
              {report.by_tech && report.by_tech.length > 0 && (
                <>
                  <Text style={styles.sectionTitle}>👨‍🔧 Por Técnico</Text>
                  {report.by_tech.map((tech, index) => (
                    <View key={index} style={styles.techRow}>
                      <View style={styles.techInfo}>
                        <View style={styles.techAvatar}>
                          <Text style={styles.techAvatarText}>
                            {tech.name.charAt(0).toUpperCase()}
                          </Text>
                        </View>
                        <View>
                          <Text style={styles.techName}>{tech.name}</Text>
                          <Text style={styles.techOrders}>{tech.orders} órdenes</Text>
                        </View>
                      </View>
                      <View style={styles.techStats}>
                        <Text style={styles.techBilled}>${tech.billed.toFixed(0)}</Text>
                        <Text style={styles.techPaid}>${tech.paid.toFixed(0)} cobrado</Text>
                      </View>
                    </View>
                  ))}
                </>
              )}
            </>
          )}
        </>
      )}

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#111827',
  },
  header: {
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 8,
  },
  headerTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  dateSelector: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 14,
    backgroundColor: '#1F2937',
    marginHorizontal: 16,
    marginTop: 8,
    borderRadius: 12,
  },
  dateButton: {
    padding: 8,
  },
  dateButtonDisabled: {
    opacity: 0.5,
  },
  dateDisplay: {
    alignItems: 'center',
  },
  dateText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#FFFFFF',
    textTransform: 'capitalize',
  },
  todayBadge: {
    fontSize: 12,
    color: '#3B82F6',
    marginTop: 2,
    fontWeight: '600',
  },
  techFilter: {
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  techChip: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: '#1F2937',
    borderRadius: 20,
    marginRight: 8,
    borderWidth: 1,
    borderColor: '#374151',
  },
  techChipActive: {
    backgroundColor: '#3B82F6',
    borderColor: '#3B82F6',
  },
  techChipText: {
    color: '#9CA3AF',
    fontSize: 14,
  },
  techChipTextActive: {
    color: '#FFFFFF',
    fontWeight: '600',
  },

  // ===== ESTILOS PARA TÉCNICO =====
  mainStatCard: {
    backgroundColor: '#1F2937',
    marginHorizontal: 16,
    marginTop: 16,
    borderRadius: 16,
    padding: 28,
    alignItems: 'center',
  },
  mainStatValue: {
    fontSize: 56,
    fontWeight: '700',
    color: '#FFFFFF',
    marginTop: 8,
  },
  mainStatLabel: {
    fontSize: 16,
    color: '#9CA3AF',
    marginTop: 4,
  },
  statusGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    padding: 16,
    gap: 10,
  },
  statusCard: {
    width: '48%',
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 16,
    borderLeftWidth: 4,
  },
  statusValue: {
    fontSize: 28,
    fontWeight: '700',
    color: '#FFFFFF',
    marginTop: 8,
  },
  statusLabel: {
    fontSize: 13,
    color: '#9CA3AF',
    marginTop: 2,
  },
  infoMessage: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: '#1F2937',
    marginHorizontal: 16,
    borderRadius: 12,
    padding: 14,
    gap: 10,
  },
  infoText: {
    flex: 1,
    fontSize: 13,
    color: '#6B7280',
    lineHeight: 20,
  },

  // ===== ESTILOS PARA ADMIN =====
  mainStats: {
    padding: 16,
  },
  bigStatCard: {
    backgroundColor: '#1F2937',
    borderRadius: 16,
    padding: 24,
    alignItems: 'center',
  },
  bigStatValue: {
    fontSize: 48,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginTop: 8,
  },
  bigStatLabel: {
    fontSize: 16,
    color: '#9CA3AF',
    marginTop: 4,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#FFFFFF',
    marginHorizontal: 16,
    marginTop: 20,
    marginBottom: 12,
  },
  financialStats: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    gap: 10,
  },
  finStatCard: {
    flex: 1,
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  finStatValue: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginTop: 8,
  },
  finStatLabel: {
    fontSize: 11,
    color: 'rgba(255,255,255,0.7)',
    marginTop: 4,
  },
  pendingCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#78350F',
    marginHorizontal: 16,
    marginTop: 10,
    borderRadius: 12,
    padding: 16,
    gap: 14,
  },
  pendingInfo: {
    flex: 1,
  },
  pendingLabel: {
    fontSize: 13,
    color: 'rgba(255,255,255,0.7)',
  },
  pendingValue: {
    fontSize: 22,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  statusRow: {
    backgroundColor: '#1F2937',
    marginHorizontal: 16,
    borderRadius: 12,
    padding: 16,
  },
  statusItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
  },
  statusDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    marginRight: 12,
  },
  statusText: {
    flex: 1,
    fontSize: 14,
    color: '#D1D5DB',
  },
  statusNum: {
    fontSize: 18,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  techRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 14,
    marginHorizontal: 16,
    marginBottom: 8,
  },
  techInfo: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  techAvatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#3B82F6',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  techAvatarText: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  techName: {
    fontSize: 15,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  techOrders: {
    fontSize: 12,
    color: '#9CA3AF',
  },
  techStats: {
    alignItems: 'flex-end',
  },
  techBilled: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  techPaid: {
    fontSize: 12,
    color: '#10B981',
  },
});
