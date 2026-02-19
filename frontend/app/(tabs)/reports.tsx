import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  RefreshControl,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { getDailyReport, getUsers, getDailyDetailedReport } from '../../src/services/api';
import { useAuthStore } from '../../src/store/authStore';
import { DailyReport, User } from '../../src/types';
import * as Print from 'expo-print';
import * as Sharing from 'expo-sharing';

export default function ReportsScreen() {
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';
  const [report, setReport] = useState<DailyReport | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [techs, setTechs] = useState<User[]>([]);
  const [selectedTech, setSelectedTech] = useState<string | null>(null);
  const [generatingPdf, setGeneratingPdf] = useState(false);

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

  const generatePdfReport = async () => {
    setGeneratingPdf(true);
    try {
      const dateStr = selectedDate.toISOString().split('T')[0];
      const detailedReport = await getDailyDetailedReport(dateStr);
      
      const formattedDate = selectedDate.toLocaleDateString('es-ES', {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      });

      const html = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: Arial, sans-serif; padding: 20px; color: #333; }
    .header { text-align: center; margin-bottom: 30px; border-bottom: 3px solid #3B82F6; padding-bottom: 20px; }
    .header h1 { font-size: 24px; color: #1F2937; margin-bottom: 5px; }
    .header h2 { font-size: 16px; color: #6B7280; font-weight: normal; }
    .header .date { font-size: 14px; color: #3B82F6; margin-top: 10px; }
    
    .summary { display: flex; justify-content: space-around; margin-bottom: 30px; flex-wrap: wrap; }
    .summary-box { text-align: center; padding: 15px 25px; background: #F3F4F6; border-radius: 8px; margin: 5px; min-width: 140px; }
    .summary-box .value { font-size: 28px; font-weight: 700; color: #1F2937; }
    .summary-box .label { font-size: 12px; color: #6B7280; margin-top: 4px; }
    .summary-box.green { background: #D1FAE5; }
    .summary-box.green .value { color: #059669; }
    .summary-box.yellow { background: #FEF3C7; }
    .summary-box.yellow .value { color: #D97706; }
    
    .section { margin-bottom: 25px; }
    .section-title { font-size: 16px; font-weight: 700; color: #1F2937; margin-bottom: 15px; padding-bottom: 8px; border-bottom: 2px solid #E5E7EB; }
    
    .payment-grid { display: flex; gap: 15px; flex-wrap: wrap; }
    .payment-card { flex: 1; min-width: 120px; background: #F9FAFB; border-radius: 8px; padding: 15px; text-align: center; border: 1px solid #E5E7EB; }
    .payment-card .icon { font-size: 24px; margin-bottom: 8px; }
    .payment-card .amount { font-size: 20px; font-weight: 700; color: #1F2937; }
    .payment-card .label { font-size: 11px; color: #6B7280; }
    .payment-card .count { font-size: 12px; color: #9CA3AF; margin-top: 4px; }
    
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th { background: #F3F4F6; padding: 10px 8px; text-align: left; font-weight: 600; color: #374151; border-bottom: 2px solid #E5E7EB; }
    td { padding: 10px 8px; border-bottom: 1px solid #E5E7EB; }
    tr:nth-child(even) { background: #F9FAFB; }
    .text-right { text-align: right; }
    .text-center { text-align: center; }
    .status-paid { color: #059669; font-weight: 600; }
    .status-pending { color: #D97706; font-weight: 600; }
    
    .footer { margin-top: 30px; text-align: center; padding-top: 20px; border-top: 1px solid #E5E7EB; }
    .footer p { font-size: 11px; color: #9CA3AF; }
  </style>
</head>
<body>
  <div class="header">
    <h1>${detailedReport.workshop_name}</h1>
    <h2>Reporte Diario de Servicios</h2>
    <div class="date">${formattedDate}</div>
  </div>

  <div class="summary">
    <div class="summary-box">
      <div class="value">${detailedReport.total_orders}</div>
      <div class="label">Vehículos Atendidos</div>
    </div>
    <div class="summary-box green">
      <div class="value">$${detailedReport.total_paid.toFixed(2)}</div>
      <div class="label">Total Cobrado</div>
    </div>
    <div class="summary-box yellow">
      <div class="value">$${detailedReport.total_pending.toFixed(2)}</div>
      <div class="label">Pendiente</div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">💳 Desglose por Método de Pago</div>
    <div class="payment-grid">
      <div class="payment-card">
        <div class="icon">💵</div>
        <div class="amount">$${detailedReport.by_payment_method.cash.amount.toFixed(2)}</div>
        <div class="label">Efectivo</div>
        <div class="count">${detailedReport.by_payment_method.cash.count} pagos</div>
      </div>
      <div class="payment-card">
        <div class="icon">📱</div>
        <div class="amount">$${detailedReport.by_payment_method.zelle.amount.toFixed(2)}</div>
        <div class="label">Zelle</div>
        <div class="count">${detailedReport.by_payment_method.zelle.count} pagos</div>
      </div>
      <div class="payment-card">
        <div class="icon">📝</div>
        <div class="amount">$${detailedReport.by_payment_method.check.amount.toFixed(2)}</div>
        <div class="label">Cheque</div>
        <div class="count">${detailedReport.by_payment_method.check.count} pagos</div>
      </div>
      <div class="payment-card">
        <div class="icon">💳</div>
        <div class="amount">$${detailedReport.by_payment_method.other.amount.toFixed(2)}</div>
        <div class="label">Otro</div>
        <div class="count">${detailedReport.by_payment_method.other.count} pagos</div>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">📋 Detalle de Servicios</div>
    <table>
      <thead>
        <tr>
          <th>Vehículo</th>
          <th>VIN</th>
          <th>Cliente</th>
          <th>Técnico</th>
          <th>Servicios</th>
          <th class="text-right">Total</th>
          <th class="text-center">Estado</th>
        </tr>
      </thead>
      <tbody>
        ${detailedReport.orders_detail.map((order: any) => `
          <tr>
            <td>${order.vehicle}</td>
            <td>***${order.vin_last6}</td>
            <td>${order.client_name}</td>
            <td>${order.tech_name}</td>
            <td>${order.services.slice(0, 2).join(', ')}${order.services.length > 2 ? '...' : ''}</td>
            <td class="text-right">$${order.total.toFixed(2)}</td>
            <td class="text-center ${order.payment_status === 'pagado' ? 'status-paid' : 'status-pending'}">
              ${order.payment_status === 'pagado' ? '✓ Pagado' : '⏳ Pendiente'}
            </td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  </div>

  <div class="footer">
    <p>Reporte generado el ${new Date().toLocaleString('es-ES')}</p>
    <p>${detailedReport.workshop_name} - Sistema de Gestión</p>
  </div>
</body>
</html>
      `;

      const { uri } = await Print.printToFileAsync({ html });
      
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(uri, {
          mimeType: 'application/pdf',
          dialogTitle: 'Reporte Diario PDF',
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
              {/* PDF Button */}
              <TouchableOpacity
                style={styles.pdfButton}
                onPress={generatePdfReport}
                disabled={generatingPdf}
              >
                {generatingPdf ? (
                  <ActivityIndicator color="#FFF" size="small" />
                ) : (
                  <>
                    <Ionicons name="document-text" size={22} color="#FFF" />
                    <Text style={styles.pdfButtonText}>Generar Reporte PDF</Text>
                  </>
                )}
              </TouchableOpacity>

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
