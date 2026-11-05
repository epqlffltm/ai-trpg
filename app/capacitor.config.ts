// app/capacitor.config.ts
// 앱 껍데기(Capacitor)의 설정(#429, docs/product/app-refresh.md). 화면은 web 의 빌드(dist)를 그대로 담는다.
//
// API 를 부를 출처는 APP_API_ORIGIN 으로 준다(예: https://play.example.com). 화면의 VITE_API_ORIGIN(scripts/build-web.mjs)과
// AppAuth 플러그인의 apiOrigin 이 같은 값을 쓴다. 비우면 플러그인이 서버를 부르지 못한다(로그인이 실패한다).
// appId 는 임시다(dev.aitrpg.app). 구글 플레이에 올리기 전에 우리 도메인으로 바꾼다. 한 번 올리면 바꾸지 못한다.

import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'dev.aitrpg.app',
  appName: '이매망량의 서재',
  webDir: '../web/apps/web/dist',
  android: {
    // 페이지의 출처는 https://localhost 다(프록시가 이 출처에만 CORS 를 연다, 루트 README)
  },
  plugins: {
    AppAuth: {
      apiOrigin: process.env.APP_API_ORIGIN ?? '',
    },
  },
};

export default config;
