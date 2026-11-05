# 앱 껍데기

화면(`web/`)을 Capacitor 로 감싼 Android 앱(#429). 화면의 빌드를 그대로 담고, 이 앱에만 있는 것은 refresh 토큰을 쥐는 네이티브 플러그인(`AppAuth`) 하나다.
왜 이렇게 했는지는 [앱에서의 로그인 유지](../docs/product/app-refresh.md)에 있다.

- 기준일: 2026-11-05
- 시험 단계다. CI 가 없고, 스토어에 올리지 않았다. 빌드와 실행은 PC 의 Android Studio 에서 본다
- 패키지 이름(`appId`)은 임시다(`dev.aitrpg.app`). 구글 플레이에 올리기 전에 우리 도메인으로 바꾼다. 한 번 올리면 바꾸지 못한다
- Capacitor 8.5.3, Android 의 최소 판은 7.0(API 24), 대상은 API 36 이다(`android/variables.gradle`)

## 실행

필요한 것: Node 22 이상, Android Studio(그 안의 Android SDK 와 JDK 21).

PowerShell 에서(출처는 우리 사이트의 주소로 바꾼다):

```powershell
cd D:\Programming\ai-trpg-board\web; npm ci; npm run gen:api; cd D:\Programming\ai-trpg-board\app; npm ci; $env:APP_API_ORIGIN="https://play.example.com"; npm run sync; npm run open
```

- 화면의 의존성과 API 타입(`web` 의 `npm ci`, `npm run gen:api`)이 먼저 있어야 한다
- `npm run sync` 는 화면을 앱의 길로 빌드하고(`VITE_AUTH_TRANSPORT=app`, `VITE_API_ORIGIN`, `scripts/build-web.mjs`) 그 빌드와 플러그인의 출처를 Android 프로젝트에 넣는다. 화면을 고칠 때마다 다시 한다
- `npm run open` 은 Android Studio 로 `android/` 를 연다. 거기서 에뮬레이터나 기기로 실행한다
- 처음 받은 저장소에는 `android/capacitor-cordova-android-plugins` 가 없다. `npm run sync` 가 만든다. 그 전에 Android Studio 로 열면 Gradle 이 실패한다

### PC 의 compose 에 붙이기 (디버그 빌드)

에뮬레이터에서 PC 의 프록시(8080)에 붙어 로그인까지 시험한다. 디버그 빌드만 된다.

1. PC 에서 compose 를 띄운다(루트 README 의 "실행"). 브라우저로 `http://localhost:8080` 이 열리는지 본다
2. 앱을 PC 의 compose 로 빌드해 넣는다
   ```powershell
   cd D:\Programming\ai-trpg-board\app; $env:APP_API_ORIGIN="http://localhost:8080"; npm run sync
   ```
3. 에뮬레이터를 켠 뒤, 에뮬레이터의 `localhost:8080` 을 PC 의 8080 으로 잇는다. 에뮬레이터를 다시 켤 때마다 한다(SDK 를 다른 곳에 깔았으면 그 경로의 `platform-tools`)
   ```powershell
   & "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" reverse tcp:8080 tcp:8080
   ```
4. Android Studio 에서 디버그로 실행한다(초록 ▶)

왜 이렇게 하나

- 에뮬레이터 안의 `localhost` 는 에뮬레이터 자신이다. `adb reverse` 가 그 8080 을 PC 의 8080 으로 넘긴다. `10.0.2.2`(에뮬레이터에서 본 PC)를 쓰지 않는 것은 인증 서버의 `ALLOWED_HOSTS`(localhost, 127.0.0.1)를 고치지 않으려는 것이다
- Android 는 평문 HTTP 를 막는다. 디버그 빌드만 `localhost` 에 연다(`android/app/src/debug/res/xml/network_security_config.xml`). 릴리스 빌드는 `android:usesCleartextTraffic="false"` 로 막는다
- 페이지는 `https://localhost` 라 HTTP 의 API 를 부르면 WebView 가 섞인 내용으로 막는다. `APP_API_ORIGIN` 이 `http://` 일 때만 `allowMixedContent` 를 켠다(`capacitor.config.ts`)
- Capacitor 가 가로채는 것은 `https://localhost`(포트 없음)뿐이라 `http://localhost:8080` 의 요청은 그대로 나간다(Capacitor 의 `WebViewLocalServer` 가 scheme 과 포트까지 맞춘다)
- HTTP 의 출처는 `http://localhost:포트` 만 받는다. 그 밖의 `http://` 는 `npm run build:web` 이 멈춘다
- 릴리스로 빌드하기 전에는 HTTPS 의 출처로 `npm run sync` 를 다시 한다. 그러지 않으면 섞인 내용이 켜진 채 들어가고, 평문이 막혀 API 에 닿지 못한다

## 플러그인(AppAuth)

`android/app/src/main/java/dev/aitrpg/app/` 에 있다.

| 파일 | 하는 일 |
| --- | --- |
| `AppAuthPlugin.java` | 화면이 부르는 메서드 넷(로그인 2단계, 갱신, 로그아웃, 비밀번호 변경). 답은 `{ status, body }` 이고 refresh 토큰은 빼고 넘긴다. 한 줄의 작업자로 차례로 해서 갱신이 겹치지 않는다 |
| `AuthHttp.java` | 인증 서버의 앱의 길(`/api/v1/auth/app/...`)을 네이티브의 HTTP 로 부른다. `Origin` 이 붙지 않는다(붙으면 인증 서버가 403 으로 거절한다) |
| `RefreshTokenStore.java` | refresh 토큰을 Android Keystore 의 AES 키로 암호화해 SharedPreferences 에 둔다. 풀지 못하면 지우고 다시 로그인하게 한다 |
| `MainActivity.java` | 플러그인을 등록한다 |

화면 쪽의 약속은 `web/apps/web/src/api/appAuth.ts` 의 머리에 있다. 둘이 어긋나면 그쪽이 맞다.

- 백업은 끈다(`android:allowBackup="false"`). 백업한 암호문은 다른 기기에서 풀리지 않는다
- 그 밖의 API 는 화면이 access 토큰을 `Authorization` 에 실어 부른다. 프록시가 앱의 출처(`https://localhost`)에 CORS 를 연다

## 확인한 것과 못 한 것

- 샌드박스에서 `npm run sync` 로 화면을 앱의 길로 빌드해 Android 프로젝트에 넣는 것까지 했다. 빌드한 화면에 출처가 들어가고, 플러그인의 설정(`apiOrigin`)이 채워진다. `APP_API_ORIGIN` 이 비거나 localhost 가 아닌 `http://` 면 멈춘다. `http://localhost:8080` 이면 `allowMixedContent` 가 켜지고 HTTPS 면 꺼진다
- 샌드박스에 Android SDK 와 Maven 저장소가 없어 Gradle 빌드를 하지 못했다. 플러그인의 자바는 쓰는 API 의 모양만 흉내 낸 것으로 컴파일해 문법과 타입을 봤다(Capacitor 의 실제 소스에서 메서드의 모양을 확인했다)
- 처음 할 일: Android Studio 에서 빌드, 에뮬레이터에서 로그인 → 앱을 닫았다 열기(갱신) → 로그아웃 → 다시 열면 로그인 화면인지
- `@capacitor/cli` 가 끌어오는 `xcode`(iOS 용)의 `uuid` 에 npm audit 의 moderate 가 셋 있다. 빌드할 때만 쓰는 도구이고 앱에는 들어가지 않는다
