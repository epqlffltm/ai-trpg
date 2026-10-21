// board-server/src/openapi/document.spec.ts

/**
 * API 목록을 만드는 것(document.ts)과 목록에 적는 표시(auth/public.decorator.ts, audience.ts)를 검증한다.
 *
 * 테스트는 빌드의 플러그인을 거치지 않는다. 그래서 칸의 모양은 보지 않고 이 서버가 더한 규칙만 본다.
 * 칸의 모양까지 맞는지는 CI 의 api-docs 가 빌드한 코드에서 뽑아 docs/api/board.openapi.json 과 견준다.
 */

import { Controller, Get, INestApplication, Put } from '@nestjs/common';
import { OpenAPIObject } from '@nestjs/swagger';
import { Test } from '@nestjs/testing';
import { API_PREFIX } from '../app.setup.js';
import { Public } from '../auth/public.decorator.js';
import { ForOperators } from './audience.js';
import {
  BEARER_SCHEME,
  buildDocument,
  documentConfig,
  operationsOf,
  optionalWhenDefaulted,
  withErrorResponses,
} from './document.js';

/** 작은 목록. 기본값이 있는 쿼리와 없는 쿼리, 기본값이 있는 칸과 없는 칸, API 밖의 주소가 있다. */
function smallDocument(): OpenAPIObject {
  return {
    openapi: '3.0.0',
    info: { title: '가짜', version: '0' },
    paths: {
      '/api/v1/board/posts': {
        get: {
          parameters: [
            {
              name: 'page',
              in: 'query',
              required: true,
              schema: { type: 'number', default: 1 },
            },
            {
              name: 'q',
              in: 'query',
              required: true,
              schema: { type: 'string' },
            },
          ],
          responses: { '200': { description: '' } },
        },
        parameters: [],
      },
      '/health': { get: { responses: { '200': { description: '' } } } },
    },
    components: {
      schemas: {
        PinPostDto: {
          type: 'object',
          properties: { days: { type: 'number', default: 7 } },
          required: ['days'],
        },
        CreatePostDto: {
          type: 'object',
          properties: {
            title: { type: 'string' },
            board: { type: 'string', default: 'free' },
          },
          required: ['title', 'board'],
        },
      },
    },
  };
}

describe('operationsOf', () => {
  it('요청 방식만 꺼낸다. 주소 칸의 parameters 는 요청 방식이 아니다', () => {
    const found = operationsOf(smallDocument()).map(({ path }) => path);

    expect(found).toEqual(['/api/v1/board/posts', '/health']);
  });
});

describe('optionalWhenDefaulted', () => {
  it('기본값이 있는 쿼리는 적지 않아도 된다. 기본값이 없는 것은 그대로다', () => {
    const fixed = optionalWhenDefaulted(smallDocument());

    const parameters = fixed.paths['/api/v1/board/posts'].get?.parameters;
    expect(parameters).toMatchObject([
      { name: 'page', required: false },
      { name: 'q', required: true },
    ]);
  });

  it('기본값이 있는 칸을 반드시 적을 칸에서 뺀다', () => {
    const schemas = optionalWhenDefaulted(smallDocument()).components?.schemas;

    expect(schemas?.CreatePostDto).toMatchObject({ required: ['title'] });
  });

  it('반드시 적을 칸이 남지 않으면 required 를 지운다. OpenAPI 3.0 은 빈 목록을 받지 않는다', () => {
    const schemas = optionalWhenDefaulted(smallDocument()).components?.schemas;

    expect(schemas?.PinPostDto).not.toHaveProperty('required');
  });

  it('받은 목록은 고치지 않는다', () => {
    const original = smallDocument();

    optionalWhenDefaulted(original);

    expect(original).toEqual(smallDocument());
  });
});

describe('withErrorResponses', () => {
  it('API 주소 아래의 요청에 오류의 모양(ErrorBody)을 더한다', () => {
    const fixed = withErrorResponses(smallDocument());

    expect(
      fixed.paths['/api/v1/board/posts'].get?.responses.default,
    ).toMatchObject({
      content: {
        'application/json': {
          schema: { $ref: '#/components/schemas/ErrorBody' },
        },
      },
    });
  });

  it('상태 확인(/health)에는 더하지 않는다. API 밖이고 오류의 모양을 쓰지 않는다', () => {
    const fixed = withErrorResponses(smallDocument());

    expect(fixed.paths['/health'].get?.responses).not.toHaveProperty('default');
  });
});

describe('documentConfig', () => {
  it('기본으로 bearer 토큰이 필요하다고 적는다', () => {
    const config = documentConfig();

    expect(config.security).toEqual([{ [BEARER_SCHEME]: [] }]);
    expect(config.components?.securitySchemes?.[BEARER_SCHEME]).toMatchObject({
      type: 'http',
      scheme: 'bearer',
    });
  });
});

@Controller('things')
class ThingsController {
  @Public()
  @Get()
  list(): string[] {
    return [];
  }

  @Get('mine')
  mine(): string[] {
    return [];
  }
}

@ForOperators()
@Controller('things/:id/lock')
class LocksController {
  @Put()
  lock(): void {}
}

describe('buildDocument', () => {
  let app: INestApplication;
  let document: OpenAPIObject;

  beforeAll(async () => {
    const moduleRef = await Test.createTestingModule({
      controllers: [ThingsController, LocksController],
    }).compile();
    app = moduleRef.createNestApplication({ logger: false });
    app.setGlobalPrefix(API_PREFIX);
    document = buildDocument(app);
  });

  afterAll(async () => {
    await app.close();
  });

  it('@Public() 인 API 는 로그인 없이 부를 수 있다고 적는다', () => {
    expect(document.paths['/api/v1/board/things'].get?.security).toEqual([{}]);
  });

  it('로그인이 필요한 API 는 따로 적지 않는다. 목록 전체의 기본(bearer)을 따른다', () => {
    expect(
      document.paths['/api/v1/board/things/mine'].get?.security,
    ).toBeUndefined();
    expect(document.security).toEqual([{ [BEARER_SCHEME]: [] }]);
  });

  it('@ForOperators() 를 붙인 컨트롤러의 API 는 운영자의 것이라고 적는다', () => {
    const lock = document.paths['/api/v1/board/things/{id}/lock'].put;

    expect(lock).toMatchObject({ 'x-audience': 'operator' });
    expect(document.paths['/api/v1/board/things'].get).not.toHaveProperty(
      'x-audience',
    );
  });

  it('오류의 모양(ErrorBody)이 목록에 실린다', () => {
    expect(document.components?.schemas).toHaveProperty('ErrorBody');
  });
});
