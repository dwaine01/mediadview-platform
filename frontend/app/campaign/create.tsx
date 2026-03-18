import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  TextInput, ActivityIndicator, Alert, Image,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { screensAPI, campaignsAPI, mediaAPI, paymentsAPI } from '../../src/services/api';
import { Screen } from '../../src/types';
import { CITY_COLORS } from '../../src/constants/theme';

const STEPS = ['Screen', 'Schedule', 'Media', 'Review'];
const TIME_OPTIONS = ['06:00', '08:00', '10:00', '12:00', '14:00', '16:00', '18:00', '20:00', '22:00'];
const DURATION_OPTIONS = [10, 15, 30];

export default function CreateCampaignScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  // Step 1: Screen selection
  const [screens, setScreens] = useState<Screen[]>([]);
  const [selectedScreen, setSelectedScreen] = useState<Screen | null>(null);

  // Step 2: Schedule
  const [campaignName, setCampaignName] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [startTime, setStartTime] = useState('08:00');
  const [endTime, setEndTime] = useState('22:00');
  const [slotDuration, setSlotDuration] = useState(15);
  const [pricing, setPricing] = useState<any>(null);

  // Step 3: Media
  const [mediaImage, setMediaImage] = useState<any>(null);
  const [mediaId, setMediaId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    screensAPI.list().then(res => {
      setScreens(res.data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  // Calculate price when schedule changes
  useEffect(() => {
    if (selectedScreen && startDate && endDate && startTime && endTime) {
      screensAPI.calculatePrice(selectedScreen.id, {
        start_date: startDate, end_date: endDate,
        start_time: startTime, end_time: endTime,
        slot_duration: slotDuration, frequency: 5,
      }).then(res => setPricing(res.data)).catch(() => {});
    }
  }, [selectedScreen, startDate, endDate, startTime, endTime, slotDuration]);

  const pickImage = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsEditing: true,
      aspect: [16, 9],
      quality: 0.8,
      base64: true,
    });
    if (!result.canceled && result.assets[0]) {
      const asset = result.assets[0];
      setMediaImage(asset);
      setUploading(true);
      try {
        const res = await mediaAPI.upload({
          filename: asset.fileName || 'campaign_media.jpg',
          content_type: 'image/jpeg',
          data: asset.base64,
        });
        setMediaId(res.data.id);
      } catch (e: any) {
        Alert.alert('Upload Error', e.response?.data?.detail || 'Failed to upload media');
        setMediaImage(null);
      } finally {
        setUploading(false);
      }
    }
  };

  const handleSubmit = async () => {
    if (!selectedScreen || !campaignName || !startDate || !endDate || !mediaId) {
      Alert.alert('Error', 'Please complete all steps');
      return;
    }
    setSubmitting(true);
    try {
      const campaignRes = await campaignsAPI.create({
        name: campaignName,
        screen_id: selectedScreen.id,
        schedule: {
          start_date: startDate, end_date: endDate,
          start_time: startTime, end_time: endTime,
          slot_duration: slotDuration, frequency: 5,
        },
        media_ids: [mediaId],
      });

      // Mock payment
      await paymentsAPI.create({
        campaign_id: campaignRes.data.id,
        method: 'card',
        card_last4: '4242',
      });

      Alert.alert(
        'Campaign Submitted!',
        'Your campaign has been submitted for review. You will be notified once approved.',
        [{ text: 'OK', onPress: () => router.replace('/(tabs)/campaigns') }]
      );
    } catch (e: any) {
      Alert.alert('Error', e.response?.data?.detail || 'Failed to create campaign');
    } finally {
      setSubmitting(false);
    }
  };

  const canNext = () => {
    if (step === 0) return !!selectedScreen;
    if (step === 1) return !!campaignName && !!startDate && !!endDate;
    if (step === 2) return !!mediaId;
    return true;
  };

  const getCityColor = (city: string) => CITY_COLORS[city] || '#4F46E5';

  const renderStep = () => {
    if (step === 0) {
      return (
        <ScrollView style={styles.stepContent}>
          <Text style={styles.stepTitle}>Select a Screen</Text>
          <Text style={styles.stepDesc}>Choose where to display your advertisement</Text>
          {screens.map(s => (
            <TouchableOpacity
              key={s.id}
              style={[styles.screenCard, selectedScreen?.id === s.id && styles.screenCardSelected]}
              onPress={() => setSelectedScreen(s)}
            >
              <View style={[styles.screenThumb, { backgroundColor: getCityColor(s.location?.city) }]}>
                <Ionicons name="tv" size={24} color="rgba(255,255,255,0.4)" />
              </View>
              <View style={styles.screenCardInfo}>
                <Text style={styles.screenCardName} numberOfLines={1}>{s.name}</Text>
                <Text style={styles.screenCardCity}>{s.location?.city}, {s.location?.state}</Text>
                <Text style={styles.screenCardPrice}>${s.pricing?.per_hour}/hr</Text>
              </View>
              {selectedScreen?.id === s.id && (
                <Ionicons name="checkmark-circle" size={24} color="#4F46E5" />
              )}
            </TouchableOpacity>
          ))}
        </ScrollView>
      );
    }

    if (step === 1) {
      return (
        <ScrollView style={styles.stepContent} keyboardShouldPersistTaps="handled">
          <Text style={styles.stepTitle}>Campaign Schedule</Text>
          <Text style={styles.stepDesc}>Set your campaign dates and preferences</Text>

          <Text style={styles.fieldLabel}>Campaign Name *</Text>
          <TextInput
            style={styles.fieldInput}
            placeholder="e.g. Summer Sale Promo"
            placeholderTextColor="#94A3B8"
            value={campaignName}
            onChangeText={setCampaignName}
          />

          <View style={styles.dateRow}>
            <View style={styles.dateField}>
              <Text style={styles.fieldLabel}>Start Date *</Text>
              <TextInput
                style={styles.fieldInput}
                placeholder="YYYY-MM-DD"
                placeholderTextColor="#94A3B8"
                value={startDate}
                onChangeText={setStartDate}
              />
            </View>
            <View style={styles.dateField}>
              <Text style={styles.fieldLabel}>End Date *</Text>
              <TextInput
                style={styles.fieldInput}
                placeholder="YYYY-MM-DD"
                placeholderTextColor="#94A3B8"
                value={endDate}
                onChangeText={setEndDate}
              />
            </View>
          </View>

          <Text style={styles.fieldLabel}>Start Time</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipRow}>
            {TIME_OPTIONS.map(t => (
              <TouchableOpacity
                key={t}
                style={[styles.chip, startTime === t && styles.chipActive]}
                onPress={() => setStartTime(t)}
              >
                <Text style={[styles.chipText, startTime === t && styles.chipTextActive]}>{t}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <Text style={styles.fieldLabel}>End Time</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipRow}>
            {TIME_OPTIONS.map(t => (
              <TouchableOpacity
                key={t}
                style={[styles.chip, endTime === t && styles.chipActive]}
                onPress={() => setEndTime(t)}
              >
                <Text style={[styles.chipText, endTime === t && styles.chipTextActive]}>{t}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <Text style={styles.fieldLabel}>Slot Duration</Text>
          <View style={styles.durationRow}>
            {DURATION_OPTIONS.map(d => (
              <TouchableOpacity
                key={d}
                style={[styles.durationBtn, slotDuration === d && styles.durationBtnActive]}
                onPress={() => setSlotDuration(d)}
              >
                <Text style={[styles.durationText, slotDuration === d && styles.durationTextActive]}>{d}s</Text>
              </TouchableOpacity>
            ))}
          </View>

          {pricing && (
            <View style={styles.pricePreview}>
              <Text style={styles.pricePreviewTitle}>Estimated Price</Text>
              <View style={styles.priceRow}>
                <Text style={styles.priceLabel}>{pricing.total_hours} hours x ${pricing.per_hour}/hr</Text>
                <Text style={styles.priceValue}>${pricing.subtotal?.toLocaleString()}</Text>
              </View>
              <View style={styles.priceRow}>
                <Text style={styles.priceLabel}>Tax (8%)</Text>
                <Text style={styles.priceValue}>${pricing.tax?.toLocaleString()}</Text>
              </View>
              <View style={styles.priceDivider} />
              <View style={styles.priceRow}>
                <Text style={styles.priceTotalLabel}>Total</Text>
                <Text style={styles.priceTotalValue}>${pricing.total?.toLocaleString()}</Text>
              </View>
            </View>
          )}
        </ScrollView>
      );
    }

    if (step === 2) {
      return (
        <ScrollView style={styles.stepContent}>
          <Text style={styles.stepTitle}>Upload Media</Text>
          <Text style={styles.stepDesc}>Upload your ad creative (JPG, PNG supported)</Text>

          {mediaImage ? (
            <View style={styles.mediaPreview}>
              <Image source={{ uri: mediaImage.uri }} style={styles.previewImage} resizeMode="cover" />
              <TouchableOpacity style={styles.removeMediaBtn} onPress={() => { setMediaImage(null); setMediaId(null); }}>
                <Ionicons name="close-circle" size={28} color="#EF4444" />
              </TouchableOpacity>
              {uploading && (
                <View style={styles.uploadOverlay}>
                  <ActivityIndicator size="large" color="#FFFFFF" />
                  <Text style={styles.uploadText}>Uploading...</Text>
                </View>
              )}
            </View>
          ) : (
            <TouchableOpacity style={styles.uploadArea} onPress={pickImage}>
              <Ionicons name="cloud-upload-outline" size={48} color="#94A3B8" />
              <Text style={styles.uploadAreaText}>Tap to upload image</Text>
              <Text style={styles.uploadAreaSub}>JPG, PNG - Optimized for 1920x1080</Text>
            </TouchableOpacity>
          )}

          <View style={styles.mediaInfo}>
            <Ionicons name="information-circle-outline" size={18} color="#64748B" />
            <Text style={styles.mediaInfoText}>
              For best results, upload images in 16:9 aspect ratio (1920x1080).
              Your media will be displayed on the selected LED screen.
            </Text>
          </View>
        </ScrollView>
      );
    }

    // Step 3: Review
    return (
      <ScrollView style={styles.stepContent}>
        <Text style={styles.stepTitle}>Review & Pay</Text>
        <Text style={styles.stepDesc}>Confirm your campaign details</Text>

        <View style={styles.reviewCard}>
          <Text style={styles.reviewSection}>Campaign</Text>
          <Text style={styles.reviewValue}>{campaignName}</Text>
        </View>

        <View style={styles.reviewCard}>
          <Text style={styles.reviewSection}>Screen</Text>
          <Text style={styles.reviewValue}>{selectedScreen?.name}</Text>
          <Text style={styles.reviewSub}>{selectedScreen?.location?.city}, {selectedScreen?.location?.state}</Text>
        </View>

        <View style={styles.reviewCard}>
          <Text style={styles.reviewSection}>Schedule</Text>
          <Text style={styles.reviewValue}>{startDate} to {endDate}</Text>
          <Text style={styles.reviewSub}>{startTime} - {endTime} | {slotDuration}s slots</Text>
        </View>

        {pricing && (
          <View style={styles.reviewCard}>
            <Text style={styles.reviewSection}>Price Breakdown</Text>
            <View style={styles.priceRow}>
              <Text style={styles.priceLabel}>Subtotal ({pricing.total_hours}hrs)</Text>
              <Text style={styles.priceValue}>${pricing.subtotal?.toLocaleString()}</Text>
            </View>
            <View style={styles.priceRow}>
              <Text style={styles.priceLabel}>Tax</Text>
              <Text style={styles.priceValue}>${pricing.tax?.toLocaleString()}</Text>
            </View>
            <View style={styles.priceDivider} />
            <View style={styles.priceRow}>
              <Text style={styles.priceTotalLabel}>Total</Text>
              <Text style={styles.priceTotalValue}>${pricing.total?.toLocaleString()}</Text>
            </View>
          </View>
        )}

        <View style={styles.mockPayment}>
          <Ionicons name="card" size={20} color="#64748B" />
          <Text style={styles.mockPaymentText}>Payment: **** **** **** 4242 (Simulated)</Text>
        </View>

        <TouchableOpacity
          style={[styles.payButton, submitting && styles.payButtonDisabled]}
          onPress={handleSubmit}
          disabled={submitting}
        >
          {submitting ? (
            <ActivityIndicator color="#FFFFFF" />
          ) : (
            <>
              <Ionicons name="checkmark-circle" size={22} color="#FFFFFF" />
              <Text style={styles.payButtonText}>Pay & Submit Campaign</Text>
            </>
          )}
        </TouchableOpacity>
      </ScrollView>
    );
  };

  if (loading) {
    return <View style={[styles.center, { paddingTop: insets.top }]}><ActivityIndicator size="large" color="#4F46E5" /></View>;
  }

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={22} color="#0F172A" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Create Campaign</Text>
        <View style={{ width: 40 }} />
      </View>

      {/* Step Indicator */}
      <View style={styles.stepIndicator}>
        {STEPS.map((s, i) => (
          <View key={i} style={styles.stepItem}>
            <View style={[styles.stepDot, i <= step && styles.stepDotActive,
              i < step && styles.stepDotDone]}>
              {i < step ? (
                <Ionicons name="checkmark" size={14} color="#FFFFFF" />
              ) : (
                <Text style={[styles.stepNum, i <= step && styles.stepNumActive]}>{i + 1}</Text>
              )}
            </View>
            <Text style={[styles.stepLabel, i <= step && styles.stepLabelActive]}>{s}</Text>
            {i < STEPS.length - 1 && <View style={[styles.stepLine, i < step && styles.stepLineActive]} />}
          </View>
        ))}
      </View>

      {/* Content */}
      {renderStep()}

      {/* Navigation */}
      <View style={[styles.navBar, { paddingBottom: insets.bottom + 12 }]}>
        {step > 0 && (
          <TouchableOpacity style={styles.navBack} onPress={() => setStep(step - 1)}>
            <Ionicons name="arrow-back" size={20} color="#4F46E5" />
            <Text style={styles.navBackText}>Back</Text>
          </TouchableOpacity>
        )}
        {step < 3 && (
          <TouchableOpacity
            style={[styles.navNext, !canNext() && styles.navNextDisabled]}
            onPress={() => canNext() && setStep(step + 1)}
            disabled={!canNext()}
          >
            <Text style={styles.navNextText}>Next</Text>
            <Ionicons name="arrow-forward" size={20} color="#FFFFFF" />
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F1F5F9' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#F1F5F9' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingVertical: 12,
  },
  backBtn: { width: 40, height: 40, borderRadius: 10, backgroundColor: '#FFFFFF', justifyContent: 'center', alignItems: 'center' },
  headerTitle: { fontSize: 18, fontWeight: '700', color: '#0F172A' },
  stepIndicator: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 24, paddingVertical: 12 },
  stepItem: { flexDirection: 'row', alignItems: 'center' },
  stepDot: {
    width: 28, height: 28, borderRadius: 14, backgroundColor: '#E2E8F0',
    justifyContent: 'center', alignItems: 'center',
  },
  stepDotActive: { backgroundColor: '#4F46E5' },
  stepDotDone: { backgroundColor: '#10B981' },
  stepNum: { fontSize: 12, fontWeight: '700', color: '#94A3B8' },
  stepNumActive: { color: '#FFFFFF' },
  stepLabel: { fontSize: 11, color: '#94A3B8', marginLeft: 4, fontWeight: '600' },
  stepLabelActive: { color: '#4F46E5' },
  stepLine: { width: 20, height: 2, backgroundColor: '#E2E8F0', marginHorizontal: 4 },
  stepLineActive: { backgroundColor: '#10B981' },
  stepContent: { flex: 1, paddingHorizontal: 20 },
  stepTitle: { fontSize: 22, fontWeight: '700', color: '#0F172A', marginBottom: 4 },
  stepDesc: { fontSize: 14, color: '#64748B', marginBottom: 20 },
  screenCard: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: '#FFFFFF',
    borderRadius: 14, padding: 12, marginBottom: 10,
    borderWidth: 2, borderColor: 'transparent',
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.04, shadowRadius: 4, elevation: 1,
  },
  screenCardSelected: { borderColor: '#4F46E5' },
  screenThumb: {
    width: 56, height: 56, borderRadius: 12, justifyContent: 'center', alignItems: 'center', marginRight: 12,
  },
  screenCardInfo: { flex: 1 },
  screenCardName: { fontSize: 15, fontWeight: '600', color: '#0F172A' },
  screenCardCity: { fontSize: 12, color: '#64748B', marginTop: 2 },
  screenCardPrice: { fontSize: 14, fontWeight: '700', color: '#4F46E5', marginTop: 4 },
  fieldLabel: { fontSize: 13, fontWeight: '600', color: '#374151', marginBottom: 6, marginTop: 12 },
  fieldInput: {
    backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0',
    borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12,
    fontSize: 15, color: '#0F172A',
  },
  dateRow: { flexDirection: 'row', gap: 12 },
  dateField: { flex: 1 },
  chipRow: { marginBottom: 8, maxHeight: 44 },
  chip: {
    paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10,
    backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E2E8F0', marginRight: 8,
  },
  chipActive: { backgroundColor: '#4F46E5', borderColor: '#4F46E5' },
  chipText: { fontSize: 13, fontWeight: '600', color: '#64748B' },
  chipTextActive: { color: '#FFFFFF' },
  durationRow: { flexDirection: 'row', gap: 12, marginBottom: 16 },
  durationBtn: {
    flex: 1, paddingVertical: 14, borderRadius: 12, backgroundColor: '#FFFFFF',
    alignItems: 'center', borderWidth: 1, borderColor: '#E2E8F0',
  },
  durationBtnActive: { backgroundColor: '#4F46E5', borderColor: '#4F46E5' },
  durationText: { fontSize: 16, fontWeight: '700', color: '#64748B' },
  durationTextActive: { color: '#FFFFFF' },
  pricePreview: {
    backgroundColor: '#FFFFFF', borderRadius: 14, padding: 16, marginTop: 16,
    borderWidth: 1, borderColor: '#E2E8F0',
  },
  pricePreviewTitle: { fontSize: 14, fontWeight: '700', color: '#0F172A', marginBottom: 10 },
  priceRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 },
  priceLabel: { fontSize: 14, color: '#64748B' },
  priceValue: { fontSize: 14, fontWeight: '600', color: '#0F172A' },
  priceDivider: { height: 1, backgroundColor: '#E2E8F0', marginVertical: 8 },
  priceTotalLabel: { fontSize: 16, fontWeight: '700', color: '#0F172A' },
  priceTotalValue: { fontSize: 20, fontWeight: '700', color: '#4F46E5' },
  uploadArea: {
    backgroundColor: '#FFFFFF', borderRadius: 16, padding: 40, alignItems: 'center',
    borderWidth: 2, borderStyle: 'dashed', borderColor: '#CBD5E1',
  },
  uploadAreaText: { fontSize: 16, fontWeight: '600', color: '#64748B', marginTop: 12 },
  uploadAreaSub: { fontSize: 12, color: '#94A3B8', marginTop: 4 },
  mediaPreview: { borderRadius: 16, overflow: 'hidden', marginBottom: 16 },
  previewImage: { width: '100%', height: 200, borderRadius: 16 },
  removeMediaBtn: { position: 'absolute', top: 8, right: 8 },
  uploadOverlay: {
    ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center', alignItems: 'center', borderRadius: 16,
  },
  uploadText: { color: '#FFFFFF', fontSize: 14, fontWeight: '600', marginTop: 8 },
  mediaInfo: {
    flexDirection: 'row', gap: 8, backgroundColor: '#F8FAFC',
    padding: 14, borderRadius: 12, marginTop: 12,
  },
  mediaInfoText: { flex: 1, fontSize: 13, color: '#64748B', lineHeight: 18 },
  reviewCard: {
    backgroundColor: '#FFFFFF', borderRadius: 14, padding: 16, marginBottom: 12,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.04, shadowRadius: 4, elevation: 1,
  },
  reviewSection: { fontSize: 12, fontWeight: '600', color: '#64748B', textTransform: 'uppercase', marginBottom: 6 },
  reviewValue: { fontSize: 16, fontWeight: '600', color: '#0F172A' },
  reviewSub: { fontSize: 13, color: '#64748B', marginTop: 2 },
  mockPayment: {
    flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: '#FEF3C7',
    padding: 14, borderRadius: 12, marginBottom: 16,
  },
  mockPaymentText: { fontSize: 13, color: '#92400E', flex: 1 },
  payButton: {
    flexDirection: 'row', backgroundColor: '#10B981', borderRadius: 14,
    paddingVertical: 16, alignItems: 'center', justifyContent: 'center', gap: 8, marginBottom: 20,
  },
  payButtonDisabled: { opacity: 0.6 },
  payButtonText: { color: '#FFFFFF', fontSize: 16, fontWeight: '700' },
  navBar: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: 20, paddingTop: 12, borderTopWidth: 1, borderTopColor: '#E2E8F0',
    backgroundColor: '#FFFFFF',
  },
  navBack: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 10, paddingHorizontal: 16 },
  navBackText: { fontSize: 15, fontWeight: '600', color: '#4F46E5' },
  navNext: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: '#4F46E5', paddingVertical: 12, paddingHorizontal: 24, borderRadius: 12, marginLeft: 'auto',
  },
  navNextDisabled: { opacity: 0.4 },
  navNextText: { fontSize: 15, fontWeight: '700', color: '#FFFFFF' },
});
