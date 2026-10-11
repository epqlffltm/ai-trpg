// board-server/src/migrations/migrations.spec.ts

/**
 * 마이그레이션 파일에 스키마 이름이 박혀 있지 않은지 본다. DB 에 연결하지 않고 파일의 글만 읽는다.
 *
 * 같은 마이그레이션을 개발용(board)과 테스트용(board_test) 스키마에 함께 쓴다. 어느 스키마인지는 연결이 정한다.
 * TypeORM 이 자동으로 만든 파일은 색인을 지우는 줄에 만들 때의 스키마 이름을 붙인다(DROP INDEX "board"."IDX_...").
 * 그대로 두면 테스트용 스키마에서 되돌릴 때 개발용 스키마의 색인을 지우려 든다.
 * 이 테스트가 실패하면 그 줄에서 "board". 을 지운다.
 */

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

/** 마이그레이션 파일에 나오면 안 되는 스키마 이름들 */
const SCHEMAS = ['board', 'board_test'];

/** 글에서 스키마 이름을 붙여 부른 곳을 찾는다. "board"."posts" 나 board.posts 같은 모양이다. */
function findSchemaNames(text: string): string[] {
  return SCHEMAS.flatMap(
    (schema) =>
      text.match(new RegExp(`"${schema}"\\s*\\.|\\b${schema}\\.\\w`, 'g')) ??
      [],
  );
}

/** 이 폴더의 마이그레이션 파일들. 테스트 파일은 뺀다. */
function migrationFiles(): string[] {
  return readdirSync(import.meta.dirname)
    .filter((name) => name.endsWith('.ts') && !name.endsWith('.spec.ts'))
    .map((name) => join(import.meta.dirname, name));
}

describe('findSchemaNames', () => {
  it('스키마 이름을 붙여 부른 곳을 찾는다', () => {
    expect(findSchemaNames('DROP INDEX "board"."IDX_1"')).toEqual(['"board".']);
    expect(findSchemaNames('DROP TABLE board_test.posts')).toHaveLength(1);
  });

  it('이름이 붙지 않은 SQL 은 지나친다', () => {
    expect(findSchemaNames('CREATE TABLE "posts" ("id" uuid)')).toEqual([]);
    expect(findSchemaNames('CREATE TABLE "boards" ("id" uuid)')).toEqual([]);
    expect(findSchemaNames('DROP INDEX "IDX_board_posts"')).toEqual([]);
  });
});

describe('마이그레이션 파일', () => {
  it.each(migrationFiles().map((file) => [file]))(
    '%s 에 스키마 이름이 박혀 있지 않다',
    (file) => {
      expect(findSchemaNames(readFileSync(file, 'utf8'))).toEqual([]);
    },
  );

  it('이 폴더를 읽을 수 있다', () => {
    expect(Array.isArray(migrationFiles())).toBe(true);
  });
});
