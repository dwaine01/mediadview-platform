import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
  TextInput,
  Linking,
  Modal,
} from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { 
  getWorkOrders, 
  getClients, 
  getUsers, 
  getDailyReport,
  getDailyDetailedReport,
  getCreditReport,
  getWorkshop,
} from '../../src/services/api';
import { useAuthStore } from '../../src/store/authStore';
import * as Print from 'expo-print';
import * as Sharing from 'expo-sharing';

type TabType = 'dashboard' | 'orders' | 'clients' | 'reports' | 'credit' | 'settings';

export default function OfficePanelPro() {
  const { user, logout } = useAuthStore();
  const [activeTab, setActiveTab] = useState<TabType>('dashboard');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  
  // Data
  const [orders, setOrders] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [technicians, setTechnicians] = useState<any[]>([]);
  const [report, setReport] = useState<any>(null);
  const [creditData, setCreditData] = useState<any[]>([]);
  const [workshop, setWorkshop] = useState<any>(null);
  
  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [dateFilter, setDateFilter] = useState(new Date().toISOString().split('T')[0]);

  const loadData = async () => {
    try {
      const [ordersRes, clientsRes, usersRes, reportRes, creditRes, workshopRes] = await Promise.all([
        getWorkOrders(),
        getClients(),
        getUsers(),
        getDailyReport(dateFilter),
        getCreditReport().catch(() => []),
        getWorkshop().catch(() => null),
      ]);
      
      setOrders(ordersRes || []);
      setClients(clientsRes || []);
      setTechnicians(usersRes?.filter((u: any) => u.role === 'tech') || []);
      setReport(reportRes);
      setCreditData(creditRes || []);
      setWorkshop(workshopRes);
    } catch (error) {
      console.error('Error loading data:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useFocusEffect(useCallback(() => { loadData(); }, [dateFilter]));

  const onRefresh = () => { setRefreshing(true); loadData(); };

  const filteredOrders = orders.filter(order => {
    const matchesSearch = !searchQuery || 
      order.client?.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      order.vehicle?.make?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      order.vehicle?.vin?.includes(searchQuery);
    const matchesStatus = !statusFilter || order.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const getStatusColor = (status: string) => {
    const colors: any = { asignado: '#6366F1', iniciado: '#3B82F6', pendiente: '#F59E0B', terminado: '#10B981' };
    return colors[status] || '#6B7280';
  };

  const getStatusLabel = (status: string) => {
    const labels: any = { asignado: 'Asignado', iniciado: 'En Proceso', pendiente: 'Pendiente', terminado: 'Completado' };
    return labels[status] || status;
  };

  const generateDailyPDF = async () => {
    try {
      const detailed = await getDailyDetailedReport(dateFilter);
      const html = `
<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  body { font-family: Arial, sans-serif; font-size: 11px; padding: 20px; }
  .header { border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 15px; }
  .header h1 { margin: 0; font-size: 18px; }
  .header p { margin: 5px 0 0; color: #666; font-size: 12px; }
  .stats { display: flex; gap: 20px; margin-bottom: 20px; }
  .stat { background: #f5f5f5; padding: 12px; border-radius: 6px; text-align: center; flex: 1; }
  .stat-value { font-size: 20px; font-weight: bold; color: #333; }
  .stat-label { font-size: 10px; color: #666; margin-top: 4px; }
  table { width: 100%; border-collapse: collapse; margin-top: 15px; }
  th { background: #333; color: #fff; padding: 8px; text-align: left; font-size: 10px; }
  td { padding: 8px; border-bottom: 1px solid #ddd; }
  .section-title { font-size: 13px; font-weight: bold; margin: 20px 0 10px; border-bottom: 1px solid #ddd; padding-bottom: 5px; }
  .payment-grid { display: flex; gap: 15px; margin-bottom: 15px; }
  .payment-box { background: #f9f9f9; padding: 10px; border-radius: 4px; flex: 1; text-align: center; }
</style></head><body>
  <div class="header">
    <h1>${workshop?.name || 'Ohio Airbag Light Reset'}</h1>
    <p>Reporte Diario - ${new Date(dateFilter).toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</p>
  </div>
  <div class="stats">
    <div class="stat"><div class="stat-value">${detailed.total_orders}</div><div class="stat-label">Órdenes</div></div>
    <div class="stat"><div class="stat-value">$${detailed.total_paid?.toFixed(2)}</div><div class="stat-label">Cobrado</div></div>
    <div class="stat"><div class="stat-value">$${detailed.total_pending?.toFixed(2)}</div><div class="stat-label">Pendiente</div></div>
  </div>
  <div class="section-title">Desglose por Método de Pago</div>
  <div class="payment-grid">
    <div class="payment-box"><strong>$${detailed.by_payment_method?.cash?.amount?.toFixed(2) || '0.00'}</strong><br><small>Efectivo (${detailed.by_payment_method?.cash?.count || 0})</small></div>
    <div class="payment-box"><strong>$${detailed.by_payment_method?.zelle?.amount?.toFixed(2) || '0.00'}</strong><br><small>Zelle (${detailed.by_payment_method?.zelle?.count || 0})</small></div>
    <div class="payment-box"><strong>$${detailed.by_payment_method?.check?.amount?.toFixed(2) || '0.00'}</strong><br><small>Cheque (${detailed.by_payment_method?.check?.count || 0})</small></div>
  </div>
  <div class="section-title">Detalle de Órdenes</div>
  <table>
    <tr><th>Cliente</th><th>Vehículo</th><th>VIN</th><th>Técnico</th><th>Total</th><th>Estado</th></tr>
    ${detailed.orders_detail?.map((o: any) => `
      <tr><td>${o.client_name}</td><td>${o.vehicle}</td><td>...${o.vin_last6}</td><td>${o.tech_name}</td><td>$${o.total?.toFixed(2)}</td><td>${o.payment_status === 'pagado' ? '✓ Pagado' : 'Pendiente'}</td></tr>
    `).join('') || ''}
  </table>
  <p style="margin-top:20px;color:#999;font-size:9px;">Generado: ${new Date().toLocaleString('es-ES')}</p>
</body></html>`;
      const { uri } = await Print.printToFileAsync({ html });
      await Sharing.shareAsync(uri, { mimeType: 'application/pdf', UTI: 'com.adobe.pdf' });
    } catch (e) { console.error(e); }
  };

  const generateCreditPDF = async () => {
    try {
      const total = creditData.reduce((s, c) => s + (c.total_pending || 0), 0);
      const html = `
<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  body { font-family: Arial, sans-serif; font-size: 11px; padding: 20px; }
  .header { border-bottom: 2px solid #F59E0B; padding-bottom: 10px; margin-bottom: 15px; }
  .header h1 { margin: 0; font-size: 18px; }
  .total-box { background: #FEF3C7; padding: 15px; border-radius: 6px; text-align: center; margin-bottom: 20px; }
  .total-value { font-size: 24px; font-weight: bold; color: #D97706; }
  .client-section { margin-bottom: 20px; border: 1px solid #ddd; border-radius: 6px; overflow: hidden; }
  .client-header { background: #333; color: #fff; padding: 10px; display: flex; justify-content: space-between; }
  table { width: 100%; border-collapse: collapse; }
  th { background: #f5f5f5; padding: 8px; text-align: left; font-size: 10px; }
  td { padding: 8px; border-bottom: 1px solid #eee; }
</style></head><body>
  <div class="header"><h1>${workshop?.name || 'Ohio Airbag Light Reset'}</h1><p>Reporte de Cuentas por Cobrar</p></div>
  <div class="total-box"><div class="total-value">$${total.toFixed(2)}</div><div>Total Adeudado</div></div>
  ${creditData.filter(c => c.total_pending > 0).map(c => `
    <div class="client-section">
      <div class="client-header"><span>${c.client?.name}</span><span>$${c.total_pending?.toFixed(2)}</span></div>
      <table><tr><th>Fecha</th><th>Vehículo</th><th>Monto</th></tr>
        ${c.pending_orders?.map((o: any) => `<tr><td>${new Date(o.created_at).toLocaleDateString('es-ES')}</td><td>${o.vehicle}</td><td>$${o.total?.toFixed(2)}</td></tr>`).join('') || ''}
      </table>
    </div>
  `).join('')}
</body></html>`;
      const { uri } = await Print.printToFileAsync({ html });
      await Sharing.shareAsync(uri, { mimeType: 'application/pdf', UTI: 'com.adobe.pdf' });
    } catch (e) { console.error(e); }
  };

  if (!user || user.role !== 'admin') {
    return (
      <View style={s.container}>
        <View style={s.accessDenied}>
          <Ionicons name="lock-closed" size={48} color="#EF4444" />
          <Text style={s.accessTitle}>Acceso Restringido</Text>
          <Text style={s.accessText}>Solo administradores</Text>
        </View>
      </View>
    );
  }

  if (loading) {
    return <View style={[s.container, s.centered]}><ActivityIndicator size="large" color="#3B82F6" /></View>;
  }

  return (
    <View style={s.container}>
      {/* Sidebar */}
      <View style={s.sidebar}>
        <View style={s.logo}>
          <Text style={s.logoText}>OAR</Text>
          <Text style={s.logoSubtext}>Panel Admin</Text>
        </View>
        
        <View style={s.menu}>
          {[
            { id: 'dashboard', icon: 'grid', label: 'Dashboard' },
            { id: 'orders', icon: 'document-text', label: 'Órdenes' },
            { id: 'clients', icon: 'people', label: 'Clientes' },
            { id: 'reports', icon: 'bar-chart', label: 'Reportes' },
            { id: 'credit', icon: 'card', label: 'Créditos' },
          ].map(item => (
            <TouchableOpacity 
              key={item.id} 
              style={[s.menuItem, activeTab === item.id && s.menuItemActive]}
              onPress={() => setActiveTab(item.id as TabType)}
            >
              <Ionicons name={item.icon as any} size={18} color={activeTab === item.id ? '#3B82F6' : '#9CA3AF'} />
              <Text style={[s.menuText, activeTab === item.id && s.menuTextActive]}>{item.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
        
        <View style={s.sidebarFooter}>
          <Text style={s.userName}>{user?.name}</Text>
          <TouchableOpacity onPress={logout}>
            <Ionicons name="log-out-outline" size={18} color="#EF4444" />
          </TouchableOpacity>
        </View>
      </View>

      {/* Main Content */}
      <ScrollView 
        style={s.main} 
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#3B82F6" />}
      >
        {/* DASHBOARD */}
        {activeTab === 'dashboard' && (
          <View style={s.content}>
            <View style={s.pageHeader}>
              <Text style={s.pageTitle}>Dashboard</Text>
              <Text style={s.pageDate}>{new Date().toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric', month: 'long' })}</Text>
            </View>

            <View style={s.statsRow}>
              <View style={[s.statBox, { borderLeftColor: '#3B82F6' }]}>
                <Text style={s.statNumber}>{report?.total_orders || 0}</Text>
                <Text style={s.statLabel}>Órdenes Hoy</Text>
              </View>
              <View style={[s.statBox, { borderLeftColor: '#10B981' }]}>
                <Text style={[s.statNumber, { color: '#10B981' }]}>${report?.total_paid?.toFixed(2) || '0.00'}</Text>
                <Text style={s.statLabel}>Cobrado</Text>
              </View>
              <View style={[s.statBox, { borderLeftColor: '#F59E0B' }]}>
                <Text style={[s.statNumber, { color: '#F59E0B' }]}>${report?.total_pending?.toFixed(2) || '0.00'}</Text>
                <Text style={s.statLabel}>Pendiente</Text>
              </View>
              <View style={[s.statBox, { borderLeftColor: '#8B5CF6' }]}>
                <Text style={s.statNumber}>{clients.length}</Text>
                <Text style={s.statLabel}>Clientes</Text>
              </View>
            </View>

            <View style={s.row}>
              <View style={s.card}>
                <Text style={s.cardTitle}>Técnicos Activos</Text>
                {technicians.map(tech => {
                  const active = orders.filter(o => o.tech_id === tech.id && o.status !== 'terminado').length;
                  return (
                    <View key={tech.id} style={s.techRow}>
                      <View style={[s.techDot, { backgroundColor: active > 0 ? '#10B981' : '#6B7280' }]} />
                      <Text style={s.techName}>{tech.name}</Text>
                      <Text style={s.techOrders}>{active} activas</Text>
                    </View>
                  );
                })}
              </View>
              
              <View style={s.card}>
                <Text style={s.cardTitle}>Acciones Rápidas</Text>
                <TouchableOpacity style={s.quickBtn} onPress={() => router.push('/order/assign')}>
                  <Ionicons name="add-circle" size={16} color="#3B82F6" />
                  <Text style={s.quickBtnText}>Nueva Orden</Text>
                </TouchableOpacity>
                <TouchableOpacity style={s.quickBtn} onPress={generateDailyPDF}>
                  <Ionicons name="document" size={16} color="#10B981" />
                  <Text style={s.quickBtnText}>Reporte del Día (PDF)</Text>
                </TouchableOpacity>
                <TouchableOpacity style={s.quickBtn} onPress={generateCreditPDF}>
                  <Ionicons name="card" size={16} color="#F59E0B" />
                  <Text style={s.quickBtnText}>Reporte Créditos (PDF)</Text>
                </TouchableOpacity>
              </View>
            </View>

            <View style={s.card}>
              <Text style={s.cardTitle}>Últimas Órdenes</Text>
              <View style={s.tableHeader}>
                <Text style={[s.th, { flex: 2 }]}>Cliente</Text>
                <Text style={[s.th, { flex: 2 }]}>Vehículo</Text>
                <Text style={[s.th, { flex: 1 }]}>Técnico</Text>
                <Text style={[s.th, { flex: 1 }]}>Estado</Text>
              </View>
              {orders.slice(0, 5).map(order => (
                <TouchableOpacity key={order.id} style={s.tableRow} onPress={() => router.push(`/order/${order.id}`)}>
                  <Text style={[s.td, { flex: 2 }]}>{order.client?.name || '-'}</Text>
                  <Text style={[s.td, { flex: 2 }]}>{order.vehicle?.year} {order.vehicle?.make} {order.vehicle?.model}</Text>
                  <Text style={[s.td, { flex: 1 }]}>{order.tech_name || '-'}</Text>
                  <View style={[s.badge, { backgroundColor: getStatusColor(order.status), flex: 1 }]}>
                    <Text style={s.badgeText}>{getStatusLabel(order.status)}</Text>
                  </View>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        )}

        {/* ORDERS */}
        {activeTab === 'orders' && (
          <View style={s.content}>
            <View style={s.pageHeader}>
              <Text style={s.pageTitle}>Órdenes de Trabajo</Text>
              <TouchableOpacity style={s.primaryBtn} onPress={() => router.push('/order/assign')}>
                <Ionicons name="add" size={16} color="#FFF" />
                <Text style={s.primaryBtnText}>Nueva Orden</Text>
              </TouchableOpacity>
            </View>

            <View style={s.filters}>
              <TextInput style={s.searchInput} placeholder="Buscar..." placeholderTextColor="#9CA3AF" value={searchQuery} onChangeText={setSearchQuery} />
              <View style={s.filterBtns}>
                {[null, 'asignado', 'iniciado', 'pendiente', 'terminado'].map(st => (
                  <TouchableOpacity key={st || 'all'} style={[s.filterBtn, statusFilter === st && s.filterBtnActive]} onPress={() => setStatusFilter(st)}>
                    <Text style={[s.filterBtnText, statusFilter === st && s.filterBtnTextActive]}>{st ? getStatusLabel(st) : 'Todas'}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>

            <View style={s.card}>
              <View style={s.tableHeader}>
                <Text style={[s.th, { flex: 2 }]}>Cliente</Text>
                <Text style={[s.th, { flex: 2 }]}>Vehículo</Text>
                <Text style={[s.th, { flex: 1 }]}>VIN</Text>
                <Text style={[s.th, { flex: 1 }]}>Técnico</Text>
                <Text style={[s.th, { flex: 1 }]}>Estado</Text>
                <Text style={[s.th, { flex: 1 }]}>Acciones</Text>
              </View>
              {filteredOrders.map(order => (
                <View key={order.id} style={s.tableRow}>
                  <View style={{ flex: 2 }}>
                    <Text style={s.td}>{order.client?.name || '-'}</Text>
                    {order.client?.phone && <Text style={s.tdSmall}>📞 {order.client.phone}</Text>}
                  </View>
                  <Text style={[s.td, { flex: 2 }]}>{order.vehicle?.year} {order.vehicle?.make} {order.vehicle?.model}</Text>
                  <Text style={[s.tdSmall, { flex: 1 }]}>...{order.vehicle?.vin?.slice(-6) || 'N/A'}</Text>
                  <Text style={[s.td, { flex: 1 }]}>{order.tech_name || '-'}</Text>
                  <View style={{ flex: 1 }}>
                    <View style={[s.badge, { backgroundColor: getStatusColor(order.status) }]}>
                      <Text style={s.badgeText}>{getStatusLabel(order.status)}</Text>
                    </View>
                  </View>
                  <View style={{ flex: 1, flexDirection: 'row', gap: 8 }}>
                    <TouchableOpacity onPress={() => router.push(`/order/${order.id}`)}>
                      <Ionicons name="eye" size={16} color="#3B82F6" />
                    </TouchableOpacity>
                    {order.client?.phone && (
                      <TouchableOpacity onPress={() => Linking.openURL(`tel:${order.client.phone}`)}>
                        <Ionicons name="call" size={16} color="#10B981" />
                      </TouchableOpacity>
                    )}
                  </View>
                </View>
              ))}
              {filteredOrders.length === 0 && <Text style={s.empty}>No hay órdenes</Text>}
            </View>
          </View>
        )}

        {/* CLIENTS */}
        {activeTab === 'clients' && (
          <View style={s.content}>
            <View style={s.pageHeader}>
              <Text style={s.pageTitle}>Clientes ({clients.length})</Text>
            </View>
            <View style={s.card}>
              <View style={s.tableHeader}>
                <Text style={[s.th, { flex: 2 }]}>Nombre</Text>
                <Text style={[s.th, { flex: 2 }]}>Teléfono</Text>
                <Text style={[s.th, { flex: 3 }]}>Dirección</Text>
                <Text style={[s.th, { flex: 1 }]}>Crédito</Text>
              </View>
              {clients.map(client => (
                <View key={client.id} style={s.tableRow}>
                  <Text style={[s.td, { flex: 2 }]}>{client.name}</Text>
                  <Text style={[s.td, { flex: 2 }]}>{client.phone || '-'}</Text>
                  <Text style={[s.tdSmall, { flex: 3 }]} numberOfLines={1}>{client.address || '-'}</Text>
                  <View style={{ flex: 1 }}>
                    {client.has_credit_account && <View style={[s.badge, { backgroundColor: '#F59E0B' }]}><Text style={s.badgeText}>Crédito</Text></View>}
                  </View>
                </View>
              ))}
            </View>
          </View>
        )}

        {/* REPORTS */}
        {activeTab === 'reports' && (
          <View style={s.content}>
            <View style={s.pageHeader}>
              <Text style={s.pageTitle}>Reportes Financieros</Text>
            </View>
            
            <View style={s.dateSelector}>
              <TouchableOpacity onPress={() => { const d = new Date(dateFilter); d.setDate(d.getDate() - 1); setDateFilter(d.toISOString().split('T')[0]); }}>
                <Ionicons name="chevron-back" size={20} color="#3B82F6" />
              </TouchableOpacity>
              <Text style={s.dateText}>{new Date(dateFilter).toLocaleDateString('es-ES', { weekday: 'short', day: 'numeric', month: 'short' })}</Text>
              <TouchableOpacity onPress={() => { const d = new Date(dateFilter); d.setDate(d.getDate() + 1); setDateFilter(d.toISOString().split('T')[0]); }}>
                <Ionicons name="chevron-forward" size={20} color="#3B82F6" />
              </TouchableOpacity>
            </View>

            <View style={s.statsRow}>
              <View style={[s.statBox, { borderLeftColor: '#3B82F6' }]}>
                <Text style={s.statNumber}>{report?.total_orders || 0}</Text>
                <Text style={s.statLabel}>Órdenes</Text>
              </View>
              <View style={[s.statBox, { borderLeftColor: '#10B981' }]}>
                <Text style={[s.statNumber, { color: '#10B981' }]}>${report?.total_paid?.toFixed(2) || '0.00'}</Text>
                <Text style={s.statLabel}>Cobrado</Text>
              </View>
              <View style={[s.statBox, { borderLeftColor: '#F59E0B' }]}>
                <Text style={[s.statNumber, { color: '#F59E0B' }]}>${report?.total_pending?.toFixed(2) || '0.00'}</Text>
                <Text style={s.statLabel}>Pendiente</Text>
              </View>
            </View>

            <TouchableOpacity style={s.pdfBtn} onPress={generateDailyPDF}>
              <Ionicons name="document-text" size={18} color="#FFF" />
              <Text style={s.pdfBtnText}>Descargar Reporte PDF</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* CREDIT */}
        {activeTab === 'credit' && (
          <View style={s.content}>
            <View style={s.pageHeader}>
              <Text style={s.pageTitle}>Cuentas por Cobrar</Text>
              <TouchableOpacity style={s.pdfBtnSmall} onPress={generateCreditPDF}>
                <Ionicons name="download" size={14} color="#FFF" />
                <Text style={s.pdfBtnSmallText}>PDF</Text>
              </TouchableOpacity>
            </View>

            <View style={[s.statBox, { borderLeftColor: '#F59E0B', marginBottom: 16 }]}>
              <Text style={[s.statNumber, { color: '#F59E0B' }]}>${creditData.reduce((s, c) => s + (c.total_pending || 0), 0).toFixed(2)}</Text>
              <Text style={s.statLabel}>Total Adeudado</Text>
            </View>

            {creditData.filter(c => c.total_pending > 0).map(c => (
              <View key={c.client?.id} style={s.creditCard}>
                <View style={s.creditHeader}>
                  <Text style={s.creditName}>{c.client?.name}</Text>
                  <Text style={s.creditTotal}>${c.total_pending?.toFixed(2)}</Text>
                </View>
                {c.pending_orders?.map((o: any) => (
                  <View key={o.id} style={s.creditOrder}>
                    <Text style={s.creditOrderDate}>{new Date(o.created_at).toLocaleDateString('es-ES')}</Text>
                    <Text style={s.creditOrderVehicle}>{o.vehicle}</Text>
                    <Text style={s.creditOrderAmount}>${o.total?.toFixed(2)}</Text>
                  </View>
                ))}
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, flexDirection: 'row', backgroundColor: '#F3F4F6' },
  centered: { justifyContent: 'center', alignItems: 'center' },
  accessDenied: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  accessTitle: { color: '#EF4444', fontSize: 18, fontWeight: '600', marginTop: 12 },
  accessText: { color: '#6B7280', fontSize: 13 },
  
  // Sidebar
  sidebar: { width: 200, backgroundColor: '#1F2937', paddingTop: 20 },
  logo: { padding: 16, borderBottomWidth: 1, borderBottomColor: '#374151' },
  logoText: { color: '#3B82F6', fontSize: 24, fontWeight: '800' },
  logoSubtext: { color: '#6B7280', fontSize: 11 },
  menu: { flex: 1, paddingTop: 8 },
  menuItem: { flexDirection: 'row', alignItems: 'center', padding: 12, marginHorizontal: 8, borderRadius: 6, gap: 10 },
  menuItemActive: { backgroundColor: '#374151' },
  menuText: { color: '#9CA3AF', fontSize: 13 },
  menuTextActive: { color: '#3B82F6', fontWeight: '600' },
  sidebarFooter: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, borderTopWidth: 1, borderTopColor: '#374151' },
  userName: { color: '#D1D5DB', fontSize: 12 },
  
  // Main
  main: { flex: 1 },
  content: { padding: 20 },
  pageHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 },
  pageTitle: { fontSize: 20, fontWeight: '700', color: '#1F2937' },
  pageDate: { color: '#6B7280', fontSize: 13 },
  
  // Stats
  statsRow: { flexDirection: 'row', gap: 12, marginBottom: 20 },
  statBox: { flex: 1, backgroundColor: '#FFF', padding: 16, borderRadius: 8, borderLeftWidth: 4 },
  statNumber: { fontSize: 22, fontWeight: '700', color: '#1F2937' },
  statLabel: { fontSize: 11, color: '#6B7280', marginTop: 4 },
  
  // Cards
  row: { flexDirection: 'row', gap: 16, marginBottom: 16 },
  card: { flex: 1, backgroundColor: '#FFF', borderRadius: 8, padding: 16 },
  cardTitle: { fontSize: 13, fontWeight: '600', color: '#374151', marginBottom: 12, borderBottomWidth: 1, borderBottomColor: '#E5E7EB', paddingBottom: 8 },
  
  // Tech list
  techRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 8, gap: 8 },
  techDot: { width: 8, height: 8, borderRadius: 4 },
  techName: { flex: 1, fontSize: 13, color: '#374151' },
  techOrders: { fontSize: 11, color: '#6B7280' },
  
  // Quick buttons
  quickBtn: { flexDirection: 'row', alignItems: 'center', padding: 10, backgroundColor: '#F9FAFB', borderRadius: 6, marginBottom: 8, gap: 8 },
  quickBtnText: { fontSize: 12, color: '#374151' },
  
  // Table
  tableHeader: { flexDirection: 'row', backgroundColor: '#F9FAFB', padding: 10, borderRadius: 4, marginBottom: 4 },
  th: { fontSize: 10, fontWeight: '600', color: '#6B7280', textTransform: 'uppercase' },
  tableRow: { flexDirection: 'row', alignItems: 'center', padding: 10, borderBottomWidth: 1, borderBottomColor: '#F3F4F6' },
  td: { fontSize: 12, color: '#374151' },
  tdSmall: { fontSize: 11, color: '#6B7280' },
  
  // Badge
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10, alignSelf: 'flex-start' },
  badgeText: { fontSize: 10, color: '#FFF', fontWeight: '600' },
  
  // Filters
  filters: { flexDirection: 'row', gap: 12, marginBottom: 16, flexWrap: 'wrap' },
  searchInput: { backgroundColor: '#FFF', borderRadius: 6, paddingHorizontal: 12, paddingVertical: 8, fontSize: 13, color: '#374151', minWidth: 200, borderWidth: 1, borderColor: '#E5E7EB' },
  filterBtns: { flexDirection: 'row', gap: 6 },
  filterBtn: { paddingHorizontal: 12, paddingVertical: 6, backgroundColor: '#FFF', borderRadius: 4, borderWidth: 1, borderColor: '#E5E7EB' },
  filterBtnActive: { backgroundColor: '#3B82F6', borderColor: '#3B82F6' },
  filterBtnText: { fontSize: 11, color: '#6B7280' },
  filterBtnTextActive: { color: '#FFF' },
  
  // Buttons
  primaryBtn: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#3B82F6', paddingHorizontal: 14, paddingVertical: 8, borderRadius: 6, gap: 6 },
  primaryBtnText: { color: '#FFF', fontSize: 13, fontWeight: '600' },
  pdfBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', backgroundColor: '#DC2626', padding: 14, borderRadius: 8, gap: 8, marginTop: 16 },
  pdfBtnText: { color: '#FFF', fontSize: 14, fontWeight: '600' },
  pdfBtnSmall: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#F59E0B', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 4, gap: 4 },
  pdfBtnSmallText: { color: '#FFF', fontSize: 11, fontWeight: '600' },
  
  // Date selector
  dateSelector: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 20, marginBottom: 20, backgroundColor: '#FFF', padding: 12, borderRadius: 8 },
  dateText: { fontSize: 14, fontWeight: '600', color: '#374151' },
  
  // Credit
  creditCard: { backgroundColor: '#FFF', borderRadius: 8, marginBottom: 12, overflow: 'hidden' },
  creditHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#1F2937', padding: 12 },
  creditName: { color: '#FFF', fontSize: 14, fontWeight: '600' },
  creditTotal: { color: '#F59E0B', fontSize: 16, fontWeight: '700' },
  creditOrder: { flexDirection: 'row', padding: 10, borderBottomWidth: 1, borderBottomColor: '#F3F4F6' },
  creditOrderDate: { flex: 1, fontSize: 11, color: '#6B7280' },
  creditOrderVehicle: { flex: 2, fontSize: 12, color: '#374151' },
  creditOrderAmount: { flex: 1, fontSize: 12, color: '#374151', textAlign: 'right' },
  
  empty: { textAlign: 'center', color: '#9CA3AF', padding: 20 },
});
