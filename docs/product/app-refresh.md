# 앱(WebView)에서의 로그인 유지

앱은 웹을 Capacitor 로 감싸서 낸다([화면 명세](screens.md)의 "앱 껍데기에서 확인할 것" 1). 앱의 WebView 에서 리프레시 쿠키로 갱신이 되는지, 안 되면 어느 길로 고칠지를 적는다. 이슈 #429.

- 기준일: 2026-11-06
- 2026-11-05 에 C(앱만 본문의 토큰)를 골랐다. 인증 서버의 길([인증 서버](../../auth-server/README.md)의 "앱의 토큰")과 앱 껍데기([앱](../../app/README.md))를 만들었다.
- 2026-11-06 에 Android 에뮬레이터에서 로그인, 갱신, 로그아웃을 봤다(아래 "기기에서 확인한 것").

## 지금의 모양

- 인증 서버는 리프레시 토큰(14일)을 httpOnly 쿠키로 준다. `SameSite=Strict`, `Secure`, `Path=/api/v1/auth` 다(`auth-server/accounts/cookies.py`). access 토큰은 15분이다.
- refresh 와 logout 은 쿠키에 더해 `Origin` 을 허용 목록(`REFRESH_COOKIE_ALLOWED_ORIGINS`)과 그대로 비교한다(`auth-server/accounts/origin_check.py`).
- 웹은 모든 서버를 같은 출처의 상대 주소(`/api/v1/<서버>/`)로 부르고 `credentials: 'same-origin'` 을 쓴다(`web/apps/web/src/api/http.ts`). 실시간은 같은 출처의 `EventSource` 다.
- 어느 서버에도 CORS 가 없다. 화면과 API 가 프록시 뒤의 한 출처라 필요가 없었다.

## 시험 (2026-11-05, Chromium)

Android 기기가 없어 데스크톱 Chromium(Playwright, headless)으로 쿠키의 규칙만 먼저 봤다. Android WebView 도 Chromium 이지만, 기기에서 다시 봐야 한다(아래 "확인 못 한 것").

- 가짜 API(`https://example.test`): 로그인이 위와 같은 쿠키(`HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth`)를 주고, refresh 는 받은 쿠키를 돌려준다. 허용한 출처에는 CORS(`Access-Control-Allow-Origin` 에 그 출처, `Allow-Credentials: true`)를 준다.
- 페이지를 세 출처에서 열고 `fetch(..., { credentials: 'include' })` 로 로그인 → refresh 를 불렀다. 이름은 `--host-resolver-rules` 로 모두 이 PC 에 묶고, 자체 서명 인증서를 썼다.

| 페이지의 출처 | API 와의 관계 | refresh 에 쿠키가 실렸나 |
| --- | --- | --- |
| `https://example.test` | 같은 출처(지금의 웹) | 실렸다 |
| `https://app.example.test` | 같은 사이트, 다른 출처(CORS 허용) | 실렸다 |
| `https://other.test` | 다른 사이트(CORS 허용) | 실리지 않았다. 오류도 없이 쿠키만 빠졌다 |

뜻하는 것:

- Capacitor 의 기본 출처는 Android 가 `https://localhost`, iOS 가 `capacitor://localhost` 다. 둘 다 우리 도메인과 **다른 사이트**라, CORS 를 열어도 `SameSite=Strict` 쿠키가 실리지 않는다. 앱은 15분 뒤에 조용히 로그아웃된다.
- 기본 출처 그대로면 쿠키 전에 CORS 가 없어 API 를 아예 부르지 못한다.
- 쿠키를 `SameSite=None` 으로 풀면 다른 사이트에서도 실리지만, 웹에서도 다른 사이트가 쿠키를 싣게 된다(지금은 출처 검사만 남는다). 그리고 Android WebView 는 다른 사이트의 쿠키(서드 파티 쿠키)를 기본으로 받지 않는다. 고르지 않는다.

## 길 셋

### A. 앱이 사이트를 그대로 연다

Capacitor 의 `server.url` 을 우리 사이트로 둔다. WebView 가 웹과 같은 출처에서 돈다.

- 서버와 웹을 고칠 것이 없다. 쿠키, 출처 검사, 상대 주소, `EventSource` 가 웹과 같다.
- 웹을 배포하면 앱도 바로 바뀐다. 앱의 판을 올릴 일이 적다.
- Capacitor 문서는 `server.url` 을 라이브 리로드용이라 하고 운영에 권하지 않는다. 플러그인(푸시, 결제)이 원격 출처에서도 도는지 확인해야 한다.
- 망이 없으면 아무것도 뜨지 않는다. 게임이 원래 온라인이라 잃는 것은 첫 화면(오프라인 안내)뿐이다.
- 웹을 그대로 감싼 앱은 심사에서 걸릴 수 있다(화면 명세의 "앱 껍데기에서 확인할 것" 3). A 는 그 모양에 가장 가깝다.

