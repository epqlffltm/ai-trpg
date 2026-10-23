// web/apps/web/vite.config.ts
// 화면을 만드는 설정. 빌드한 것(dist)은 프록시의 이미지에 담긴다(web/Dockerfile).
//
// 개발 중에는 Vite 의 개발 서버가 /api/ 를 로컬 compose 의 프록시(127.0.0.1:8080)로 넘긴다.
// 서버마다 주소를 적지 않는다. 주소의 갈래와 요청 수 제한이 실제와 같아진다(docs/product/screens.md 의 "시작할 때 정한 것").
// refresh 쿠키를 쓰는 주소는 화면의 출처(Origin)를 본다. 개발 서버의 주소를 인증 서버의 허용 목록에 더한다(web/README.md).
//
// 빌드는 화면마다 조각을 나누고(src/routing/pages.ts), 늘 쓰는 라이브러리는 vendor 조각 하나로 묶는다.
// 라이브러리는 우리 코드보다 드물게 바뀐다. 따로 두면 화면만 고쳐 올렸을 때 vendor 의 이름(해시)이 그대로라 캐시가 남는다.
// 문서 보기에만 쓰는 react-markdown 같은 것은 넣지 않는다. 그 화면을 열 때 받는다.

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// vendor 로 묶을 라이브러리. 모든 화면이 쓰는 것만
const VENDOR = /[\\/]node_modules[\\/](react|react-dom|scheduler|react-router|@tanstack)[\\/]/;

// 로컬 compose 의 프록시. 루트 .env 의 PROXY_PORT 를 바꿨으면 같이 바꾼다
const LOCAL_PROXY = process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8080';

export default defineConfig({
  plugins: [react()],
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [{ name: 'vendor', test: VENDOR }],
        },
      },
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api/': { target: LOCAL_PROXY },
    },
  },
});
