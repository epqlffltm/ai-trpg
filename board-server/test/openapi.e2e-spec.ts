// board-server/test/openapi.e2e-spec.ts

/**
 * 앱을 통째로 만들어 API 목록(src/openapi/document.ts)을 뽑아 본다. 실제 PostgreSQL 에서 돈다.
 *
 * 목록이 문지기의 규칙과 같은지를 본다. 로그인 없이 부르는 API 와 운영자의 API 가 목록에 그렇게 적혀 있어야
 * 화면이 맞는 API 를 부른다. 칸의 모양은 보지 않는다. 테스트는 빌드의 플러그인을 거치지 않는다
 * (칸의 모양은 CI 의 api-docs 가 빌드한 코드에서 뽑아 docs/api/board.openapi.json 과 견준다).
 */

import { NestExpressApplication } from '@nestjs/platform-express';
import { OpenAPIObject, OperationObject } from '@nestjs/swagger';
import { buildDocument, operationsOf } from '../src/openapi/document.js';
import { createTestApp } from './app.js';

/** 주소 앞부분 */
const API = '/api/v1/board';

describe('API 목록', () => {
  let app: NestExpressApplication;
  let document: OpenAPIObject;

  beforeAll(async () => {
    app = await createTestApp();
    document = buildDocument(app);
  });

  afterAll(async () => {
    await app.close();
  });

  /** 주소와 방식으로 요청 하나를 찾는다. 없으면 테스트가 실패한다. */
  function operation(
    method: 'get' | 'post' | 'put',
    path: string,
  ): OperationObject {
    const found = document.paths[`${API}${path}`]?.[method];
    expect(found, `${method.toUpperCase()} ${path}`).toBeDefined();
    return found as OperationObject;
  }

  it.each([
    ['get', '/boards'],
    ['get', '/boards/{slug}/posts'],
    ['get', '/posts/{id}'],
    ['get', '/posts'],
    ['get', '/posts/{postId}/comments'],
  ] as const)(
    '로그인 없이 부르는 %s %s 는 그렇게 적혀 있다',
    (method, path) => {
      expect(operation(method, path).security).toEqual([{}]);
    },
  );

  it.each([
    ['get', '/me'],
    ['post', '/boards/{slug}/posts'],
    ['post', '/posts/{postId}/comments'],
    ['post', '/posts/{id}/reports'],
  ] as const)(
    '로그인이 필요한 %s %s 는 목록 전체의 기본(토큰)을 따른다',
    (method, path) => {
      expect(operation(method, path).security).toBeUndefined();
    },
  );

  it.each([
    ['put', '/posts/{id}/pin'],
    ['get', '/reports'],
    ['get', '/posts/{id}/reports'],
    ['put', '/comments/{id}/reports/outcome'],
  ] as const)(
    '운영자의 %s %s 는 운영자의 것이라고 적혀 있다',
    (method, path) => {
      expect(operation(method, path)['x-audience']).toBe('operator');
    },
  );

  it('신고하기는 운영자의 것이 아니다. 같은 주소의 신고 목록과 갈린다', () => {
    expect(operation('post', '/posts/{id}/reports')).not.toHaveProperty(
      'x-audience',
    );
  });

  it('API 주소 아래의 요청은 모두 오류의 모양을 돌려준다고 적혀 있다', () => {
    const missing = operationsOf(document)
      .filter(({ path }) => path.startsWith(`${API}/`))
      .filter(({ operation: found }) => found.responses.default === undefined)
      .map(({ path }) => path);

    expect(missing).toEqual([]);
  });
});
