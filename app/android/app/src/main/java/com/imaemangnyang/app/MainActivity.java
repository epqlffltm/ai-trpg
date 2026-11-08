// app/android/app/src/main/java/com/imaemangnyang/app/MainActivity.java
// 앱의 첫 화면. Capacitor 의 BridgeActivity 가 web 의 빌드를 WebView 에 띄운다.
// 이 앱에만 있는 플러그인(AppAuth)은 super.onCreate 앞에서 등록한다. 그 뒤에 등록하면 화면이 찾지 못한다.

package com.imaemangnyang.app;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        registerPlugin(AppAuthPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
