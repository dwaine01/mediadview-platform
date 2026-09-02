# MediAd View Player v3.0 - Guía de Producción
# Compatible con: onn Android TV/Google TV, Android TV, Colorlight A40, Fire TV

## TABLA DE COMPATIBILIDAD

| Dispositivo | Instalar APK | Auto-inicio | Kiosk 24/7 | Recomendado |
|---|---|---|---|---|
| **onn 4K / onn 4K Pro** | SI via ADB/red | SI como HOME | SI tras provisión | ★★★★★ |
| Colorlight A40 | SI (firmware custom) | SI (firmware) | SI | ★★★★★ |
| NVIDIA Shield TV Pro | SI via ADB | SI (boot receiver) | SI | ★★★★ |
| Mecool KM2 Plus | SI via ADB | SI | SI | ★★★★ |
| Sony BRAVIA BZ30L | SI via ADB | SI | SI (rated 24/7) | ★★★★ |
| TCL Google TV | SI via ADB | Limitado (Safe Guard) | Parcial | ★★★ |
| Fire TV Stick | SI via ADB | SI | SI | ★★★ |

---

## 1. ONN ANDROID TV / GOOGLE TV (OBJETIVO DE VALIDACIÓN)

### 1.1 Preparación
1. Conectar el onn al televisor y a la misma red del computador.
2. Activar Developer options y Wireless debugging/USB debugging.
3. Instalar `mediaview-player-v3.0.0-diagnostic.apk` mediante ADB.

```bash
adb connect IP_DEL_ONN:5555
adb install -r mediaview-player-v3.0.0-diagnostic.apk
adb shell cmd package set-home-activity com.mediaview.player/.MainActivity
adb shell am start -n com.mediaview.player/.MainActivity
```

El comando HOME es importante: Android/Google TV moderno puede bloquear el inicio
de Activities desde `BOOT_COMPLETED`. Como HOME, el sistema inicia el player al
arrancar. La instalación de futuras APK puede seguir mostrando confirmación del
sistema si el onn no está provisionado como Device Owner.

---

## 2. COLORLIGHT A40

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
4. Seleccionar `mediaview-player-v3.0.0.apk`
5. Esperar la instalacion

### 1.4 Instalar APK via ADB (Alternativa)
```bash
# Conectar (el firmware habilita ADB)
adb connect [IP_DEL_A40]:5555
adb devices

# Instalar
adb install mediaview-player-v3.0.0.apk

# Configurar como launcher predeterminado
adb shell cmd package set-home-activity com.mediaview.player/.MainActivity

# Iniciar
adb shell am start -n com.mediaview.player/.MainActivity
```

### 1.5 Vincular dispositivo
1. Abrir el player y anotar el código estable de seis caracteres.
2. En el panel, abrir **Devices > Link Device by Code**.
3. Seleccionar la pantalla; `screen_id` y URL se guardan en la identidad nativa.

### 1.6 Auto-inicio
Con el firmware personalizado de Colorlight:
- La app se configura como **launcher predeterminado**
- Se inicia automaticamente al encender el A40
- No requiere configuracion adicional

---

## 3. OTROS ANDROID TV / GOOGLE TV

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
adb install mediaview-player-v3.0.0.apk

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

## 4. FIRE TV / FIRE TV STICK

### 3.1 Habilitar Developer Mode
1. Settings > My Fire TV > About
2. Click Build Number 7 veces
3. Developer Options > ADB debugging ON
4. Apps from Unknown Sources > ON

### 3.2 Instalar
```bash
adb connect [IP]:5555
adb install mediaview-player-v3.0.0.apk
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
- Ver info del dispositivo
- Desvincular y volver a la pantalla de activación

### 5.2 Diagnósticos HUD
La variante diagnóstica muestra el HUD y permite alternarlo con **I**. La variante
de producción lo compila desactivado.

### 5.3 Recuperación de crashes
Si la app falla, se reinicia automaticamente sin intervencion humana.

### 5.4 Reconexión automática
Si se pierde la red, el player conserva la reproducción y reintenta con backoff
exponencial (5s, 10s, 20s… hasta 5 minutos), además de reaccionar al retorno de red.

### 5.5 Caché offline
El contenido se pre-descarga y almacena localmente. Si la red falla, el ultimo contenido sigue reproduciendose.

---

## 6. ACTUALIZACIONES REMOTAS

### 6.1 Actualizar APK
```bash
adb connect [IP]:5555
adb install -r mediaview-player-v3.x.x.apk
adb shell am start -n com.mediaview.player/.MainActivity
```

### 6.2 Actualizar Contenido
El contenido se actualiza cada 15 segundos y también al recuperar conectividad.

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

## 8. ARQUITECTURA v3

```
[PairingActivity nativa] -> /api/devices/register + /check
             |
             v
[Room: manifiesto último válido] <-> [Sync 15s + NetworkCallback]
             |
             v
[Caché atómica verificada SHA-256/tamaño]
             |
             v
[Media3 video | Coil imagen | WebView aislado HTML/widget]
             |
             v
[Watchdog + heartbeat + actualización APK verificada]
```

### Garantías operativas

- Nunca se sustituye la playlist válida por una descarga parcial o corrupta.
- La UI de estado permanece visible hasta recibir frame de video, imagen decodificada
  o commit visual de HTML.
- La pérdida de red conserva la última playlist descargada y sincroniza al reconectar.
- Los errores SSL se cancelan; no se aceptan certificados inválidos.
- El autoarranque en Android estándar requiere seleccionar MediAd View como HOME.
  Para cero intervención garantizada, el equipo debe aprovisionarse como dispositivo
  dedicado/Device Owner o usar firmware AOSP del fabricante.

## 9. Protocolo de liberación

1. Codemagic ejecuta pruebas JVM y genera `mediaview-player-diagnostic.apk`.
2. Validar en A40: pairing, imagen, video, widget HTML, offline/reconexión y reboot.
3. Registrar el resultado visible del HUD descrito en `ROOT_CAUSE_REPORT.md`.
4. Cambiar CI a `assembleRelease`; la variante release compila con
   `DIAGNOSTICS_ENABLED=false` y no muestra el HUD durante reproducción.

---

*MediAd View Player v3.0.0 - Optimizado para Colorlight A40*
*© MediAd View LLC*
