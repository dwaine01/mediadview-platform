# MediAd View Player - ProGuard Rules
# Keep WebView JavaScript interface
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}

# Keep WorkManager
-keep class * extends androidx.work.Worker
-keep class * extends androidx.work.ListenableWorker {
    public <init>(android.content.Context, androidx.work.WorkerParameters);
}

# Keep BroadcastReceivers
-keep class com.mediaview.player.BootReceiver
-keep class com.mediaview.player.NetworkBootReceiver
-keep class com.mediaview.player.BootWorker

# Keep Application class
-keep class com.mediaview.player.PlayerApp

# Keep BuildConfig
-keep class com.mediaview.player.BuildConfig { *; }

# General Android
-keepattributes *Annotation*
-keepattributes SourceFile,LineNumberTable
-keep public class * extends android.app.Activity
-keep public class * extends android.app.Service
-keep public class * extends android.content.BroadcastReceiver
