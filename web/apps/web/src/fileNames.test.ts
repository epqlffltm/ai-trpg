// web/apps/web/src/fileNames.test.ts
// 한 폴더 안에 확장자를 떼면 대소문자만 다른(또는 같은) 모듈 파일이 둘 있으면 안 된다.
// 화면은 확장자 없이 가져온다(`from './RoomNotices'`). 리졸버는 .ts 를 .tsx 보다 먼저 찾고, Windows 의 파일 시스템은
// 대소문자를 가리지 않아 `RoomNotices.ts` 를 찾다가 `roomNotices.ts` 를 연다. 그 컴포넌트가 없어 화면이 깨진다.
// Linux(CI)에서는 드러나지 않아 이 검사로 막는다. 앱의 src 와 공통 구성요소(packages/ui/src)를 본다.
// 파일 시스템을 읽으므로 브라우저 흉내(jsdom)가 아니라 node 에서 돈다(아래의 @vitest-environment).
// @vitest-environment node

import { readdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const MODULE = /\.(ts|tsx|js|jsx|mts|mjs)$/;
const ROOTS = [fileURLToPath(new URL('.', import.meta.url)), fileURLToPath(new URL('../../../packages/ui/src', import.meta.url))];

/** 폴더 하나의 모듈 파일 가운데 확장자를 떼고 대소문자를 가리지 않으면 같은 것들. "폴더: 파일, 파일" */
function clashesIn(folder: string, names: string[]): string[] {
  const byKey = new Map<string, string[]>();
  for (const name of names.filter((one) => MODULE.test(one))) {
    const key = name.replace(MODULE, '').toLowerCase();
    byKey.set(key, [...(byKey.get(key) ?? []), name]);
  }
  return [...byKey.values()].filter((group) => group.length > 1).map((group) => `${folder}: ${group.sort().join(', ')}`);
}

/** 그 폴더와 아래 폴더들의 겹치는 이름 */
function clashesUnder(folder: string): string[] {
  const entries = readdirSync(folder, { withFileTypes: true });
  const here = clashesIn(
    folder,
    entries.filter((entry) => entry.isFile()).map((entry) => entry.name),
  );
  const below = entries.filter((entry) => entry.isDirectory() && entry.name !== 'node_modules').flatMap((entry) => clashesUnder(join(folder, entry.name)));
  return [...here, ...below];
}

describe('파일 이름', () => {
  it('확장자를 떼면 대소문자만 다른 모듈 파일이 한 폴더에 없다', () => {
    expect(ROOTS.flatMap(clashesUnder)).toEqual([]);
  });

  it('겹침은 대소문자와 확장자를 가리지 않고 모듈 파일만 본다', () => {
    expect(clashesIn('a', ['RoomNotices.tsx', 'roomNotices.ts', 'app.css', 'App.tsx', 'x.test.ts', 'x.ts'])).toEqual(['a: RoomNotices.tsx, roomNotices.ts']);
    expect(clashesIn('b', ['Same.ts', 'Same.tsx'])).toEqual(['b: Same.ts, Same.tsx']);
  });
});
