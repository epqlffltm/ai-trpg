// board-server/test/collector.ts

/**
 * OTLP(HTTP)를 받는 척하는 수집기. 이 컴퓨터 안에 띄워 span 과 메트릭을 실제로 보내 본다.
 * src/observability/tracing.spec.ts 와 metrics.spec.ts 가 쓴다. 받은 주소와 본문의 형식만 적는다.
 */

import { createServer, Server } from 'node:http';
import { AddressInfo } from 'node:net';

/** 받은 요청. 주소와 본문의 형식만 본다 */
export interface Received {
  path: string | undefined;
  contentType: string | undefined;
  bytes: number;
}

/** OTLP(HTTP)를 받는 척하는 수집기. */
export class Collector {
  readonly received: Received[] = [];
  private server: Server | undefined;

  /** 띄우고 주소(경로 없이)를 돌려준다. */
  async start(): Promise<string> {
    this.server = createServer((request, response) => {
      const chunks: Buffer[] = [];
      request.on('data', (chunk: Buffer) => chunks.push(chunk));
      request.on('end', () => {
        this.received.push({
          path: request.url,
          contentType: request.headers['content-type'],
          bytes: Buffer.concat(chunks).length,
        });
        response.statusCode = 200;
        response.end();
      });
    });
    await new Promise<void>((resolve) =>
      this.server?.listen(0, '127.0.0.1', resolve),
    );
    const { port } = this.server.address() as AddressInfo;
    return `http://127.0.0.1:${port}`;
  }

  /** 끈다. */
  stop(): Promise<void> {
    return new Promise((resolve) => this.server?.close(() => resolve()));
  }
}
