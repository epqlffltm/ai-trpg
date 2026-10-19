// board-server/test/tracing-export.e2e-spec.ts

/**
 * 서버가 뜰 때처럼 추적을 켜고(configureTracing) 앱을 닫으면, 모아 둔 span 을 수집기에 보내는지 본다.
 * 이 컴퓨터 안에 가짜 수집기를 띄운다. 묶어 보내기는 5초마다라, 닫을 때 보내지 않으면 수집기에 아무것도 오지 않는다.
 */

import { createServer, Server } from 'node:http';
import { AddressInfo } from 'node:net';
import { trace } from '@opentelemetry/api';
import request from 'supertest';
import { API_PREFIX } from '../src/app.setup.js';
import { useProvider } from '../src/observability/spans.js';
import { configureTracing, TRACES_PATH } from '../src/observability/tracing.js';
import { createTestApp } from './app.js';

/** 받은 요청의 주소들. */
const received: string[] = [];
let collector: Server;
let endpoint: string;

beforeAll(async () => {
  collector = createServer((incoming, response) => {
    incoming.resume();
    incoming.on('end', () => {
      received.push(incoming.url ?? '');
      response.writeHead(200).end();
    });
  });
  await new Promise<void>((resolve) =>
    collector.listen(0, '127.0.0.1', resolve),
  );
  const { port } = collector.address() as AddressInfo;
  endpoint = `http://127.0.0.1:${port}`;
});

afterAll(async () => {
  useProvider(trace.getTracerProvider());
  await new Promise((resolve) => collector.close(resolve));
});

it('앱을 닫으면 모아 둔 span 을 수집기의 /v1/traces 로 보낸다', async () => {
  const app = await createTestApp();
  configureTracing(endpoint, {
    service: 'board-server',
    environment: 'test',
    version: 'test',
  });

  await request(app.getHttpServer()).get(`/${API_PREFIX}/boards`).expect(200);
  expect(received).toEqual([]);
  await app.close();

  expect(received).toEqual([TRACES_PATH]);
});
