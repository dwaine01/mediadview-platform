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
  Dimensions,
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

type TabType = 'dashboard' | 'orders' | 'clients' | 'reports' | 'credit';

export default function OfficeDashboard() {
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
    const colors: any = { asignado: '#8B5CF6', iniciado: '#3B82F6', pendiente: '#F59E0B', terminado: '#10B981' };
    return colors[status] || '#6B7280';
  };

  const getStatusLabel = (status: string) => {
    const labels: any = { asignado: 'Asignado', iniciado: 'En Proceso', pendiente: 'Pendiente', terminado: 'Completado' };
    return labels[status] || status;
  };

  const generateDailyPDF = async () => {
    try {
      const detailed = await getDailyDetailedReport(dateFilter);
      const html = `<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
body{font-family:system-ui,-apple-system,sans-serif;font-size:10px;padding:15px;color:#1a1a1a;line-height:1.4}
.header{display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #1F2937;padding-bottom:8px;margin-bottom:12px}
.header h1{margin:0;font-size:16px;font-weight:700}
.header p{margin:0;color:#666;font-size:10px}
.stats{display:flex;gap:10px;margin-bottom:15px}
.stat{flex:1;background:#f8f9fa;padding:10px;border-radius:4px;text-align:center;border-left:3px solid #3B82F6}
.stat.green{border-left-color:#10B981}
.stat.orange{border-left-color:#F59E0B}
.stat-value{font-size:18px;font-weight:700;color:#1F2937}
.stat-label{font-size:9px;color:#666;margin-top:2px;text-transform:uppercase}
.section{margin-bottom:15px}
.section-title{font-size:11px;font-weight:600;color:#374151;margin-bottom:8px;padding-bottom:4px;border-bottom:1px solid #e5e7eb}
.payment-grid{display:flex;gap:10px}
.payment-box{flex:1;background:#f8f9fa;padding:8px;border-radius:4px;text-align:center}
.payment-box strong{font-size:13px;color:#1F2937}
.payment-box small{display:block;font-size:8px;color:#666;margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:9px}
th{background:#1F2937;color:#fff;padding:6px 8px;text-align:left;font-weight:500}
td{padding:6px 8px;border-bottom:1px solid #e5e7eb}
tr:hover{background:#f8f9fa}
.badge{display:inline-block;padding:2px 6px;border-radius:3px;font-size:8px;font-weight:500}
.badge-paid{background:#D1FAE5;color:#065F46}
.badge-pending{background:#FEF3C7;color:#92400E}
.footer{margin-top:15px;padding-top:8px;border-top:1px solid #e5e7eb;font-size:8px;color:#999;text-align:center}
</style></head><body>
<div class="header">
<div><h1>${workshop?.name || 'Ohio Airbag Light Reset'}</h1><p>Reporte Financiero Diario</p></div>
<div style="text-align:right"><p style="font-size:11px;font-weight:600">${new Date(dateFilter).toLocaleDateString('es-ES',{weekday:'long',day:'numeric',month:'long',year:'numeric'})}</p></div>
</div>
<div class="stats">
<div class="stat"><div class="stat-value">${detailed.total_orders}</div><div class="stat-label">Órdenes</div></div>
<div class="stat green"><div class="stat-value">$${detailed.total_paid?.toFixed(2)}</div><div class="stat-label">Cobrado</div></div>
<div class="stat orange"><div class="stat-value">$${detailed.total_pending?.toFixed(2)}</div><div class="stat-label">Pendiente</div></div>
</div>
<div class="section">
<div class="section-title">Desglose por Método de Pago</div>
<div class="payment-grid">
<div class="payment-box"><strong>$${detailed.by_payment_method?.cash?.amount?.toFixed(2)||'0.00'}</strong><small>Efectivo (${detailed.by_payment_method?.cash?.count||0})</small></div>
<div class="payment-box"><strong>$${detailed.by_payment_method?.zelle?.amount?.toFixed(2)||'0.00'}</strong><small>Zelle (${detailed.by_payment_method?.zelle?.count||0})</small></div>
<div class="payment-box"><strong>$${detailed.by_payment_method?.check?.amount?.toFixed(2)||'0.00'}</strong><small>Cheque (${detailed.by_payment_method?.check?.count||0})</small></div>
</div></div>
<div class="section">
<div class="section-title">Detalle de Órdenes del Día</div>
<table><tr><th>Cliente</th><th>Vehículo</th><th>VIN</th><th>Técnico</th><th>Total</th><th>Estado</th></tr>
${detailed.orders_detail?.map((o:any)=>`<tr><td>${o.client_name}</td><td>${o.vehicle}</td><td>...${o.vin_last6}</td><td>${o.tech_name}</td><td>$${o.total?.toFixed(2)}</td><td><span class="badge ${o.payment_status==='pagado'?'badge-paid':'badge-pending'}">${o.payment_status==='pagado'?'Pagado':'Pendiente'}</span></td></tr>`).join('')||'<tr><td colspan="6" style="text-align:center;color:#999">Sin órdenes</td></tr>'}
</table></div>
<div class="footer">Generado: ${new Date().toLocaleString('es-ES')} | ${workshop?.name||'Ohio Airbag Light Reset'}</div>
</body></html>`;
      const { uri } = await Print.printToFileAsync({ html });
      await Sharing.shareAsync(uri, { mimeType: 'application/pdf', UTI: 'com.adobe.pdf' });
    } catch (e) { console.error(e); }
  };

  const generateCreditPDF = async () => {
    try {
      const total = creditData.reduce((s, c) => s + (c.total_pending || 0), 0);
      const html = `<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
body{font-family:system-ui,-apple-system,sans-serif;font-size:10px;padding:15px;color:#1a1a1a}
.header{display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #F59E0B;padding-bottom:8px;margin-bottom:12px}
.header h1{margin:0;font-size:16px}
.total-box{background:linear-gradient(135deg,#FEF3C7,#FDE68A);padding:12px;border-radius:6px;text-align:center;margin-bottom:15px}
.total-value{font-size:24px;font-weight:700;color:#92400E}
.total-label{font-size:10px;color:#A16207}
.client-card{margin-bottom:12px;border:1px solid #e5e7eb;border-radius:6px;overflow:hidden}
.client-header{background:#1F2937;color:#fff;padding:8px 12px;display:flex;justify-content:space-between;align-items:center}
.client-name{font-weight:600;font-size:11px}
.client-total{color:#F59E0B;font-weight:700;font-size:12px}
table{width:100%;border-collapse:collapse;font-size:9px}
th{background:#f8f9fa;padding:6px 8px;text-align:left;font-weight:500;color:#666}
td{padding:6px 8px;border-bottom:1px solid #f3f4f6}
.footer{margin-top:15px;text-align:center;font-size:8px;color:#999}
</style></head><body>
<div class="header"><h1>${workshop?.name||'Ohio Airbag Light Reset'}</h1><p>Reporte de Cuentas por Cobrar</p></div>
<div class="total-box"><div class="total-value">$${total.toFixed(2)}</div><div class="total-label">Total Adeudado</div></div>
${creditData.filter(c=>c.total_pending>0).map(c=>`
<div class="client-card">
<div class="client-header"><span class="client-name">${c.client?.name}</span><span class="client-total">$${c.total_pending?.toFixed(2)}</span></div>
<table><tr><th>Fecha</th><th>Vehículo</th><th>Monto</th></tr>
${c.pending_orders?.map((o:any)=>`<tr><td>${new Date(o.created_at).toLocaleDateString('es-ES')}</td><td>${o.vehicle}</td><td>$${o.total?.toFixed(2)}</td></tr>`).join('')||''}
</table></div>`).join('')}
<div class="footer">Generado: ${new Date().toLocaleString('es-ES')}</div>
</body></html>`;
      const { uri } = await Print.printToFileAsync({ html });
      await Sharing.shareAsync(uri, { mimeType: 'application/pdf', UTI: 'com.adobe.pdf' });
    } catch (e) { console.error(e); }
  };

  // Access check
  if (!user || user.role !== 'admin') {
    return (
      <View style={styles.container}>
        <View style={styles.accessDenied}>
          <Ionicons name="shield-outline" size={40} color="#EF4444" />
          <Text style={styles.accessTitle}>Acceso Restringido</Text>
          <Text style={styles.accessText}>Este panel es solo para administradores</Text>
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
        <Text style={styles.loadingText}>Cargando datos...</Text>
      </View>
    );
  }

  // Stats calculations
  const todayOrders = orders.filter(o => {
    const orderDate = new Date(o.created_at).toISOString().split('T')[0];
    return orderDate === new Date().toISOString().split('T')[0];
  });
  const pendingOrders = orders.filter(o => o.status !== 'terminado');
  const completedToday = todayOrders.filter(o => o.status === 'terminado');
  const totalDebt = creditData.reduce((s, c) => s + (c.total_pending || 0), 0);

  return (
    <View style={styles.container}>
      {/* Top Navigation Bar */}
      <View style={styles.navbar}>
        <View style={styles.navLeft}>
          <Text style={styles.navLogo}>OAR</Text>
          <Text style={styles.navTitle}>{workshop?.name || 'Panel de Oficina'}</Text>
        </View>
        <View style={styles.navTabs}>
          {[
            { id: 'dashboard', icon: 'grid-outline', label: 'Inicio' },
            { id: 'orders', icon: 'document-text-outline', label: 'Órdenes' },
            { id: 'clients', icon: 'people-outline', label: 'Clientes' },
            { id: 'reports', icon: 'stats-chart-outline', label: 'Reportes' },
            { id: 'credit', icon: 'card-outline', label: 'Créditos' },
          ].map(tab => (
            <TouchableOpacity 
              key={tab.id} 
              style={[styles.navTab, activeTab === tab.id && styles.navTabActive]}
              onPress={() => setActiveTab(tab.id as TabType)}
            >
              <Ionicons name={tab.icon as any} size={14} color={activeTab === tab.id ? '#3B82F6' : '#6B7280'} />
              <Text style={[styles.navTabText, activeTab === tab.id && styles.navTabTextActive]}>{tab.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
        <View style={styles.navRight}>
          <Text style={styles.navUser}>{user?.name}</Text>
          <TouchableOpacity onPress={logout} style={styles.logoutBtn}>
            <Ionicons name="log-out-outline" size={16} color="#EF4444" />
          </TouchableOpacity>
        </View>
      </View>

      {/* Main Content */}
      <ScrollView 
        style={styles.main}
        contentContainerStyle={styles.mainContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#3B82F6" />}
      >
        {/* ========== DASHBOARD ========== */}
        {activeTab === 'dashboard' && (
          <>
            {/* Quick Stats Row */}
            <View style={styles.statsGrid}>
              <View style={[styles.statCard, styles.statBlue]}>
                <View style={styles.statIcon}><Ionicons name="today-outline" size={18} color="#3B82F6" /></View>
                <View style={styles.statInfo}>
                  <Text style={styles.statValue}>{todayOrders.length}</Text>
                  <Text style={styles.statLabel}>Órdenes Hoy</Text>
                </View>
              </View>
              <View style={[styles.statCard, styles.statGreen]}>
                <View style={styles.statIcon}><Ionicons name="checkmark-circle-outline" size={18} color="#10B981" /></View>
                <View style={styles.statInfo}>
                  <Text style={[styles.statValue, {color:'#10B981'}]}>{completedToday.length}</Text>
                  <Text style={styles.statLabel}>Completadas</Text>
                </View>
              </View>
              <View style={[styles.statCard, styles.statPurple]}>
                <View style={styles.statIcon}><Ionicons name="time-outline" size={18} color="#8B5CF6" /></View>
                <View style={styles.statInfo}>
                  <Text style={[styles.statValue, {color:'#8B5CF6'}]}>{pendingOrders.length}</Text>
                  <Text style={styles.statLabel}>En Proceso</Text>
                </View>
              </View>
              <View style={[styles.statCard, styles.statOrange]}>
                <View style={styles.statIcon}><Ionicons name="cash-outline" size={18} color="#F59E0B" /></View>
                <View style={styles.statInfo}>
                  <Text style={[styles.statValue, {color:'#F59E0B'}]}>${totalDebt.toFixed(0)}</Text>
                  <Text style={styles.statLabel}>Por Cobrar</Text>
                </View>
              </View>
            </View>

            {/* Two Column Layout */}
            <View style={styles.twoColumns}>
              {/* Left: Recent Orders */}
              <View style={styles.columnWide}>
                <View style={styles.card}>
                  <View style={styles.cardHeader}>
                    <Text style={styles.cardTitle}>Últimas Órdenes</Text>
                    <TouchableOpacity onPress={() => setActiveTab('orders')}>
                      <Text style={styles.cardLink}>Ver todas →</Text>
                    </TouchableOpacity>
                  </View>
                  <View style={styles.miniTable}>
                    <View style={styles.miniTableHeader}>
                      <Text style={[styles.miniTh, {flex:2}]}>Cliente</Text>
                      <Text style={[styles.miniTh, {flex:2}]}>Vehículo</Text>
                      <Text style={[styles.miniTh, {flex:1}]}>Técnico</Text>
                      <Text style={[styles.miniTh, {flex:1}]}>Estado</Text>
                    </View>
                    {orders.slice(0, 6).map(order => (
                      <TouchableOpacity key={order.id} style={styles.miniTableRow} onPress={() => router.push(`/order/${order.id}`)}>
                        <Text style={[styles.miniTd, {flex:2}]} numberOfLines={1}>{order.client?.name || '-'}</Text>
                        <Text style={[styles.miniTd, {flex:2}]} numberOfLines={1}>
                          {order.vehicle?.year} {order.vehicle?.make} {order.vehicle?.model}
                        </Text>
                        <Text style={[styles.miniTd, {flex:1}]} numberOfLines={1}>{order.tech_name?.split(' ')[0] || '-'}</Text>
                        <View style={{flex:1}}>
                          <View style={[styles.statusBadge, {backgroundColor: getStatusColor(order.status)}]}>
                            <Text style={styles.statusText}>{getStatusLabel(order.status)}</Text>
                          </View>
                        </View>
                      </TouchableOpacity>
                    ))}
                    {orders.length === 0 && <Text style={styles.emptyText}>Sin órdenes</Text>}
                  </View>
                </View>
              </View>

              {/* Right: Quick Actions & Techs */}
              <View style={styles.columnNarrow}>
                <View style={styles.card}>
                  <Text style={styles.cardTitle}>Acciones Rápidas</Text>
                  <TouchableOpacity style={styles.actionBtn} onPress={() => router.push('/order/assign')}>
                    <View style={[styles.actionIcon, {backgroundColor:'#EEF2FF'}]}><Ionicons name="add" size={16} color="#3B82F6" /></View>
                    <Text style={styles.actionText}>Nueva Orden</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={styles.actionBtn} onPress={generateDailyPDF}>
                    <View style={[styles.actionIcon, {backgroundColor:'#ECFDF5'}]}><Ionicons name="document-text" size={16} color="#10B981" /></View>
                    <Text style={styles.actionText}>Reporte Diario PDF</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={styles.actionBtn} onPress={generateCreditPDF}>
                    <View style={[styles.actionIcon, {backgroundColor:'#FEF3C7'}]}><Ionicons name="card" size={16} color="#F59E0B" /></View>
                    <Text style={styles.actionText}>Reporte Créditos PDF</Text>
                  </TouchableOpacity>
                </View>

                <View style={styles.card}>
                  <Text style={styles.cardTitle}>Técnicos</Text>
                  {technicians.map(tech => {
                    const activeOrders = orders.filter(o => o.tech_id === tech.id && o.status !== 'terminado').length;
                    return (
                      <View key={tech.id} style={styles.techItem}>
                        <View style={[styles.techDot, {backgroundColor: activeOrders > 0 ? '#10B981' : '#D1D5DB'}]} />
                        <Text style={styles.techName}>{tech.name}</Text>
                        <Text style={styles.techCount}>{activeOrders}</Text>
                      </View>
                    );
                  })}
                  {technicians.length === 0 && <Text style={styles.emptyText}>Sin técnicos</Text>}
                </View>
              </View>
            </View>
          </>
        )}

        {/* ========== ORDERS ========== */}
        {activeTab === 'orders' && (
          <View style={styles.card}>
            <View style={styles.cardHeader}>
              <Text style={styles.cardTitle}>Órdenes de Trabajo ({filteredOrders.length})</Text>
              <TouchableOpacity style={styles.primaryBtn} onPress={() => router.push('/order/assign')}>
                <Ionicons name="add" size={14} color="#FFF" />
                <Text style={styles.primaryBtnText}>Nueva</Text>
              </TouchableOpacity>
            </View>
            
            <View style={styles.filtersRow}>
              <View style={styles.searchBox}>
                <Ionicons name="search" size={14} color="#9CA3AF" />
                <TextInput 
                  style={styles.searchInput} 
                  placeholder="Buscar cliente, vehículo, VIN..." 
                  placeholderTextColor="#9CA3AF" 
                  value={searchQuery} 
                  onChangeText={setSearchQuery}
                />
              </View>
              <View style={styles.filterTabs}>
                {[null, 'asignado', 'iniciado', 'pendiente', 'terminado'].map(st => (
                  <TouchableOpacity 
                    key={st || 'all'} 
                    style={[styles.filterTab, statusFilter === st && styles.filterTabActive]} 
                    onPress={() => setStatusFilter(st)}
                  >
                    <Text style={[styles.filterTabText, statusFilter === st && styles.filterTabTextActive]}>
                      {st ? getStatusLabel(st) : 'Todas'}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>

            <View style={styles.tableWrapper}>
              <View style={styles.tableHeader}>
                <Text style={[styles.th, {flex:2}]}>Cliente</Text>
                <Text style={[styles.th, {flex:2}]}>Vehículo</Text>
                <Text style={[styles.th, {flex:1}]}>VIN</Text>
                <Text style={[styles.th, {flex:1}]}>Técnico</Text>
                <Text style={[styles.th, {flex:1}]}>Estado</Text>
                <Text style={[styles.th, {width:60}]}>Acciones</Text>
              </View>
              {filteredOrders.map(order => (
                <View key={order.id} style={styles.tableRow}>
                  <View style={{flex:2}}>
                    <Text style={styles.td} numberOfLines={1}>{order.client?.name || '-'}</Text>
                    {order.client?.phone && (
                      <TouchableOpacity onPress={() => Linking.openURL(`tel:${order.client.phone}`)}>
                        <Text style={styles.tdLink}>{order.client.phone}</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                  <Text style={[styles.td, {flex:2}]} numberOfLines={1}>
                    {order.vehicle?.year} {order.vehicle?.make} {order.vehicle?.model}
                  </Text>
                  <Text style={[styles.tdSmall, {flex:1}]}>...{order.vehicle?.vin?.slice(-6) || 'N/A'}</Text>
                  <Text style={[styles.td, {flex:1}]} numberOfLines={1}>{order.tech_name?.split(' ')[0] || '-'}</Text>
                  <View style={{flex:1}}>
                    <View style={[styles.statusBadge, {backgroundColor: getStatusColor(order.status)}]}>
                      <Text style={styles.statusText}>{getStatusLabel(order.status)}</Text>
                    </View>
                  </View>
                  <View style={{width:60, flexDirection:'row', gap:8}}>
                    <TouchableOpacity onPress={() => router.push(`/order/${order.id}`)}>
                      <Ionicons name="eye-outline" size={16} color="#3B82F6" />
                    </TouchableOpacity>
                    {order.client?.phone && (
                      <TouchableOpacity onPress={() => Linking.openURL(`tel:${order.client.phone}`)}>
                        <Ionicons name="call-outline" size={16} color="#10B981" />
                      </TouchableOpacity>
                    )}
                  </View>
                </View>
              ))}
              {filteredOrders.length === 0 && <Text style={styles.emptyText}>No se encontraron órdenes</Text>}
            </View>
          </View>
        )}

        {/* ========== CLIENTS ========== */}
        {activeTab === 'clients' && (
          <View style={styles.card}>
            <View style={styles.cardHeader}>
              <Text style={styles.cardTitle}>Clientes ({clients.length})</Text>
            </View>
            <View style={styles.tableWrapper}>
              <View style={styles.tableHeader}>
                <Text style={[styles.th, {flex:2}]}>Nombre</Text>
                <Text style={[styles.th, {flex:1.5}]}>Teléfono</Text>
                <Text style={[styles.th, {flex:2.5}]}>Dirección</Text>
                <Text style={[styles.th, {flex:1}]}>Crédito</Text>
              </View>
              {clients.map(client => (
                <View key={client.id} style={styles.tableRow}>
                  <Text style={[styles.td, {flex:2}]}>{client.name}</Text>
                  <View style={{flex:1.5}}>
                    {client.phone ? (
                      <TouchableOpacity onPress={() => Linking.openURL(`tel:${client.phone}`)}>
                        <Text style={styles.tdLink}>{client.phone}</Text>
                      </TouchableOpacity>
                    ) : <Text style={styles.tdSmall}>-</Text>}
                  </View>
                  <Text style={[styles.tdSmall, {flex:2.5}]} numberOfLines={1}>{client.address || '-'}</Text>
                  <View style={{flex:1}}>
                    {client.has_credit && (
                      <View style={[styles.statusBadge, {backgroundColor:'#F59E0B'}]}>
                        <Text style={styles.statusText}>Crédito</Text>
                      </View>
                    )}
                  </View>
                </View>
              ))}
              {clients.length === 0 && <Text style={styles.emptyText}>Sin clientes registrados</Text>}
            </View>
          </View>
        )}

        {/* ========== REPORTS ========== */}
        {activeTab === 'reports' && (
          <View style={styles.card}>
            <View style={styles.cardHeader}>
              <Text style={styles.cardTitle}>Reporte Financiero</Text>
              <TouchableOpacity style={styles.pdfBtn} onPress={generateDailyPDF}>
                <Ionicons name="download-outline" size={14} color="#FFF" />
                <Text style={styles.pdfBtnText}>Descargar PDF</Text>
              </TouchableOpacity>
            </View>

            <View style={styles.dateNav}>
              <TouchableOpacity style={styles.dateArrow} onPress={() => {
                const d = new Date(dateFilter); d.setDate(d.getDate() - 1);
                setDateFilter(d.toISOString().split('T')[0]);
              }}>
                <Ionicons name="chevron-back" size={16} color="#3B82F6" />
              </TouchableOpacity>
              <Text style={styles.dateLabel}>
                {new Date(dateFilter).toLocaleDateString('es-ES', {weekday:'long', day:'numeric', month:'long', year:'numeric'})}
              </Text>
              <TouchableOpacity style={styles.dateArrow} onPress={() => {
                const d = new Date(dateFilter); d.setDate(d.getDate() + 1);
                setDateFilter(d.toISOString().split('T')[0]);
              }}>
                <Ionicons name="chevron-forward" size={16} color="#3B82F6" />
              </TouchableOpacity>
            </View>

            <View style={styles.reportStats}>
              <View style={[styles.reportStat, {borderLeftColor:'#3B82F6'}]}>
                <Text style={styles.reportStatValue}>{report?.total_orders || 0}</Text>
                <Text style={styles.reportStatLabel}>Órdenes</Text>
              </View>
              <View style={[styles.reportStat, {borderLeftColor:'#10B981'}]}>
                <Text style={[styles.reportStatValue, {color:'#10B981'}]}>${report?.total_paid?.toFixed(2) || '0.00'}</Text>
                <Text style={styles.reportStatLabel}>Cobrado</Text>
              </View>
              <View style={[styles.reportStat, {borderLeftColor:'#F59E0B'}]}>
                <Text style={[styles.reportStatValue, {color:'#F59E0B'}]}>${report?.total_pending?.toFixed(2) || '0.00'}</Text>
                <Text style={styles.reportStatLabel}>Pendiente</Text>
              </View>
            </View>
          </View>
        )}

        {/* ========== CREDIT ========== */}
        {activeTab === 'credit' && (
          <View style={styles.card}>
            <View style={styles.cardHeader}>
              <Text style={styles.cardTitle}>Cuentas por Cobrar</Text>
              <TouchableOpacity style={styles.pdfBtn} onPress={generateCreditPDF}>
                <Ionicons name="download-outline" size={14} color="#FFF" />
                <Text style={styles.pdfBtnText}>Descargar PDF</Text>
              </TouchableOpacity>
            </View>

            <View style={[styles.reportStat, {borderLeftColor:'#F59E0B', marginBottom:16}]}>
              <Text style={[styles.reportStatValue, {color:'#F59E0B', fontSize:24}]}>${totalDebt.toFixed(2)}</Text>
              <Text style={styles.reportStatLabel}>Total Adeudado</Text>
            </View>

            {creditData.filter(c => c.total_pending > 0).map(c => (
              <View key={c.client?.id} style={styles.creditCard}>
                <View style={styles.creditHeader}>
                  <Text style={styles.creditName}>{c.client?.name}</Text>
                  <Text style={styles.creditAmount}>${c.total_pending?.toFixed(2)}</Text>
                </View>
                {c.pending_orders?.map((o: any) => (
                  <View key={o.id} style={styles.creditRow}>
                    <Text style={styles.creditDate}>{new Date(o.created_at).toLocaleDateString('es-ES')}</Text>
                    <Text style={styles.creditVehicle}>{o.vehicle}</Text>
                    <Text style={styles.creditOrderAmount}>${o.total?.toFixed(2)}</Text>
                  </View>
                ))}
              </View>
            ))}
            {creditData.filter(c => c.total_pending > 0).length === 0 && (
              <Text style={styles.emptyText}>No hay cuentas pendientes</Text>
            )}
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F8FAFC' },
  centered: { justifyContent: 'center', alignItems: 'center' },
  loadingText: { marginTop: 10, color: '#6B7280', fontSize: 13 },
  
  // Access Denied
  accessDenied: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 20 },
  accessTitle: { fontSize: 18, fontWeight: '600', color: '#1F2937', marginTop: 12 },
  accessText: { fontSize: 13, color: '#6B7280', marginTop: 4 },
  backBtn: { marginTop: 20, backgroundColor: '#3B82F6', paddingHorizontal: 20, paddingVertical: 10, borderRadius: 6 },
  backBtnText: { color: '#FFF', fontWeight: '600' },

  // Navbar
  navbar: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#FFFFFF', borderBottomWidth: 1, borderBottomColor: '#E5E7EB', paddingHorizontal: 16, paddingVertical: 8, gap: 16 },
  navLeft: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  navLogo: { fontSize: 18, fontWeight: '800', color: '#3B82F6', backgroundColor: '#EEF2FF', paddingHorizontal: 8, paddingVertical: 4, borderRadius: 4 },
  navTitle: { fontSize: 13, fontWeight: '600', color: '#1F2937' },
  navTabs: { flex: 1, flexDirection: 'row', justifyContent: 'center', gap: 4 },
  navTab: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 4, gap: 4 },
  navTabActive: { backgroundColor: '#EEF2FF' },
  navTabText: { fontSize: 12, color: '#6B7280' },
  navTabTextActive: { color: '#3B82F6', fontWeight: '600' },
  navRight: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  navUser: { fontSize: 12, color: '#374151' },
  logoutBtn: { padding: 6, backgroundColor: '#FEF2F2', borderRadius: 4 },

  // Main
  main: { flex: 1 },
  mainContent: { padding: 16 },

  // Stats Grid
  statsGrid: { flexDirection: 'row', gap: 12, marginBottom: 16 },
  statCard: { flex: 1, backgroundColor: '#FFF', borderRadius: 8, padding: 12, flexDirection: 'row', alignItems: 'center', gap: 10, shadowColor: '#000', shadowOffset: {width:0,height:1}, shadowOpacity: 0.05, shadowRadius: 2, elevation: 1 },
  statBlue: { borderLeftWidth: 3, borderLeftColor: '#3B82F6' },
  statGreen: { borderLeftWidth: 3, borderLeftColor: '#10B981' },
  statPurple: { borderLeftWidth: 3, borderLeftColor: '#8B5CF6' },
  statOrange: { borderLeftWidth: 3, borderLeftColor: '#F59E0B' },
  statIcon: { width: 36, height: 36, borderRadius: 8, backgroundColor: '#F3F4F6', justifyContent: 'center', alignItems: 'center' },
  statInfo: {},
  statValue: { fontSize: 20, fontWeight: '700', color: '#1F2937' },
  statLabel: { fontSize: 10, color: '#6B7280', textTransform: 'uppercase', marginTop: 2 },

  // Two Columns
  twoColumns: { flexDirection: 'row', gap: 16 },
  columnWide: { flex: 2 },
  columnNarrow: { flex: 1, gap: 16 },

  // Cards
  card: { backgroundColor: '#FFF', borderRadius: 8, padding: 14, shadowColor: '#000', shadowOffset: {width:0,height:1}, shadowOpacity: 0.05, shadowRadius: 2, elevation: 1 },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, paddingBottom: 10, borderBottomWidth: 1, borderBottomColor: '#F3F4F6' },
  cardTitle: { fontSize: 13, fontWeight: '600', color: '#1F2937' },
  cardLink: { fontSize: 11, color: '#3B82F6' },

  // Mini Table (Dashboard)
  miniTable: {},
  miniTableHeader: { flexDirection: 'row', backgroundColor: '#F9FAFB', padding: 8, borderRadius: 4, marginBottom: 4 },
  miniTh: { fontSize: 9, fontWeight: '600', color: '#6B7280', textTransform: 'uppercase' },
  miniTableRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#F9FAFB' },
  miniTd: { fontSize: 11, color: '#374151' },

  // Actions
  actionBtn: { flexDirection: 'row', alignItems: 'center', padding: 10, backgroundColor: '#F9FAFB', borderRadius: 6, marginBottom: 8, gap: 10 },
  actionIcon: { width: 28, height: 28, borderRadius: 6, justifyContent: 'center', alignItems: 'center' },
  actionText: { fontSize: 12, color: '#374151', fontWeight: '500' },

  // Tech List
  techItem: { flexDirection: 'row', alignItems: 'center', paddingVertical: 8, gap: 8 },
  techDot: { width: 8, height: 8, borderRadius: 4 },
  techName: { flex: 1, fontSize: 12, color: '#374151' },
  techCount: { fontSize: 11, color: '#6B7280', backgroundColor: '#F3F4F6', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 10 },

  // Filters
  filtersRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 12 },
  searchBox: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#F9FAFB', borderRadius: 6, paddingHorizontal: 10, paddingVertical: 6, gap: 6, flex: 1, maxWidth: 280 },
  searchInput: { flex: 1, fontSize: 12, color: '#374151' },
  filterTabs: { flexDirection: 'row', gap: 4 },
  filterTab: { paddingHorizontal: 10, paddingVertical: 5, backgroundColor: '#F9FAFB', borderRadius: 4 },
  filterTabActive: { backgroundColor: '#3B82F6' },
  filterTabText: { fontSize: 11, color: '#6B7280' },
  filterTabTextActive: { color: '#FFF', fontWeight: '600' },

  // Table
  tableWrapper: {},
  tableHeader: { flexDirection: 'row', backgroundColor: '#1F2937', padding: 10, borderRadius: 4 },
  th: { fontSize: 10, fontWeight: '600', color: '#FFF', textTransform: 'uppercase' },
  tableRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 10, paddingHorizontal: 4, borderBottomWidth: 1, borderBottomColor: '#F3F4F6' },
  td: { fontSize: 12, color: '#374151' },
  tdSmall: { fontSize: 11, color: '#6B7280' },
  tdLink: { fontSize: 11, color: '#3B82F6' },

  // Status Badge
  statusBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, alignSelf: 'flex-start' },
  statusText: { fontSize: 9, color: '#FFF', fontWeight: '600' },

  // Buttons
  primaryBtn: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#3B82F6', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 4, gap: 4 },
  primaryBtnText: { color: '#FFF', fontSize: 12, fontWeight: '600' },
  pdfBtn: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#DC2626', paddingHorizontal: 10, paddingVertical: 5, borderRadius: 4, gap: 4 },
  pdfBtnText: { color: '#FFF', fontSize: 11, fontWeight: '600' },

  // Date Nav
  dateNav: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 16, marginBottom: 16, padding: 10, backgroundColor: '#F9FAFB', borderRadius: 6 },
  dateArrow: { padding: 4, backgroundColor: '#EEF2FF', borderRadius: 4 },
  dateLabel: { fontSize: 13, fontWeight: '600', color: '#374151' },

  // Report Stats
  reportStats: { flexDirection: 'row', gap: 12 },
  reportStat: { flex: 1, backgroundColor: '#F9FAFB', padding: 14, borderRadius: 6, borderLeftWidth: 3 },
  reportStatValue: { fontSize: 20, fontWeight: '700', color: '#1F2937' },
  reportStatLabel: { fontSize: 10, color: '#6B7280', textTransform: 'uppercase', marginTop: 4 },

  // Credit
  creditCard: { backgroundColor: '#F9FAFB', borderRadius: 6, overflow: 'hidden', marginBottom: 10 },
  creditHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#1F2937', padding: 10 },
  creditName: { color: '#FFF', fontSize: 12, fontWeight: '600' },
  creditAmount: { color: '#F59E0B', fontSize: 14, fontWeight: '700' },
  creditRow: { flexDirection: 'row', padding: 8, borderBottomWidth: 1, borderBottomColor: '#E5E7EB' },
  creditDate: { flex: 1, fontSize: 10, color: '#6B7280' },
  creditVehicle: { flex: 2, fontSize: 11, color: '#374151' },
  creditOrderAmount: { flex: 1, fontSize: 11, color: '#374151', textAlign: 'right' },

  emptyText: { textAlign: 'center', color: '#9CA3AF', fontSize: 12, padding: 20 },
});
