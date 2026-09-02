plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.kapt")
}

android {
    namespace = "com.mediaview.player"
    compileSdk = 34

    buildFeatures {
        buildConfig = true
    }

    defaultConfig {
        applicationId = "com.mediaview.player"
        minSdk = 21
        targetSdk = 34
        versionCode = 16
        versionName = "3.1.0"

        // =============================================================
        // CONFIGURACION DE PRODUCCION
        // Servidor de MediAd View (backend FastAPI en Render).
        // =============================================================
        buildConfigField("String", "SERVER_URL", "\"https://mediadview.com\"")
    }

    buildTypes {
        release {
            // R8/minify DISABLED temporarily until the pairing screen is verified
            // to work in production. Re-enable once we know all classes survive shrinking.
            isMinifyEnabled = false
            buildConfigField("boolean", "DIAGNOSTICS_ENABLED", "false")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            // If a release keystore is provided via environment variables
            // (used by GitHub Actions), sign with it. Otherwise fall back
            // to the debug signing config so the APK is still installable.
            signingConfig = if (!System.getenv("MEDIAVIEW_KEYSTORE_PATH").isNullOrBlank()) {
                signingConfigs.getByName("release")
            } else {
                signingConfigs.getByName("debug")
            }
        }
        debug {
            isMinifyEnabled = false
            applicationIdSuffix = ".debug"
            buildConfigField("boolean", "DIAGNOSTICS_ENABLED", "true")
        }
        create("diagnostic") {
            initWith(getByName("release"))
            isDebuggable = true
            versionNameSuffix = "-diagnostic"
            buildConfigField("boolean", "DIAGNOSTICS_ENABLED", "true")
            matchingFallbacks += listOf("release")
        }
    }

    signingConfigs {
        create("release") {
            val ksPath = System.getenv("MEDIAVIEW_KEYSTORE_PATH")
            if (ksPath != null && file(ksPath).exists()) {
                storeFile = file(ksPath)
                storePassword = System.getenv("MEDIAVIEW_KEYSTORE_PASSWORD") ?: ""
                keyAlias = System.getenv("MEDIAVIEW_KEY_ALIAS") ?: "mediaview"
                keyPassword = System.getenv("MEDIAVIEW_KEY_PASSWORD") ?: ""
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8
        targetCompatibility = JavaVersion.VERSION_1_8
    }
    kotlinOptions {
        jvmTarget = "1.8"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("androidx.webkit:webkit:1.10.0")
    implementation("androidx.work:work-runtime-ktx:2.9.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
    implementation("androidx.room:room-runtime:2.6.1")
    implementation("androidx.room:room-ktx:2.6.1")
    kapt("androidx.room:room-compiler:2.6.1")
    implementation("androidx.media3:media3-exoplayer:1.3.1")
    implementation("androidx.media3:media3-ui:1.3.1")
    implementation("io.coil-kt:coil:2.6.0")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
