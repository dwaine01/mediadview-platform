# MediAd View Player v2.0 - Guia de Produccion
# Compatible con: Colorlight A40, Android TV, Google TV, Fire TV

## TABLA DE COMPATIBILIDAD

| Dispositivo | Instalar APK | Auto-inicio | Kiosk 24/7 | Recomendado |
|---|---|---|---|---|
| **Colorlight A40** | SI (firmware custom) | SI (firmware) | SI | ★★★★★ |
| NVIDIA Shield TV Pro | SI via ADB | SI (boot receiver) | SI | ★★★★ |
| Mecool KM2 Plus | SI via ADB | SI | SI | ★★★★ |
| Sony BRAVIA BZ30L | SI via ADB | SI | SI (rated 24/7) | ★★★★ |
| TCL Google TV | SI via ADB | Limitado (Safe Guard) | Parcial | ★★★ |
| Fire TV Stick | SI via ADB | SI | SI | ★★★ |

---

## 1. COLORLIGHT A40 (RECOMENDADO)

### 1.1 Requisitos
- Colorlight A40 con **firmware personalizado** de Colorlight
- El firmware habilita: Unknown Sources, ADB, Auto-inicio, Launcher personalizado
- Solicitar firmware a tu contacto de Colorlight (~3 dias de desarrollo)

### 1.2 Instalar Firmware Personalizado
1. Conectar A40 al PC via USB
2. Abrir **PlayerMaster** (contraseña: 168)
3. Ir a **Advanced > Firmware Update**
4. Seleccionar el firmware proporcionado por Colorlight
5. Esperar la actualizacion y reinicio

### 1.3 Instalar APK via PlayerMaster
Con el firmware actualizado:
1. Abrir PlayerMaster
2. Seleccionar Terminal (A40) en la lista
3. Ir a **Advanced > Custom APK Installation**
4. Seleccionar `mediaview-player-v2.0.0.apk`
5. Esperar la instalacion

### 1.4 Instalar APK via ADB (Alternativa)
```bash
# Conectar (el firmware habilita ADB)
adb connect [IP_DEL_A40]:5555
adb devices

# Instalar
adb install mediaview-player-v2.0.0.apk

# Configurar como launcher predeterminado
adb shell cmd package set-home-activity com.mediaview.player/.MainActivity

# Iniciar
adb shell am start -n com.mediaview.player/.MainActivity
```

### 1.5 Configurar Server URL
Opcion A - Via ADB:
```bash
adb shell am start -n com.mediaview.player/.MainActivity \
  --es server_url "https://app.mediadview.com" \
  --es screen_id "TU_SCREEN_ID"
```

Opcion B - Via Menu Oculto:
1. Con un teclado USB o control remoto, presionar **Menu 5 veces rapido**
2. Se abre el dialogo de configuracion
3. Ingresar URL del servidor y Screen ID
4. Presionar Guardar

### 1.6 Auto-inicio
Con el firmware personalizado de Colorlight:
- La app se configura como **launcher predeterminado**
- Se inicia automaticamente al encender el A40
- No requiere configuracion adicional

---

## 2. ANDROID TV / GOOGLE TV

### 2.1 Habilitar Developer Mode
1. Settings > System > About
2. Click Build Number 7 veces
3. Settings > System > Developer options
4. Activar USB debugging

### 2.2 Instalar via ADB
```bash
# Conectar
adb connect [IP_DE_LA_TV]:5555
adb devices

# Instalar
adb install mediaview-player-v2.0.0.apk

# Configurar como Home (auto-inicio)
adb shell cmd package set-home-activity com.mediaview.player/.MainActivity

# Desactivar auto-apagado
adb shell settings put system screen_off_timeout 2147483647
adb shell settings put secure screensaver_enabled 0
```

### 2.3 TCL Google TV - Configuracion Adicional
TCL tiene restricciones extra ("Safe Guard"):
1. Settings > Apps > Safe Guard > Automatic start > OFF para gestion automatica
2. Activar MediAd View en la lista
3. Settings > Apps > Special app access > Display over other apps > MediAd View ON
4. Settings > Apps > MediAd View > Battery > Unrestricted

---

## 3. FIRE TV / FIRE TV STICK

