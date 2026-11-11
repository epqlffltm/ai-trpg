// web/e2e/support/mailpit.ts
// 가입과 로그인의 메일 코드를 Mailpit 에서 읽는다. 인증 서버는 e2e 스택에서 메일을 Mailpit 으로 보낸다(docker-compose.e2e.yml).
// 메일은 발송함(DB)에 적힌 뒤 워커(auth-mail)가 보낸다. 그래서 곧바로 오지 않는다. 올 때까지 다시 묻는다.

import { expect } from '@playwright/test';

const MAILPIT = process.env.E2E_MAILPIT_URL ?? 'http://127.0.0.1:8025';
// 메일의 코드. 인증 서버의 코드는 숫자 여섯 자리다(accounts/email_codes.py)
const CODE = /\b(\d{6})\b/;

type Summary = { ID: string };
/** 코드를 요청하기 전에 그 주소로 이미 와 있던 메일들. 그 뒤에 온 메일만 본다. */
export type MailMark = { address: string; seen: ReadonlySet<string> };

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${MAILPIT}${path}`);
  if (!response.ok) throw new Error(`Mailpit ${path} → ${response.status}`);
  return (await response.json()) as T;
}

/** 그 주소로 온 메일들. 새것부터다. */
async function messagesTo(address: string): Promise<Summary[]> {
  const query = encodeURIComponent(`to:"${address}"`);
  return (await getJson<{ messages: Summary[] }>(`/api/v1/search?query=${query}`)).messages;
}

/** 메일 하나의 본문(글). */
async function textOf(id: string): Promise<string> {
  return (await getJson<{ Text: string }>(`/api/v1/message/${id}`)).Text;
}

/**
 * 지금 그 주소로 와 있는 메일을 적어 둔다. 코드를 요청하기 전에 부른다.
 * 시각으로 가르지 않는다. 앞의 메일(가입의 코드)이 늦게 닿으면 시각으로는 섞인다.
 */
export async function mailMark(address: string): Promise<MailMark> {
  return { address, seen: new Set((await messagesTo(address)).map((message) => message.ID)) };
}

/** 적어 둔 뒤에 그 주소로 온 메일의 코드. 올 때까지 기다린다(워커가 보낸다). */
export async function codeSentAfter(mark: MailMark): Promise<string> {
  let code: string | undefined;
  await expect
    .poll(
      async () => {
        const fresh = (await messagesTo(mark.address)).find((message) => !mark.seen.has(message.ID));
        code = fresh ? CODE.exec(await textOf(fresh.ID))?.[1] : undefined;
        return code;
      },
      { message: `${mark.address} 로 새로 온 코드`, timeout: 30_000, intervals: [500, 1_000, 2_000] },
    )
    .toBeTruthy();
  return code as string;
}