### B. 앱의 파일을 우리 도메인의 하위 도메인 출처로 띄운다

화면 파일은 앱 안에 두고, Capacitor 의 `server.hostname` 을 `app.<도메인>` 으로 둔다(Android 의 `androidScheme` 은 `https`). 위 시험의 두 번째 줄이다.

- 쿠키는 그대로 쓴다(`SameSite=Strict` 가 같은 사이트라 실린다).
- 고칠 것
  - 프록시: 앱의 출처 하나에만 CORS 를 준다(`Allow-Credentials`, 미리 묻는 요청 OPTIONS 포함). 서버마다가 아니라 프록시 한 곳에서 한다.
  - 인증: `REFRESH_COOKIE_ALLOWED_ORIGINS` 에 앱의 출처를 더한다.
  - 웹: API 의 주소를 바꿀 수 있게 한다(앱에서는 `https://<도메인>/api/v1/...` 의 절대 주소). `credentials: 'include'`, `EventSource` 의 `withCredentials`. 그림 주소(`/_images/...`)도 절대 주소로.
- `app.<도메인>` 은 Capacitor 가 가로채는 이름이다. 실제 DNS 에 같은 이름의 사이트를 두지 않는다.
- iOS 는 `https` 를 쓸 수 없어(`capacitor://app.<도메인>`) 같은 사이트로 치지 않을 수 있다. iOS 를 낼 때 따로 본다.

### C. 앱만 리프레시 토큰을 본문으로 받는다

앱은 로그인과 refresh 의 응답 본문으로 리프레시 토큰을 받아 기기의 안전한 저장소(Android Keystore 를 쓰는 플러그인)에 두고, refresh 에 본문으로 보낸다.

- 쿠키와 출처에 매이지 않는다. iOS 도 같다.
- 인증 서버에 앱용 길이 따로 생긴다. 본문으로 토큰을 주는 길을 웹이 부르지 못하게 막아야 한다(앱을 가리는 방법도 정해야 한다).
- 탈취 면이 달라진다. 지금은 스크립트가 리프레시 토큰을 읽지 못한다(httpOnly). C 에서는 네이티브 저장소에 있고, WebView 의 스크립트가 플러그인을 거쳐 꺼낼 수 있으면 XSS 가 14일짜리 토큰을 가져간다. 플러그인이 스크립트에 토큰을 넘기지 않게(네이티브 쪽에서 refresh 를 부르게) 짜야 같은 수준이 된다.
- 실시간과 그 밖의 API 는 B 와 같이 절대 주소와 CORS 가 필요하다(쿠키 대신 access 토큰을 머리말로 싣는다면 CORS 의 `Allow-Credentials` 는 필요 없다).

### 비교

| | A. 사이트를 연다 | B. 하위 도메인 출처 | C. 본문의 토큰 |
| --- | --- | --- | --- |
| 서버를 고칠 것 | 없다 | 프록시의 CORS, 인증의 허용 출처 | 인증의 앱용 길, 프록시의 CORS |
| 웹을 고칠 것 | 없다 | API 주소, credentials, EventSource | B 에 더해 토큰을 넘기는 플러그인 |
| 쿠키의 보안 | 웹과 같다 | 웹과 같다 | 네이티브 저장소. 짜는 법에 따라 달라진다 |
| iOS | 같다 | 따로 봐야 한다 | 같다 |
| 앱 갱신 | 웹 배포로 끝난다 | 앱의 판을 올린다 | 앱의 판을 올린다 |
| 걸리는 것 | Capacitor 가 운영에 권하지 않음, 심사 | iOS, 고칠 곳이 여러 군데 | 보안 설계, 인증의 길이 둘 |

## 확인 못 한 것

C 를 골라 A, B 의 것은 더 보지 않는다. 고르기 전에 남긴 것이다.

- 실제 Android WebView. 위 시험은 데스크톱 Chromium 이다. WebView 의 서드 파티 쿠키 설정은 B 에 걸리지 않을 것으로 보지만(같은 사이트) 기기에서 보지 않았다.
- Capacitor 가 `server.hostname` 의 이름을 가로챌 때 그 출처의 쿠키와 CORS 가 브라우저와 같게 도는지.
- A 에서 Capacitor 플러그인이 원격 출처의 페이지에서 도는지.
- 앱을 닫았다 열었을 때 WebView 가 쿠키를 남기는지(Android 의 CookieManager 는 디스크에 쓰지만, 앱이 바로 죽으면 마지막 쿠키가 빠질 수 있다).

