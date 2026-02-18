import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Alert,
  Modal,
  TextInput,
  RefreshControl,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuthStore } from '../../src/store/authStore';
import { getWorkshop, getUsers, createUser, updateWorkshop } from '../../src/services/api';
import { Workshop, User } from '../../src/types';

export default function SettingsScreen() {
  const { user, logout } = useAuthStore();
  const [workshop, setWorkshop] = useState<Workshop | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [userModalVisible, setUserModalVisible] = useState(false);
  const [taxModalVisible, setTaxModalVisible] = useState(false);
  const [newUser, setNewUser] = useState({
    name: '',
    email: '',
    password: '',
    role: 'tech',
  });
  const [newTaxRate, setNewTaxRate] = useState('');
  const [workshopModalVisible, setWorkshopModalVisible] = useState(false);
  const [editWorkshop, setEditWorkshop] = useState({
    name: '',
    phone: '',
    address: '',
  });

  const isAdmin = user?.role === 'admin';

  const loadData = async () => {
    try {
      const [workshopRes, usersRes] = await Promise.all([
        getWorkshop(),
        isAdmin ? getUsers() : Promise.resolve([]),
      ]);
      setWorkshop(workshopRes);
      if (isAdmin) setUsers(usersRes);
    } catch (error) {
      console.error('Error loading settings:', error);
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

  const handleLogout = () => {
    Alert.alert(
      'Cerrar Sesión',
      '¿Estás seguro que deseas salir?',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Salir',
          style: 'destructive',
          onPress: async () => {
            await logout();
            router.replace('/(auth)/login');
          },
        },
      ]
    );
  };

  const handleCreateUser = async () => {
    if (!newUser.name.trim() || !newUser.email.trim() || !newUser.password.trim()) {
      Alert.alert('Error', 'Todos los campos son requeridos');
      return;
    }

    try {
      await createUser({
        ...newUser,
        workshop_id: user?.workshop_id || '',
      });
      setUserModalVisible(false);
      setNewUser({ name: '', email: '', password: '', role: 'tech' });
      loadData();
      Alert.alert('Éxito', 'Usuario creado correctamente');
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Error al crear usuario');
    }
  };

  const handleUpdateTax = async () => {
    const rate = parseFloat(newTaxRate);
    if (isNaN(rate) || rate < 0 || rate > 100) {
      Alert.alert('Error', 'Ingrese un porcentaje válido (0-100)');
      return;
    }

    try {
      await updateWorkshop({ tax_rate: rate });
      setTaxModalVisible(false);
      setNewTaxRate('');
      loadData();
      Alert.alert('Éxito', 'Impuesto actualizado');
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Error al actualizar');
    }
  };

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#3B82F6" />
      }
    >
      {/* Profile Section */}
      <View style={styles.section}>
        <View style={styles.profileCard}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>
              {user?.name?.charAt(0).toUpperCase()}
            </Text>
          </View>
          <View style={styles.profileInfo}>
            <Text style={styles.profileName}>{user?.name}</Text>
            <Text style={styles.profileEmail}>{user?.email}</Text>
            <View style={styles.roleBadge}>
              <Text style={styles.roleText}>
                {isAdmin ? 'Administrador' : 'Técnico'}
              </Text>
            </View>
          </View>
        </View>
      </View>

      {/* Workshop Info */}
      {workshop && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Taller</Text>
          <View style={styles.card}>
            <View style={styles.cardRow}>
              <Ionicons name="business" size={20} color="#3B82F6" />
              <Text style={styles.cardText}>{workshop.name}</Text>
            </View>
            {workshop.phone && (
              <View style={styles.cardRow}>
                <Ionicons name="call" size={20} color="#6B7280" />
                <Text style={styles.cardTextSecondary}>{workshop.phone}</Text>
              </View>
            )}
            {workshop.address && (
              <View style={styles.cardRow}>
                <Ionicons name="location" size={20} color="#6B7280" />
                <Text style={styles.cardTextSecondary}>{workshop.address}</Text>
              </View>
            )}
          </View>
        </View>
      )}

      {/* Admin Options */}
      {isAdmin && (
        <>
          {/* Tax Settings */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Configuración</Text>
            <TouchableOpacity
              style={styles.optionCard}
              onPress={() => {
                setNewTaxRate(workshop?.tax_rate?.toString() || '');
                setTaxModalVisible(true);
              }}
            >
              <View style={styles.optionInfo}>
                <Ionicons name="receipt" size={24} color="#3B82F6" />
                <View style={styles.optionText}>
                  <Text style={styles.optionTitle}>Impuesto</Text>
                  <Text style={styles.optionSubtitle}>{workshop?.tax_rate || 0}%</Text>
                </View>
              </View>
              <Ionicons name="chevron-forward" size={20} color="#6B7280" />
            </TouchableOpacity>
          </View>

          {/* Users Section */}
          <View style={styles.section}>
            <View style={styles.sectionHeader}>
              <Text style={styles.sectionTitle}>Usuarios</Text>
              <TouchableOpacity
                style={styles.addButton}
                onPress={() => setUserModalVisible(true)}
              >
                <Ionicons name="add" size={20} color="#FFFFFF" />
                <Text style={styles.addButtonText}>Agregar</Text>
              </TouchableOpacity>
            </View>
            {users.map((u) => (
              <View key={u.id} style={styles.userCard}>
                <View style={styles.userAvatar}>
                  <Text style={styles.userAvatarText}>
                    {u.name.charAt(0).toUpperCase()}
                  </Text>
                </View>
                <View style={styles.userInfo}>
                  <Text style={styles.userName}>{u.name}</Text>
                  <Text style={styles.userEmail}>{u.email}</Text>
                </View>
                <View style={[styles.userRole, u.role === 'admin' && styles.userRoleAdmin]}>
                  <Text style={styles.userRoleText}>
                    {u.role === 'admin' ? 'Admin' : 'Técnico'}
                  </Text>
                </View>
              </View>
            ))}
          </View>
        </>
      )}

      {/* Logout */}
      <View style={styles.section}>
        <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
          <Ionicons name="log-out" size={24} color="#EF4444" />
          <Text style={styles.logoutText}>Cerrar Sesión</Text>
        </TouchableOpacity>
      </View>

      {/* Create User Modal */}
      <Modal
        visible={userModalVisible}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setUserModalVisible(false)}
      >
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.modalOverlay}
        >
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Nuevo Usuario</Text>
              <TouchableOpacity onPress={() => setUserModalVisible(false)}>
                <Ionicons name="close" size={24} color="#FFFFFF" />
              </TouchableOpacity>
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Nombre</Text>
              <TextInput
                style={styles.input}
                placeholder="Nombre completo"
                placeholderTextColor="#6B7280"
                value={newUser.name}
                onChangeText={(text) => setNewUser({ ...newUser, name: text })}
              />
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Email</Text>
              <TextInput
                style={styles.input}
                placeholder="Correo electrónico"
                placeholderTextColor="#6B7280"
                value={newUser.email}
                onChangeText={(text) => setNewUser({ ...newUser, email: text })}
                keyboardType="email-address"
                autoCapitalize="none"
              />
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Contraseña</Text>
              <TextInput
                style={styles.input}
                placeholder="Contraseña"
                placeholderTextColor="#6B7280"
                value={newUser.password}
                onChangeText={(text) => setNewUser({ ...newUser, password: text })}
                secureTextEntry
              />
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Rol</Text>
              <View style={styles.roleSelector}>
                <TouchableOpacity
                  style={[
                    styles.roleOption,
                    newUser.role === 'tech' && styles.roleOptionActive,
                  ]}
                  onPress={() => setNewUser({ ...newUser, role: 'tech' })}
                >
                  <Text
                    style={[
                      styles.roleOptionText,
                      newUser.role === 'tech' && styles.roleOptionTextActive,
                    ]}
                  >
                    Técnico
                  </Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[
                    styles.roleOption,
                    newUser.role === 'admin' && styles.roleOptionActive,
                  ]}
                  onPress={() => setNewUser({ ...newUser, role: 'admin' })}
                >
                  <Text
                    style={[
                      styles.roleOptionText,
                      newUser.role === 'admin' && styles.roleOptionTextActive,
                    ]}
                  >
                    Admin
                  </Text>
                </TouchableOpacity>
              </View>
            </View>

            <TouchableOpacity style={styles.saveButton} onPress={handleCreateUser}>
              <Text style={styles.saveButtonText}>Crear Usuario</Text>
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Tax Modal */}
      <Modal
        visible={taxModalVisible}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setTaxModalVisible(false)}
      >
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.modalOverlay}
        >
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Configurar Impuesto</Text>
              <TouchableOpacity onPress={() => setTaxModalVisible(false)}>
                <Ionicons name="close" size={24} color="#FFFFFF" />
              </TouchableOpacity>
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Porcentaje de Impuesto (%)</Text>
              <TextInput
                style={styles.input}
                placeholder="7.0"
                placeholderTextColor="#6B7280"
                value={newTaxRate}
                onChangeText={setNewTaxRate}
                keyboardType="decimal-pad"
              />
            </View>

            <TouchableOpacity style={styles.saveButton} onPress={handleUpdateTax}>
              <Text style={styles.saveButtonText}>Guardar</Text>
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#111827',
  },
  section: {
    padding: 16,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 16,
  },
  profileCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1F2937',
    borderRadius: 16,
    padding: 20,
  },
  avatar: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: '#3B82F6',
    justifyContent: 'center',
    alignItems: 'center',
  },
  avatarText: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  profileInfo: {
    marginLeft: 16,
    flex: 1,
  },
  profileName: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  profileEmail: {
    fontSize: 14,
    color: '#9CA3AF',
    marginTop: 4,
  },
  roleBadge: {
    backgroundColor: '#374151',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
    alignSelf: 'flex-start',
    marginTop: 8,
  },
  roleText: {
    fontSize: 12,
    color: '#D1D5DB',
  },
  card: {
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 16,
  },
  cardRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  cardText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
    marginLeft: 12,
  },
  cardTextSecondary: {
    fontSize: 14,
    color: '#9CA3AF',
    marginLeft: 12,
  },
  optionCard: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 16,
  },
  optionInfo: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  optionText: {
    marginLeft: 16,
  },
  optionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  optionSubtitle: {
    fontSize: 14,
    color: '#9CA3AF',
  },
  addButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#3B82F6',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
    gap: 4,
  },
  addButtonText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '600',
  },
  userCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1F2937',
    borderRadius: 12,
    padding: 16,
    marginBottom: 8,
  },
  userAvatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#374151',
    justifyContent: 'center',
    alignItems: 'center',
  },
  userAvatarText: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  userInfo: {
    flex: 1,
    marginLeft: 12,
  },
  userName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  userEmail: {
    fontSize: 13,
    color: '#9CA3AF',
  },
  userRole: {
    backgroundColor: '#374151',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  userRoleAdmin: {
    backgroundColor: '#3B82F6',
  },
  userRoleText: {
    fontSize: 12,
    color: '#FFFFFF',
  },
  logoutButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(239, 68, 68, 0.1)',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: 'rgba(239, 68, 68, 0.3)',
  },
  logoutText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#EF4444',
    marginLeft: 8,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#1F2937',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: 24,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 24,
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  inputGroup: {
    marginBottom: 16,
  },
  inputLabel: {
    fontSize: 14,
    color: '#9CA3AF',
    marginBottom: 8,
  },
  input: {
    backgroundColor: '#374151',
    borderRadius: 12,
    paddingHorizontal: 16,
    height: 48,
    color: '#FFFFFF',
    fontSize: 16,
  },
  roleSelector: {
    flexDirection: 'row',
    gap: 8,
  },
  roleOption: {
    flex: 1,
    backgroundColor: '#374151',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  roleOptionActive: {
    backgroundColor: '#3B82F6',
  },
  roleOptionText: {
    color: '#9CA3AF',
    fontSize: 14,
  },
  roleOptionTextActive: {
    color: '#FFFFFF',
    fontWeight: '600',
  },
  saveButton: {
    backgroundColor: '#3B82F6',
    borderRadius: 12,
    height: 50,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 16,
  },
  saveButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
});
