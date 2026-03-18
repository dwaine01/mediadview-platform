plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.mediaview.player"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.mediaview.player"
        minSdk = 21
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"

        // MediaView server URL - change this for production
        buildConfigField("String", "SERVER_URL", "\"https://your-server.com\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
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
}
