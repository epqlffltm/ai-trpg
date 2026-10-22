// web/apps/web/vite.config.ts
// 화면을 만드는 설정. 빌드한 것(dist)은 프록시의 이미지에 담긴다(web/Dockerfile).
//
// 개발 중에는 Vite 의 개발 서버가 /api/ 를 로컬 compose 의 프록시(127.0.0.1:8080)로 넘긴다.
// 서버마다 주소를 적지 않는다. 주소의 갈래와 요청 수 제한이 실제와 같아진다(docs/product/screens.md 의 "시작할 때 정한 것").
// refresh 쿠키를 쓰는 주소는 화면의 출처(Origin)를 본다. 개발 서버의 주소를 인증 서버의 허용 목록에 더한다(web/README.md).

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// 로컬 compose 의 프록시. 루트 .env 의 PROXY_PORT 를 바꿨으면 같이 바꾼다
const LOCAL_PROXY = process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8080';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api/': { target: LOCAL_PROXY },
    },
  },
});
