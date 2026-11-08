// app/android/app/src/main/java/com/imaemangnyang/app/RefreshTokenStore.java
// refresh 토큰을 기기에 두는 곳(#429). 화면의 스크립트는 이 값을 보지 못한다(AppAuthPlugin 만 쓴다).
//
// Android Keystore 의 AES 키(기기 밖으로 꺼낼 수 없다)로 암호화해 SharedPreferences 에 둔다(AES-GCM).
// Jetpack Security 의 EncryptedSharedPreferences 는 쓰지 않는다. 더 손보지 않는 라이브러리라 의존을 늘리지 않는다.
// 풀지 못하면(키가 바뀌었거나 다른 기기에서 백업을 되살렸다) 토큰이 없는 것으로 보고 지운다. 사용자는 다시 로그인한다.

package com.imaemangnyang.app;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

final class RefreshTokenStore {

    private static final String KEYSTORE = "AndroidKeyStore";
    private static final String KEY_ALIAS = "ai-trpg-refresh-token";
    private static final String PREFERENCES = "app_auth";
    private static final String TOKEN_FIELD = "refresh_token";
    private static final String IV_FIELD = "refresh_token_iv";
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int TAG_BITS = 128;

    private final SharedPreferences preferences;

    RefreshTokenStore(Context context) {
        this.preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE);
    }

    /** 둔 토큰. 없거나 풀지 못하면 null 이다(풀지 못한 것은 지운다) */
    String read() {
        String sealed = preferences.getString(TOKEN_FIELD, null);
        String iv = preferences.getString(IV_FIELD, null);
        if (sealed == null || iv == null) return null;
        try {
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(TAG_BITS, Base64.decode(iv, Base64.NO_WRAP)));
            return new String(cipher.doFinal(Base64.decode(sealed, Base64.NO_WRAP)), StandardCharsets.UTF_8);
        } catch (GeneralSecurityException | IllegalArgumentException exception) {
            clear();
            return null;
        }
    }

    /** 토큰을 새것으로 바꿔 둔다. 암호화하지 못하면 옛것도 지운다(옛 토큰은 서버에서 이미 폐기됐다) */
    void write(String token) {
        try {
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(Cipher.ENCRYPT_MODE, key());
            byte[] sealed = cipher.doFinal(token.getBytes(StandardCharsets.UTF_8));
            preferences
                .edit()
                .putString(TOKEN_FIELD, Base64.encodeToString(sealed, Base64.NO_WRAP))
                .putString(IV_FIELD, Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP))
                .commit();
        } catch (GeneralSecurityException exception) {
            clear();
        }
    }

    void clear() {
        preferences.edit().remove(TOKEN_FIELD).remove(IV_FIELD).commit();
    }

    /** Keystore 의 키. 없으면 만든다 */
    private static SecretKey key() throws GeneralSecurityException {
        KeyStore keyStore = KeyStore.getInstance(KEYSTORE);
        try {
            keyStore.load(null);
        } catch (java.io.IOException exception) {
            throw new GeneralSecurityException(exception);
        }
        KeyStore.Entry entry = keyStore.getEntry(KEY_ALIAS, null);
        if (entry instanceof KeyStore.SecretKeyEntry) {
            return ((KeyStore.SecretKeyEntry) entry).getSecretKey();
        }
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE);
        generator.init(
            new KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        );
        return generator.generateKey();
    }
}