## 고른 것 (2026-11-05)

C 다. 네이티브 앱이 흔히 하는 방식이고(OAuth 의 네이티브 앱 모범 사례, RFC 8252), Android 와 iOS 가 같다.

- 인증 서버: `/api/v1/auth/app/` 아래의 길 넷(로그인 2단계, 갱신, 로그아웃, 비밀번호 변경). 쿠키를 쓰지 않는다
- 브라우저의 요청(`Origin`, `Sec-Fetch-Site`)은 거절한다. 웹 페이지의 XSS 가 이 길로 토큰을 받아 가지 못한다
- 앱에 준 토큰과 웹에 준 토큰은 서로의 길에서 통하지 않는다. 어디에 줬는지 적어 둔다(관리자 화면의 "토큰을 준 곳")
- 우리 앱인지(기기 증명, Play Integrity 등)는 가리지 않는다. 나중에 본다

앱 껍데기를 만들 때 할 것

- refresh 토큰은 네이티브 플러그인만 쥔다. 로그인 2단계와 갱신과 로그아웃을 네이티브 쪽이 부르고, 화면의 스크립트에는 access 토큰만 넘긴다. 스크립트가 refresh 토큰을 꺼낼 수 있으면 앱 안의 XSS 가 14일짜리 토큰을 가져간다
- 화면 쪽은 준비됐다. `VITE_AUTH_TRANSPORT=app` 으로 빌드하면 로그인 2단계, 갱신, 로그아웃, 비밀번호 변경이 플러그인(`AppAuth`)을 부른다. 플러그인이 지킬 약속(메서드, 답의 모양, refresh 토큰을 빼고 넘기기, 망이 없을 때 reject)은 `web/apps/web/src/api/appAuth.ts` 의 머리에 있다. 남은 것은 플러그인 자신(Android 의 안전한 저장소와 네이티브의 HTTP)이다
- 플러그인은 `Origin` 을 붙이지 않는 네이티브의 HTTP 로 부른다(붙으면 `403`)
- 그 밖의 API 는 access 토큰을 `Authorization` 에 싣는다. 프록시가 앱의 출처(`https://localhost`, `capacitor://localhost`)에만 CORS 를 연다(루트 README 의 "프록시는 앱의 출처에만 CORS 를 연다"). `Allow-Credentials` 는 없다. Capacitor 의 출처를 바꾸면(`server.hostname` 등) 프록시의 목록도 고친다
- 앱으로 빌드할 때는 API 의 출처를 적는다(`VITE_API_ORIGIN`, web README). 비우면 웹처럼 같은 출처의 상대 주소다

## 기기에서 확인한 것 (2026-11-06)

에뮬레이터(Android Studio)의 디버그 빌드를 PC 의 compose 에 붙였다(`APP_API_ORIGIN=http://localhost:8080`, `adb reverse`). 방법은 [앱](../../app/README.md)의 "PC 의 compose 에 붙이기"다.
인증 서버의 로그(`route`)와 기기의 저장 파일(`run-as` 로 읽은 `shared_prefs/app_auth.xml`)로 봤다.

| 한 것 | 서버 | 기기 |
| --- | --- | --- |
| 로그인(2단계) | `/api/v1/auth/app/login/verify` 200 | refresh 토큰의 암호문과 IV 가 남는다 |
| 앱을 강제로 끄고(`am force-stop`) 다시 열기 | `/api/v1/auth/app/refresh` 200 | 로그인이 이어진다 |
| 로그아웃 | `/api/v1/auth/app/logout` 204 | 저장 파일이 빈다(`<map />`) |

- 로그인의 1단계(비밀번호)는 웹과 같은 `/api/v1/auth/login` 이다. 토큰을 주지 않아 앱의 길을 따로 두지 않았다
- 화면은 access 토큰을 메모리에만 둔다. 강제로 끈 뒤에 로그인이 이어진 것은 플러그인이 기기의 refresh 토큰으로 갱신했기 때문이다
- 보지 않은 것: 실기기, 릴리스 빌드(HTTPS 의 출처), 비밀번호 변경(`/api/v1/auth/app/password/change`), refresh 토큰이 만료된 뒤(14일), iOS

## 정하지 않은 것

- 기기 증명을 언제 붙일지.
- iOS 를 낼지.

## 알아 둘 것

- 어느 길이든 갱신은 한 번에 하나만 보낸다(#30).
- 웹을 고치는 B, C 에서도 웹 자신은 지금처럼 같은 출처의 상대 주소를 쓴다. 앱일 때만 절대 주소로 바꾼다.
