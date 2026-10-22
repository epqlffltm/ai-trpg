// web/apps/web/scripts/sync-legal.mjs
// 동의 항목의 문서(docs/legal/*.md)에서 사용자에게 보이는 본문만 판마다 화면에 넣는다(#450).
// 서버는 항목과 판 번호만 준다. 문서의 글은 화면이 갖는다(auth-server/accounts/consents.py).
//
//   npm run sync:legal         (web/ 에서)
//
// 원본의 모양: 제목(# 이용약관 (초안)), 작성자를 위한 안내, ---, 본문, ---, 검토할 것과 근거.
// 두 --- 사이의 본문과 제목(괄호를 뺀 것)만 담는다. 원본을 고치면 이것을 다시 돌려 함께 올린다. CI(web.yml)가 어긋나면 실패한다.
// 판을 올리면(consents.py 의 POLICIES) DOCUMENTS 에 새 판을 더한다. 옛 판의 파일은 지우지 않는다(그 판에 동의한 기록이 남는다).

import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const APP_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const LEGAL_DOCS = join(APP_ROOT, '..', '..', '..', 'docs', 'legal');
const OUT_DIR = join(APP_ROOT, 'src', 'legal', 'documents');

// 화면이 갖는 문서와 판. 이름은 <문서>-v<판>.md 다
const DOCUMENTS = [
  { name: 'terms', version: 1, source: 'terms.md' },
  { name: 'privacy', version: 1, source: 'privacy.md' },
];

const RULE = /^---\s*$/m;

/** 원본에서 제목과 두 --- 사이의 본문을 꺼낸다. 모양이 다르면 멈춘다(엉뚱한 글이 화면에 나가지 않게) */
export function userFacingBody(markdown, source) {
  const [head, body, ...rest] = markdown.split(RULE);
  if (body === undefined || rest.length === 0) {
    throw new Error(`${source}: 본문을 감싼 --- 두 줄을 찾지 못했다`);
  }
  const title = head.match(/^#\s+(.+?)\s*(\(.*\))?\s*$/m)?.[1];
  if (!title) throw new Error(`${source}: 맨 위의 제목(# ...)을 찾지 못했다`);
  return `# ${title}\n\n${body.trim()}\n`;
}

async function sync({ name, version, source }) {
  const markdown = await readFile(join(LEGAL_DOCS, source), 'utf8');
  const target = join(OUT_DIR, `${name}-v${version}.md`);
  await writeFile(target, userFacingBody(markdown, source));
  return target;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  await mkdir(OUT_DIR, { recursive: true });
  for (const document of DOCUMENTS) {
    console.log(`만들었다: ${await sync(document)}`);
  }
}
