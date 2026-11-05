// app/scripts/build-web.mjs
// 앱에 담을 화면을 빌드한다. 앱의 길(VITE_AUTH_TRANSPORT=app)과 API 의 출처(VITE_API_ORIGIN)를 넣는다.
// Windows 의 PowerShell 에서도 돌게 환경 변수를 이 스크립트가 넘긴다(npm 의 스크립트에 VAR=값 을 쓰지 않는다).
//
//   사용: APP_API_ORIGIN 을 정하고 npm run build:web (예: PowerShell 에서 $env:APP_API_ORIGIN="https://play.example.com")

import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

// HTTPS 의 출처이거나, PC 의 compose 에 붙이는 http://localhost:포트(디버그 빌드만 평문을 연다)
const origin = process.env.APP_API_ORIGIN ?? '';
const https = /^https:\/\/[A-Za-z0-9.-]+(?::\d{1,5})?$/;
const localHttp = /^http:\/\/localhost(?::\d{1,5})?$/;
if (!https.test(origin) && !localHttp.test(origin)) {
  console.error(
    'APP_API_ORIGIN 에 우리 사이트의 출처(예: https://play.example.com)나 PC 의 compose(http://localhost:8080)를 적는다. 지금 값:',
    JSON.stringify(origin),
  );
  process.exit(1);
}

const webDir = fileURLToPath(new URL('../../web', import.meta.url));
const result = spawnSync('npm', ['run', 'build'], {
  cwd: webDir,
  stdio: 'inherit',
  shell: process.platform === 'win32',
  env: { ...process.env, VITE_AUTH_TRANSPORT: 'app', VITE_API_ORIGIN: origin },
});
process.exit(result.status ?? 1);
