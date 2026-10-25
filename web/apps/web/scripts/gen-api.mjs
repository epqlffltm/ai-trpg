// web/apps/web/scripts/gen-api.mjs
// 서버의 API 목록(docs/api/<서버>.openapi.json)에서 화면의 타입을 만든다(openapi-typescript).
// 손으로 쓴 타입을 두지 않는다. 서버의 API 가 바뀌면 이것을 다시 돌려 함께 올린다. CI(web.yml)가 어긋나면 실패한다.
//
//   npm run gen:api            (web/ 에서)
//
// 화면이 부르는 서버만 만든다. 새 서버를 부르기 시작하면 SERVERS 에 더한다.

import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import openapiTS, { astToString } from 'openapi-typescript';

const APP_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const API_DOCS = join(APP_ROOT, '..', '..', '..', 'docs', 'api');
const OUT_DIR = join(APP_ROOT, 'src', 'api', 'generated');
const SERVERS = ['auth', 'trpg', 'asset', 'chat', 'billing', 'notification', 'board'];

const HEADER = (server) =>
  `// web/apps/web/src/api/generated/${server}.ts\n` +
  `// docs/api/${server}.openapi.json 에서 만든 타입. 손으로 고치지 않는다(npm run gen:api).\n\n`;

async function generate(server) {
  const source = pathToFileURL(join(API_DOCS, `${server}.openapi.json`));
  const ast = await openapiTS(source);
  const target = join(OUT_DIR, `${server}.ts`);
  await writeFile(target, HEADER(server) + astToString(ast));
  return target;
}

await mkdir(OUT_DIR, { recursive: true });
for (const server of SERVERS) {
  console.log(`만들었다: ${await generate(server)}`);
}
