// board-server/test/notifications.e2e-spec.ts

/**
 * 댓글과 답글을 사용자의 알림함에 알리는 것(src/notifications/)을 앱을 통째로 만들어 본다.
 * 실제 PostgreSQL 의 테스트용 스키마에서 돈다. 알림 서버는 띄우지 않는다. 가짜를 꽂는다.
 *
 * 보는 것.
 *   - 발송함에 적기: 글에 단 댓글은 글쓴이에게, 답글은 그 댓글의 글쓴이에게 한 줄. 자기에게는 없다.
 *     댓글이 거절되면(없는 글, 답글에 단 답글) 알림도 없다.
 *   - 보내는 작업: 보내면 지우고, 못 보내면 기다리는 시간을 늘려 다시 보내고, 받지 않으면 실패로 둔다.
 *     오래 못 보낸 것은 지운다. 알림 서버가 없으면 보내지 않는다. 한 알림이 예외로 끝나도 다른 알림은 보낸다.
 */

import { createServer, Server } from 'node:http';
import { AddressInfo } from 'node:net';
import { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { DataSource } from 'typeorm';
import { API_PREFIX } from '../src/app.setup.js';
import {
  HttpNotificationSender,
  NotificationSender,
  PUT_PATH,
  Sent,
} from '../src/notifications/notification-client.js';
import {
  NOTIFICATION_SENDER,
  NotificationDispatcher,
  STALE_AFTER_MS,
} from '../src/notifications/notification-dispatcher.js';
import { NotificationDispatchRunner } from '../src/notifications/notification-dispatcher.runner.js';
import { OutgoingNotification } from '../src/notifications/outgoing-notification.entity.js';
import { SIGNATURE_HEADER, sign } from '../src/notifications/signing.js';
import { both, createTestApp, Customize, useKeys } from './app.js';
import { clearData } from './data.js';
import { makeSigningKey, publicKeys, SigningKey, signToken } from './tokens.js';

const API = `/${API_PREFIX}`;

const WRITER = '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b';
const COMMENTER = '7d0e3a52-1f4b-4c8e-8a21-9b6c5d4e3f2a';
const REPLIER = 'c4a1b2d3-5e6f-4a7b-8c9d-0e1f2a3b4c5d';
const NOW = new Date('2026-10-19T03:00:00Z');

/** 보낸 것을 적어 두는 가짜 알림 서버. answers 의 결과를 차례로 낸다. 다 쓰면 받았다. Error 면 그것을 던진다. */
class FakeSender implements NotificationSender {
  answers: (Sent | Error)[] = [];
  sent: string[] = [];

  send(notification: OutgoingNotification): Promise<Sent> {
    this.sent.push(notification.sourceKey);
    const answer = this.answers.shift() ?? { delivery: 'delivered' };
    return answer instanceof Error
      ? Promise.reject(answer)
      : Promise.resolve(answer);
  }
}

let app: NestExpressApplication;
let key: SigningKey;
let sender: FakeSender;
let postId: string;

const useSender =
  (fake: NotificationSender): Customize =>
  (builder) =>
    builder.overrideProvider(NOTIFICATION_SENDER).useValue(fake);

beforeAll(async () => {
  key = await makeSigningKey('key-1');
  sender = new FakeSender();
  app = await createTestApp(
    both(
      useKeys(() => publicKeys(key)),
      useSender(sender),
    ),
  );
  // 타이머의 바퀴가 테스트가 부르는 바퀴와 겹치지 않게 멈춘다
  app.get(NotificationDispatchRunner).onModuleDestroy();
});

afterAll(async () => {
  await app.close();
});

beforeEach(async () => {
  await clearData(app);
  sender.answers = [];
  sender.sent = [];
  postId = await writtenPostId();
});

async function as(userId: string): Promise<{ Authorization: string }> {
  return {
    Authorization: `Bearer ${await signToken(key, { subject: userId })}`,
  };
}

/** WRITER 가 자유 게시판에 글을 써서 그 번호를 돌려준다. */
async function writtenPostId(): Promise<string> {
  const response = await request(app.getHttpServer())
    .post(`${API}/boards/free/posts`)
    .set(await as(WRITER))
    .send({ title: '첫 모험', content: '본문입니다.' });
  expect(response.status).toBe(201);
  return (response.body as { id: string }).id;
}

/** 글에 댓글을 단다. parentId 를 주면 답글이다. 응답을 그대로 돌려준다. */
async function comment(
  userId: string,
  parentId?: string,
  post = postId,
): Promise<request.Response> {
  return request(app.getHttpServer())
    .post(`${API}/posts/${post}/comments`)
    .set(await as(userId))
    .send({ content: '댓글입니다.', parent_id: parentId });
}

/** 댓글을 달아 그 번호를 돌려준다. */
async function commentId(userId: string, parentId?: string): Promise<string> {
  const response = await comment(userId, parentId);
  expect(response.status).toBe(201);
  return (response.body as { id: string }).id;
}

/** 발송함의 모든 줄. 적은 차례다. */
function outgoing(): Promise<OutgoingNotification[]> {
  return app
    .get(DataSource)
    .getRepository(OutgoingNotification)
    .find({ order: { id: 'ASC' } });
}

/** 발송함에 한 줄을 적는다. values 로 칸을 바꾼다. */
async function put(
  sourceKey: string,
  values: Partial<OutgoingNotification> = {},
): Promise<void> {
  await app
    .get(DataSource)
    .getRepository(OutgoingNotification)
    .save({
      sourceKey,
      userId: WRITER,
      kind: 'post.commented',
      payload: { post_title: '첫 모험' },
      ...values,
    });
}

function dispatcher(): NotificationDispatcher {
  return app.get(NotificationDispatcher);
}

describe('발송함에 적기', () => {
  it('남의 글에 단 댓글은 글쓴이에게 한 줄이다', async () => {
    const id = await commentId(COMMENTER);

    const [notice] = await outgoing();

    expect([notice.userId, notice.kind, notice.status]).toEqual([
      WRITER,
      'post.commented',
      'pending',
    ]);
    expect(notice.sourceKey).toBe(`post.commented:${id}`);
    expect(notice.payload).toEqual({
      board_slug: 'free',
      post_id: postId,
      post_title: '첫 모험',
      comment_id: id,
    });
  });

  it('답글은 그 댓글의 글쓴이에게만 간다', async () => {
    const parentId = await commentId(COMMENTER);
    const replyId = await commentId(REPLIER, parentId);

    const notices = await outgoing();

    expect(notices.map((notice) => [notice.userId, notice.kind])).toEqual([
      [WRITER, 'post.commented'],
      [COMMENTER, 'comment.replied'],
    ]);
    expect(notices[1].payload).toMatchObject({
      comment_id: replyId,
      parent_id: parentId,
    });
  });

  it('자기 글과 자기 댓글에는 알리지 않는다', async () => {
    const own = await commentId(WRITER);
    await commentId(WRITER, own);

    expect(await outgoing()).toEqual([]);
  });

  it('거절된 댓글은 알림도 없다', async () => {
    const parentId = await commentId(WRITER);
    const replyId = await commentId(COMMENTER, parentId);
    await clearOutgoing();

    const onReply = await comment(REPLIER, replyId);
    const onMissingPost = await comment(COMMENTER, undefined, '999999');

    expect([onReply.status, onMissingPost.status]).toEqual([400, 404]);
    expect(await outgoing()).toEqual([]);
  });
});

/** 발송함을 비운다. */
async function clearOutgoing(): Promise<void> {
  await app.get(DataSource).query('DELETE FROM "outgoing_notifications"');
}

describe('보내는 작업', () => {
  it('보낸 알림은 발송함에서 지운다', async () => {
    await commentId(COMMENTER);

    const dispatched = await dispatcher().tick(NOW);

    expect(dispatched.sent).toBe(1);
    expect(sender.sent).toHaveLength(1);
    expect(await outgoing()).toEqual([]);
  });

  it('못 보낸 알림은 기다렸다가 다시 보낸다', async () => {
    await put('a');
    sender.answers = [{ delivery: 'unavailable', reason: 'status_503' }];

    expect((await dispatcher().tick(NOW)).retried).toBe(1);
    const [waiting] = await outgoing();
    expect([waiting.attempts, waiting.lastError]).toEqual([1, 'status_503']);
    expect(waiting.nextAttemptAt).toEqual(new Date(NOW.getTime() + 10_000));

    // 기다리는 동안은 보내지 않는다. 지나면 다시 보낸다
    await dispatcher().tick(new Date(NOW.getTime() + 9_000));
    await dispatcher().tick(new Date(NOW.getTime() + 10_000));
    expect(sender.sent).toEqual(['a', 'a']);
    expect(await outgoing()).toEqual([]);
  });

  it('받지 않은 알림은 실패로 두고 다시 보내지 않는다', async () => {
    await put('a');
    sender.answers = [{ delivery: 'rejected', reason: 'status_409' }];

    expect((await dispatcher().tick(NOW)).rejected).toBe(1);
    await dispatcher().tick(new Date(NOW.getTime() + 60 * 60 * 1000));

    const [failed] = await outgoing();
    expect([failed.status, failed.lastError]).toEqual(['failed', 'status_409']);
    expect(sender.sent).toEqual(['a']);
  });

  it('오래 못 보낸 알림은 지우고, 받지 않은 것은 남긴다', async () => {
    const old = new Date(Date.now() - STALE_AFTER_MS - 60_000);
    await put('old', { createdAt: old });
    await put('old-failed', { createdAt: old, status: 'failed' });
    await put('fresh');

    const dispatched = await dispatcher().tick(new Date());

    expect(dispatched.dropped).toBe(1);
    expect(sender.sent).toEqual(['fresh']);
    expect((await outgoing()).map((row) => row.sourceKey)).toEqual([
      'old-failed',
    ]);
  });

  it('한 알림이 예외로 끝나도 다른 알림은 보낸다', async () => {
    await put('a');
    await put('b');
    sender.answers = [new Error('알 수 없는 오류')];

    const dispatched = await dispatcher().tick(NOW);

    expect([dispatched.failed, dispatched.sent]).toEqual([1, 1]);
    // 예외가 난 알림은 그대로 남아 다음 바퀴에 다시 보낸다
    expect((await outgoing()).map((row) => row.sourceKey)).toEqual(['a']);
  });

  it('다른 서버가 먼저 보내 지운 줄을 되살리지 않는다', async () => {
    await put('a');
    const [late] = await outgoing();
    await dispatcher().tick(NOW);

    await dispatcher().record(
      late,
      { delivery: 'unavailable', reason: 'timeout' },
      NOW,
    );

    expect(await outgoing()).toEqual([]);
  });
});

describe('늦게 온 결과', () => {
  it('다른 서버가 실패로 둔 줄을 다시 기다리게 하지 않는다', async () => {
    await put('a');
    const [late] = await outgoing();
    sender.answers = [{ delivery: 'rejected', reason: 'status_409' }];
    await dispatcher().tick(NOW);

    await dispatcher().record(
      late,
      { delivery: 'unavailable', reason: 'timeout' },
      NOW,
    );

    const [failed] = await outgoing();
    expect([failed.status, failed.lastError, failed.attempts]).toEqual([
      'failed',
      'status_409',
      0,
    ]);
  });
});

describe('알림 서버가 없을 때', () => {
  let silent: NestExpressApplication;

  beforeAll(async () => {
    silent = await createTestApp(useKeys(() => publicKeys(key)));
    silent.get(NotificationDispatchRunner).onModuleDestroy();
  });

  afterAll(async () => {
    await silent.close();
  });

  it('적기만 하고 보내지 않는다', async () => {
    await put('a');

    const dispatched = await silent.get(NotificationDispatcher).tick(NOW);

    expect(dispatched).toEqual({
      sent: 0,
      retried: 0,
      rejected: 0,
      failed: 0,
      dropped: 0,
    });
    expect(await outgoing()).toHaveLength(1);
  });
});

describe('진짜 알림 서버처럼 받는 곳에 보낼 때', () => {
  const SECRET = 'board-notification-test-secret-of-32';
  let server: Server;
  let real: NestExpressApplication;
  const received: { path: string; signature: string; body: string }[] = [];

  beforeAll(async () => {
    server = createServer((incoming, response) => {
      let body = '';
      incoming.on('data', (chunk: Buffer) => (body += chunk.toString('utf8')));
      incoming.on('end', () => {
        received.push({
          path: incoming.url ?? '',
          signature: String(incoming.headers[SIGNATURE_HEADER.toLowerCase()]),
          body,
        });
        response.writeHead(201).end();
      });
    });
    await new Promise<void>((resolve) =>
      server.listen(0, '127.0.0.1', resolve),
    );
    const { port } = server.address() as AddressInfo;
    const http = new HttpNotificationSender(
      `http://127.0.0.1:${port}`,
      SECRET,
      () => NOW,
    );
    real = await createTestApp(
      both(
        useKeys(() => publicKeys(key)),
        useSender(http),
      ),
    );
    real.get(NotificationDispatchRunner).onModuleDestroy();
  });

  afterAll(async () => {
    await real.close();
    await new Promise((resolve) => server.close(resolve));
  });

  it('댓글의 알림이 서명되어 알림 서버의 주소로 간다', async () => {
    const id = await commentId(COMMENTER);

    const dispatched = await real.get(NotificationDispatcher).tick(NOW);

    const [request] = received;
    expect(dispatched.sent).toBe(1);
    expect(request.path).toBe(PUT_PATH);
    expect(JSON.parse(request.body)).toMatchObject({
      source_key: `post.commented:${id}`,
      user_id: WRITER,
      kind: 'post.commented',
    });
    expect(request.signature).toBe(
      sign(SECRET, NOW.getTime() / 1000, 'POST', PUT_PATH, request.body),
    );
    expect(await outgoing()).toEqual([]);
  });
});
