plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Assinatura: com os segredos MORFO_KEYSTORE* (GitHub Actions) o APK sai assinado
// com uma chave fixa, e as atualizações instalam por cima. Sem eles, usa a chave
// de depuração (cada build pode exigir desinstalar a versão anterior).
val keystore: String? = System.getenv("MORFO_KEYSTORE")

android {
    namespace = "io.github.charlesmmorais.morfo"
    compileSdk = 35

    defaultConfig {
        applicationId = "io.github.charlesmmorais.morfo"
        minSdk = 31
        targetSdk = 35
        versionCode = (System.getenv("MORFO_VERSION_CODE") ?: "1").toInt()
        versionName = System.getenv("MORFO_VERSION_NAME") ?: "0.1.0"
    }

    signingConfigs {
        if (keystore != null) {
            create("morfo") {
                storeFile = file(keystore)
                storePassword = System.getenv("MORFO_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("MORFO_KEY_ALIAS")
                keyPassword = System.getenv("MORFO_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = if (keystore != null) signingConfigs.getByName("morfo") else signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}
