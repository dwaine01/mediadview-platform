# MediaView Player - Guia Completa de Produccion
# Android TV / Google TV (Built-in) + Fire TV

## 1. FUNCIONA EN TVs CON ANDROID TV INTEGRADO? SI.

### Tabla de compatibilidad:

| Aspecto | TV con Android/Google TV | Box Externo (Shield, etc) |
|---|---|---|
| Sideload APK | SI via ADB | SI via ADB/USB |
| Auto-inicio | TV resume ultima app al encender | Boot receiver nativo |
| Kiosk mode | Limitado sin MDM | Mejor control |
| 24/7 operacion | Consumer TVs rated 8-16hrs/dia | Boxes para 24/7 |
| Crash recovery | SI funciona | SI funciona |
| Offline cache | SI funciona | SI funciona |
| Reconexion | SI funciona | SI funciona |

### Limitaciones CRITICAS de TVs consumer:

1. DURABILIDAD: TVs consumer rated 8-16 hrs/dia. 24/7 reduce vida util.
2. AUTO-STANDBY: Muchas TVs entran en standby despues de X horas. Desactivar Auto Power Off.
3. AUTO-UPDATES: Google TV puede actualizar y reiniciar. Desactivar auto-updates.
4. KIOSK REAL: Sin MDM no puedes bloquear HOME button. Solucion: retirar control remoto.

## 2. TVs RECOMENDADAS

### Profesionales (24/7) - RECOMENDADO:
- Sony BRAVIA BZ30L: 43-85in, Android TV, $1000-3000, rated 24/7
- Philips D-Line: 43-86in, Android SoC, $800-2500, rated 24/7

### Consumer con Google TV (uso 16hrs/dia):
- Sony BRAVIA 3 / X77L: 43-85in, $499-1300
- TCL QM6K / QM7: 50-85in, $400-1200
- Hisense U6N / U7N: 50-75in, $350-900

### Boxes dedicados (MEJOR para 24/7):
- NVIDIA Shield TV Pro: $150, mejor rendimiento
- Mecool KM2 Plus: $70, Android TV certificado
- Xiaomi Mi Box S 2nd Gen: $50, economico

### RECOMENDACION FINAL:
- Produccion 24/7: Box + TV dumb (sin smart)
- Semi-comercial 16hrs: TV con Google TV (Sony/TCL)
- Pruebas/MVP: Cualquier TV con Google TV o Fire TV Stick

## 3. GUIA DE INSTALACION

### Paso 1: Habilitar Developer Mode

Google TV:
1. Settings > System > About
2. Click Build Number 7 veces
3. Settings > System > Developer options
4. Activar USB debugging

Android TV:
1. Settings > Device Preferences > About
2. Click Build 7 veces
3. Developer options > USB debugging ON

Fire TV:
1. Settings > My Fire TV > About
2. Click Build Number 7 veces
3. Developer Options > ADB debugging ON

### Paso 2: Obtener IP de la TV
Settings > Network > (tu WiFi) > anotar IP

### Paso 3: Conectar via ADB

```
adb connect 192.168.1.100:5555
adb devices
```
La TV mostrara popup Allow USB debugging - presionar Allow.

### Paso 4: Instalar APK

```
adb install mediaview-player-v1.0.0.apk
```

### Paso 5: Configurar y Lanzar

```
adb shell am start -n com.mediaview.player/.MainActivity --es server_url "https://tu-servidor.com" --es screen_id "TU_SCREEN_ID"
```

### Paso 6: Configurar TV para Signage

```
# Desactivar auto-apagado
adb shell settings put system screen_off_timeout 2147483647

# Desactivar screensaver
adb shell settings put secure screensaver_enabled 0

# Desactivar auto-updates
adb shell settings put global auto_time 0
```

### Paso 7: Verificar
1. La TV muestra Web Player cargando
2. Presionar 'i' para diagnosticos
3. Verificar en admin panel que dispositivo aparece

## 4. ACTUALIZACIONES REMOTAS

```
adb connect 192.168.1.100:5555
adb install -r mediaview-player-v1.1.0.apk
adb shell am start -n com.mediaview.player/.MainActivity
```

El contenido se actualiza automaticamente (polling cada 60s).

## 5. TROUBLESHOOTING

- ADB no conecta: verificar misma red WiFi, reiniciar adb kill-server
- TV se apaga: Settings > Power > Sleep timer OFF, Auto power off OFF
- App no inicia al encender: TV resume ultima app, asegurar MediaView sea la ultima
- Aparece home de Google TV: sin MDM es limitacion, retirar control remoto
