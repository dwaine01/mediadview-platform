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
        user?.role === 'admin' ? getUsers() : Promise.resolve([]),
      ]);
      setReport(reportRes);
      if (user?.role === 'admin') {
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
              year: 'numeric',
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
      {user?.role === 'admin' && techs.length > 0 && (
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
                  style={[
                    styles.techChipText,
                    selectedTech === tech.id && styles.techChipTextActive,
                  ]}
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
          {/* Main Stats */}
          <View style={styles.mainStats}>
            <View style={styles.bigStatCard}>
              <Ionicons name="car" size={32} color="#3B82F6" />
              <Text style={styles.bigStatValue}>{report.total_orders}</Text>
              <Text style={styles.bigStatLabel}>Carros Atendidos</Text>
            </View>
          </View>

          {/* Financial Stats */}
          <View style={styles.financialStats}>
            <View style={[styles.finStatCard, { backgroundColor: '#064E3B' }]}>
              <Ionicons name="wallet" size={24} color="#10B981" />
              <Text style={styles.finStatValue}>${report.total_billed.toFixed(2)}</Text>
              <Text style={styles.finStatLabel}>Facturado</Text>
            </View>
            <View style={[styles.finStatCard, { backgroundColor: '#065F46' }]}>
              <Ionicons name="checkmark-circle" size={24} color="#34D399" />
              <Text style={styles.finStatValue}>${report.total_paid.toFixed(2)}</Text>
              <Text style={styles.finStatLabel}>Pagado</Text>
            </View>
            <View style={[styles.finStatCard, { backgroundColor: '#7C2D12' }]}>
              <Ionicons name="time" size={24} color="#F59E0B" />
              <Text style={styles.finStatValue}>${report.total_pending.toFixed(2)}</Text>
              <Text style={styles.finStatLabel}>Pendiente</Text>
            </View>
          </View>

          {/* Status Breakdown */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Estado de Órdenes</Text>
            <View style={styles.statusCards}>
              <View style={styles.statusCard}>
                <View style={[styles.statusIcon, { backgroundColor: '#1D4ED8' }]}>
                  <Ionicons name="play" size={20} color="#FFFFFF" />
                </View>
                <View>
                  <Text style={styles.statusValue}>{report.by_status.iniciado}</Text>
                  <Text style={styles.statusLabel}>Iniciadas</Text>
                </View>
              </View>
              <View style={styles.statusCard}>
                <View style={[styles.statusIcon, { backgroundColor: '#D97706' }]}>
                  <Ionicons name="pause" size={20} color="#FFFFFF" />
                </View>
                <View>
                  <Text style={styles.statusValue}>{report.by_status.pendiente}</Text>
                  <Text style={styles.statusLabel}>Pendientes</Text>
                </View>
              </View>
              <View style={styles.statusCard}>
                <View style={[styles.statusIcon, { backgroundColor: '#059669' }]}>
                  <Ionicons name="checkmark" size={20} color="#FFFFFF" />
                </View>
                <View>
                  <Text style={styles.statusValue}>{report.by_status.terminado}</Text>
                  <Text style={styles.statusLabel}>Terminadas</Text>
                </View>
              </View>
            </View>
          </View>

          {/* By Tech (Admin only) */}
          {user?.role === 'admin' && report.by_tech.length > 0 && (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Por Técnico</Text>
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
                    <Text style={styles.techPaid}>${tech.paid.toFixed(0)} pagado</Text>
                  </View>
                </View>
              ))}
            </View>
          )}
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#111827',
  },
  dateSelector: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
    backgroundColor: '#1F2937',
    marginHorizontal: 16,
    marginTop: 16,
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
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
    textTransform: 'capitalize',
  },
  todayBadge: {
    fontSize: 12,
    color: '#3B82F6',
    marginTop: 4,
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
  financialStats: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    gap: 8,
  },
  finStatCard: {
    flex: 1,
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  finStatValue: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginTop: 8,
  },
  finStatLabel: {
    fontSize: 12,
    color: 'rgba(255,255,255,0.7)',
    marginTop: 4,
  },
  section: {
    padding: 16,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 16,
  },
  statusCards: {
    flexDirection: 'row',
    gap: 8,
  },
  statusCard: {
    flex: 1,
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 16,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  statusIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
  },
  statusValue: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  statusLabel: {
    fontSize: 11,
    color: '#9CA3AF',
  },
  techRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 16,
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
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  techOrders: {
    fontSize: 13,
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
    fontSize: 13,
    color: '#10B981',
  },
});
