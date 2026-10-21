// board-server/src/openapi/document.ts

/**
 * 이 서버의 API 목록(OpenAPI)을 만든다. 만들어진 앱을 받아 목록을 돌려준다. 앱을 띄우지 않는다.
 *
 * 목록의 바탕은 @nestjs/swagger 가 컨트롤러와 *.dto.ts, *.query.ts, *.response.ts 의 클래스에서 읽는다.
 * 칸의 타입과 주석은 빌드할 때 도구의 플러그인이 읽어 둔다(nest-cli.json). 그래서 목록은 빌드한 코드(dist/)에서 만든다.
 * 도구가 읽은 것에 이 서버의 규칙 둘을 더한다. 둘 다 받은 목록을 고치지 않고 고친 사본을 돌려준다.
 *
 *   - optionalWhenDefaulted: 기본값이 있는 입력은 적지 않아도 된다. 도구는 기본값이 있어도 반드시 적어야 한다고 적는다.
 *   - withErrorResponses: API 의 오류는 모두 같은 모양이다(errors/error-body.ts). 도구는 그것을 모른다.
 *
 * 로그인은 기본으로 필요하다(auth.guard.ts). 목록에도 기본으로 bearer 토큰이 필요하다고 적고,
 * 로그인 없이 부르는 API 는 @Public() 이 목록에 따로 적는다(auth/public.decorator.ts).
 */

import { INestApplication } from '@nestjs/common';
import {
  DocumentBuilder,
  OpenAPIObject,
  OperationObject,
  ParameterObject,
  ReferenceObject,
  SchemaObject,
  SwaggerModule,
} from '@nestjs/swagger';
import { API_PREFIX } from '../app.setup.js';
import { ErrorBody } from '../errors/error-body.js';

/** 토큰을 적는 방식의 이름. 목록 안에서 이 이름으로 가리킨다 */
export const BEARER_SCHEME = 'bearer';

/** 주소 한 칸 아래에서 요청의 방식인 키 */
const HTTP_METHODS = [
  'get',
  'put',
  'post',
  'delete',
  'patch',
  'head',
  'options',
  'trace',
] as const;

/** 목록의 첫머리. 이름과 설명, 토큰의 방식이다. */
export function documentConfig(): Omit<OpenAPIObject, 'paths'> {
  return new DocumentBuilder()
    .setTitle('AI TRPG 게시판 서버')
    .setDescription('게시판과 글, 댓글, 신고, 글 고정.')
    .setVersion('0.1.0')
    .addBearerAuth(
      {
        type: 'http',
        scheme: 'bearer',
        bearerFormat: 'JWT',
        description:
          '인증 서버가 발급한 access 토큰. 대상(aud)에 ai-trpg-board 가 있어야 한다',
      },
      BEARER_SCHEME,
    )
    .addSecurityRequirements(BEARER_SCHEME)
    .build();
}

/** 목록의 요청 방식(operation)들을 주소와 함께 꺼낸다. */
export function operationsOf(
  document: OpenAPIObject,
): { path: string; operation: OperationObject }[] {
  return Object.entries(document.paths).flatMap(([path, item]) =>
    HTTP_METHODS.flatMap((method) => {
      const operation = item[method];
      return operation === undefined ? [] : [{ path, operation }];
    }),
  );
}

/** 참조($ref)가 아니라 모양이 적힌 것인가. */
function isSchema(
  value: SchemaObject | ReferenceObject | undefined,
): value is SchemaObject {
  return value !== undefined && !('$ref' in value);
}

/** 주소에 붙이는 값(쿼리) 하나. 기본값이 있으면 적지 않아도 되는 것으로 고친다. */
function optionalParameter(
  parameter: ParameterObject | ReferenceObject,
): ParameterObject | ReferenceObject {
  if ('$ref' in parameter || !isSchema(parameter.schema)) {
    return parameter;
  }
  if (parameter.schema.default === undefined) {
    return parameter;
  }
  return { ...parameter, required: false };
}

/**
 * 본문의 모양 하나. 기본값이 있는 칸을 반드시 적을 칸(required)에서 뺀다.
 * 남는 칸이 없으면 required 를 지운다. OpenAPI 3.0 은 빈 목록을 받지 않는다.
 */
function optionalProperties(schema: SchemaObject): SchemaObject {
  const properties = schema.properties ?? {};
  const required = (schema.required ?? []).filter((name) => {
    const property = properties[name];
    return !(isSchema(property) && property.default !== undefined);
  });
  const copy: SchemaObject = { ...schema, required };
  if (required.length === 0) {
    delete copy.required;
  }
  return copy;
}

/**
 * 기본값이 있는 입력을 적지 않아도 되는 것으로 고친다.
 *
 * 입력의 클래스는 칸에 기본값을 둔다(page: number = 1). 값이 없이 오면 그 값이 들어간다.
 * 도구는 칸에 물음표(?)가 없으면 반드시 적어야 한다고 적는다. 그대로 두면 화면의 타입이 page 를 늘 요구한다.
 */
export function optionalWhenDefaulted(document: OpenAPIObject): OpenAPIObject {
  const copy = structuredClone(document);
  for (const { operation } of operationsOf(copy)) {
    operation.parameters = operation.parameters?.map(optionalParameter);
  }
  const schemas = copy.components?.schemas ?? {};
  for (const [name, schema] of Object.entries(schemas)) {
    if (isSchema(schema) && schema.required !== undefined) {
      schemas[name] = optionalProperties(schema);
    }
  }
  return copy;
}

/**
 * API 주소 아래의 요청마다 오류의 응답을 더한다. 상태 코드와 상관없이 본문은 ErrorBody 다.
 *
 * 오류의 본문은 앱 전체에 건 필터가 만든다(errors/all-exceptions.filter.ts). 그래서 컨트롤러마다 적지 않고 여기서 한 번에 더한다.
 * 상태 확인(/health)은 API 주소 밖이고 오류의 모양을 쓰지 않는다. 더하지 않는다.
 */
export function withErrorResponses(document: OpenAPIObject): OpenAPIObject {
  const copy = structuredClone(document);
  const apiRoot = `/${API_PREFIX}/`;
  for (const { path, operation } of operationsOf(copy)) {
    if (path.startsWith(apiRoot)) {
      operation.responses.default = {
        description: '오류. 상태 코드가 무엇이든 본문은 이 모양이다',
        content: {
          'application/json': {
            schema: { $ref: `#/components/schemas/${ErrorBody.name}` },
          },
        },
      };
    }
  }
  return copy;
}

/** 만들어진 앱에서 목록을 만든다. 앱에는 setupApp 이 걸려 있어야 주소의 앞부분이 맞는다. */
export function buildDocument(app: INestApplication): OpenAPIObject {
  const document = SwaggerModule.createDocument(app, documentConfig(), {
    extraModels: [ErrorBody],
  });
  return withErrorResponses(optionalWhenDefaulted(document));
}