### 3.1 Habilitar Developer Mode
1. Settings > My Fire TV > About
2. Click Build Number 7 veces
3. Developer Options > ADB debugging ON
4. Apps from Unknown Sources > ON

### 3.2 Instalar
```bash
adb connect [IP]:5555
adb install mediaview-player-v2.0.0.apk
```

---

## 4. COMPILAR EL APK

### 4.1 Requisitos
- Android Studio instalado (ultima version)
- JDK 17 o superior

### 4.2 Pasos
1. Abrir Android Studio
2. **File > Open** > seleccionar la carpeta `android-player/`
3. Esperar que Gradle sincronice (puede tardar unos minutos)
4. **IMPORTANTE**: Antes de compilar, editar la URL del servidor:
   - Abrir `app/build.gradle.kts`
   - Cambiar la linea `buildConfigField("String", "SERVER_URL", ...)` a tu URL real
   - Ejemplo: `buildConfigField("String", "SERVER_URL", "\"https://app.mediadview.com\"")`
5. **Build > Clean Project**
6. **Build > Build Bundle(s) / APK(s) > Build APK(s)**
7. El APK se genera en: `app/build/outputs/apk/release/app-release.apk`

### 4.3 Firmar APK para Produccion
Para distribucion:
1. **Build > Generate Signed Bundle / APK**
2. Seleccionar APK
3. Crear o usar un Keystore existente
4. Seleccionar release
5. Build

---

## 5. FUNCIONES DEL PLAYER

### 5.1 Menu Oculto de Configuracion
Acceso: Presionar tecla **Menu** 5 veces rapido, o mantener presionado **OK/Enter** 5 segundos.
- Cambiar URL del servidor
- Cambiar Screen ID
- Ver info del dispositivo
- Reset completo (vuelve a pantalla de activacion)

### 5.2 Diagnosticos HUD
Presionar tecla **I** para mostrar/ocultar panel de diagnosticos en el reproductor web.

### 5.3 Reinicio Nocturno
El player se reinicia automaticamente a las 3:00 AM para liberar memoria y refrescar contenido.

### 5.4 Recuperacion de Crashes
Si la app falla, se reinicia automaticamente sin intervencion humana.

### 5.5 Reconexion Automatica
Si se pierde la red, el player reintenta automaticamente con backoff exponencial (5s, 10s, 15s... hasta 60s max).

### 5.6 Cache Offline
El contenido se pre-descarga y almacena localmente. Si la red falla, el ultimo contenido sigue reproduciendose.

---

## 6. ACTUALIZACIONES REMOTAS

### 6.1 Actualizar APK
```bash
adb connect [IP]:5555
adb install -r mediaview-player-v2.x.x.apk
adb shell am start -n com.mediaview.player/.MainActivity
```

### 6.2 Actualizar Contenido
El contenido se actualiza automaticamente cada 60 segundos (polling al servidor).

### 6.3 Comandos Remotos
Desde el Admin Panel de MediAd View:
- **Restart**: Reinicia el reproductor
- **Reload**: Recarga el contenido
- **Clear Cache**: Limpia cache y recarga todo

---

## 7. TROUBLESHOOTING

| Problema | Solucion |
|---|---|
| No conecta por ADB | Verificar misma red WiFi, ejecutar `adb kill-server` y reintentar |
| TV/A40 se apaga | Verificar Sleep timer OFF, Auto power off OFF |
| App no auto-inicia | Verificar que esta configurada como Home launcher |
| No muestra contenido | Verificar conexion a internet, revisar Screen ID |
| Video no reproduce | El player usa muted+autoplay, algunos contenidos necesitan recodificacion |
| Menu oculto no aparece | Intentar con teclado USB, presionar Menu 5 veces en menos de 3 seg |

---

## 8. ARQUITECTURA

```
[Colorlight A40 / TV]
       |
       | WebView carga Web Player
       |
       v
[MediAd View Server]
       |
       |-- /api/player-activate (activacion por codigo)
       |-- /api/devices/{id}/playlist (contenido)
       |-- /api/devices/{id}/heartbeat (estado + comandos)
       |-- /api/player/media/{id} (archivos multimedia)
       |
       v
[Admin Panel] --> Gestiona pantallas, campañas, dispositivos
```

---

*MediAd View Player v2.0.0 - Optimizado para Colorlight A40*
*© MediAd View LLC*
