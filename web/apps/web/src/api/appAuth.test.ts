// web/apps/web/src/api/appAuth.test.ts
// 앱의 길(VITE_AUTH_TRANSPORT=app)에서 로그인 2단계, 갱신, 로그아웃, 비밀번호 변경이 네이티브 플러그인을 거치는지 본다.
// 화면은 refresh 토큰을 받지 않고, 상태 코드를 다루는 것은 웹과 같다.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { installFakeFetch, tokens } from '../test/fakeFetch';
import { changePassword } from './account';
import { answerToResponse, usesAppAuth, type AppAuthPlugin, type NativeAnswer } from './appAuth';
import { logout, verifyLogin } from './auth';
import { ApiError, NetworkError } from './errors';
import { refreshSession } from './refresh';
import { clearSession, getSession, storeTokens } from './session';

type CapacitorGlobal = { Capacitor?: { Plugins?: { AppAuth?: AppAuthPlugin } } };

function answer(status: number, body?: unknown): Promise<NativeAnswer> {
  return Promise.resolve({ status, body });
}

function installPlugin(overrides: Partial<AppAuthPlugin> = {}) {
  const plugin = {
    verifyLogin: vi.fn(() => answer(200, tokens('app-token', { refresh_token: 'secret', refresh_expires_in: 1209600 }))),
    refresh: vi.fn(() => answer(200, tokens('refreshed'))),
    logout: vi.fn(() => answer(204)),
    changePassword: vi.fn(() => answer(200, tokens('changed'))),
    ...overrides,
  };
  (globalThis as CapacitorGlobal).Capacitor = { Plugins: { AppAuth: plugin } };
  return plugin;
}

describe('usesAppAuth', () => {
  it('비었거나 web 이면 웹의 길이다', () => {
    expect(usesAppAuth(undefined)).toBe(false);
    expect(usesAppAuth('')).toBe(false);
    expect(usesAppAuth('web')).toBe(false);
  });

  it('app 이면 앱의 길이다', () => {
    expect(usesAppAuth('app')).toBe(true);
  });

  it('그 밖의 값이면 멈춘다', () => {
    expect(() => usesAppAuth('native')).toThrow('VITE_AUTH_TRANSPORT');
  });
});

describe('answerToResponse', () => {
  it('본문의 refresh 토큰은 화면에 남기지 않는다', async () => {
    const response = answerToResponse({ status: 200, body: tokens('t', { refresh_token: 'secret', refresh_expires_in: 1 }) });

    const body = (await response.json()) as Record<string, unknown>;
    expect(body.access_token).toBe('t');
    expect(body).not.toHaveProperty('refresh_token');
    expect(body).not.toHaveProperty('refresh_expires_in');
  });

  it('204 는 본문이 없다', () => {
    expect(answerToResponse({ status: 204 }).status).toBe(204);
  });
});

describe('앱의 길', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_AUTH_TRANSPORT', 'app');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    delete (globalThis as CapacitorGlobal).Capacitor;
    clearSession();
  });

  it('로그인 2단계는 플러그인이 부르고 화면은 access 토큰만 갖는다', async () => {
    const plugin = installPlugin();
    const { seen } = installFakeFetch({});

    const session = await verifyLogin('ticket-1', '123456');

    expect(plugin.verifyLogin).toHaveBeenCalledWith({ loginTicket: 'ticket-1', code: '123456' });
    expect(session.accessToken).toBe('app-token');
    expect(JSON.stringify(getSession())).not.toContain('secret');
    expect(seen).toHaveLength(0);
  });

  it('로그인 2단계가 틀리면 웹과 같은 ApiError 다', async () => {
    installPlugin({ verifyLogin: vi.fn(() => answer(400, { detail: '인증 코드가 올바르지 않거나 만료되었습니다.' })) });

    await expect(verifyLogin('ticket-1', '000000')).rejects.toMatchObject({ status: 400 });
    expect(getSession()).toBeNull();
  });

  it('갱신은 플러그인이 하고 서버를 직접 부르지 않는다', async () => {
    const plugin = installPlugin();
    const { seen } = installFakeFetch({});

    const session = await refreshSession();

    expect(plugin.refresh).toHaveBeenCalledTimes(1);
    expect(session?.accessToken).toBe('refreshed');
    expect(seen).toHaveLength(0);
  });

  it('갱신이 401 이면 로그인이 끝난 것이다', async () => {
    installPlugin({ refresh: vi.fn(() => answer(401, { detail: '다시 로그인해 주세요.' })) });
    storeTokens(tokens('old'));

    expect(await refreshSession()).toBeNull();
    expect(getSession()).toBeNull();
  });

  it('갱신이 막은 IP 면 로그인이 끝난 것이다', async () => {
    installPlugin({ refresh: vi.fn(() => answer(403, { detail: '막혔습니다.', code: 'network_blocked' })) });
    storeTokens(tokens('old'));

    expect(await refreshSession()).toBeNull();
    expect(getSession()).toBeNull();
  });

  it('갱신의 그 밖의 실패는 로그아웃시키지 않는다', async () => {
    installPlugin({ refresh: vi.fn(() => answer(503, { detail: '잠시 뒤에' })) });
    storeTokens(tokens('old'));

    await expect(refreshSession()).rejects.toBeInstanceOf(ApiError);
    expect(getSession()?.accessToken).toBe('old');
  });

  it('플러그인이 서버에 닿지 못하면 NetworkError 다', async () => {
    installPlugin({ refresh: vi.fn(() => Promise.reject(new Error('offline'))) });
    storeTokens(tokens('old'));

    await expect(refreshSession()).rejects.toBeInstanceOf(NetworkError);
    expect(getSession()?.accessToken).toBe('old');
  });

  it('로그아웃은 플러그인이 하고 화면의 상태를 비운다', async () => {
    const plugin = installPlugin();
    storeTokens(tokens('old'));

    await logout();

    expect(plugin.logout).toHaveBeenCalledTimes(1);
    expect(getSession()).toBeNull();
  });

  it('로그아웃이 서버에 닿지 못해도 화면의 상태는 비운다', async () => {
    installPlugin({ logout: vi.fn(() => Promise.reject(new Error('offline'))) });
    storeTokens(tokens('old'));

    await logout();

    expect(getSession()).toBeNull();
  });

  it('비밀번호 변경은 지금의 access 토큰을 플러그인에 넘긴다', async () => {
    const plugin = installPlugin();
    storeTokens(tokens('current'));

    const session = await changePassword('old-password', 'new-password');

    expect(plugin.changePassword).toHaveBeenCalledWith({
      accessToken: 'current',
      currentPassword: 'old-password',
      newPassword: 'new-password',
    });
    expect(session.accessToken).toBe('changed');
  });

  it('플러그인이 없으면(브라우저에서 연 앱의 빌드) 로그인하지 못한다', async () => {
    await expect(verifyLogin('ticket-1', '123456')).rejects.toThrow('AppAuth');
  });
});
