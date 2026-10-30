// web/apps/web/src/pages/settings/Settings.test.tsx
// 설정(A12). 로그인 없이 열기, 밝기와 글자 크기를 고르면 문서에 입히고 브라우저에 두기, 단축키 끄기(테이블 방이 듣지 않음),
// 처음으로 되돌리기, 저장이 막힌 브라우저의 안내, 머리의 밝기 고르기(설정 화면과 같은 값). 저장해 둔 값 읽기의 순수한 함수.

import { act, fireEvent, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { DEFAULT_SETTINGS, parseSettings } from '../../settings/settings';
import { getSettingsSnapshot, resetSettingsForTest, updateSettings } from '../../settings/settingsStore';
import { installFakeFetch, json } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { useStatusShortcuts } from '../trpg/room/status/useStatusShortcuts';

const KEY = 'ai-trpg.settings';

function signedOut() {
  installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }) });
}

function stored(): unknown {
  return JSON.parse(window.localStorage.getItem(KEY) ?? 'null');
}

beforeEach(() => {
  window.localStorage.clear();
  resetSettingsForTest();
  delete document.documentElement.dataset.theme;
  delete document.documentElement.dataset.textSize;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('설정', () => {
  it('밝기와 글자 크기를 고르면 바로 입히고 이 브라우저에 둔다. 처음으로 되돌린다', async () => {
    signedOut();
    renderApp('/settings');

    await userEvent.click(await screen.findByRole('radio', { name: '어둡게' }));
    expect(document.documentElement.dataset.theme).toBe('dark');
    await userEvent.click(screen.getByRole('radio', { name: '아주 크게' }));
    expect(document.documentElement.dataset.textSize).toBe('larger');
    await userEvent.click(screen.getByRole('checkbox', { name: '테이블 방에서 단축키 쓰기' }));
    expect(stored()).toEqual({ theme: 'dark', textSize: 'larger', shortcuts: false });
    expect(screen.getByRole('checkbox', { name: '테이블 방에서 단축키 쓰기' })).not.toBeChecked();

    await userEvent.click(screen.getByRole('button', { name: '처음으로 되돌리기' }));
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(document.documentElement.dataset.textSize).toBeUndefined();
    expect(screen.getByRole('radio', { name: '기기 설정을 따름' })).toBeChecked();
    expect(stored()).toEqual(DEFAULT_SETTINGS);
  });

  it('저장이 막힌 브라우저면 창을 닫을 때까지만 둔다고 알린다', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    signedOut();
    renderApp('/settings');
    expect(await screen.findByText(/창을 닫으면 설정이 처음으로 돌아갑니다/)).toBeInTheDocument();
  });

  it('머리의 밝기 고르기로 바로 바꾸고, 설정 화면도 같은 값을 보인다', async () => {
    signedOut();
    renderApp('/');

    const group = await screen.findByRole('group', { name: '밝기' });
    const system = screen.getByRole('button', { name: '밝기: 기기 설정을 따름' });
    expect(system).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(screen.getByRole('button', { name: '밝기: 어둡게' }));
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(stored()).toMatchObject({ theme: 'dark' });
    expect(screen.getByRole('button', { name: '밝기: 어둡게' })).toHaveAttribute('aria-pressed', 'true');
    expect(group).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '밝기: 기기 설정을 따름' }));
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(getSettingsSnapshot().settings.theme).toBe('system');
  });

  it('단축키를 끄면 테이블 방이 키를 듣지 않고, 켜면 다시 듣는다', () => {
    updateSettings({ shortcuts: false });
    const onTab = vi.fn();
    renderHook(() => useStatusShortcuts(onTab));

    fireEvent.keyDown(document, { key: 'j' });
    expect(onTab).not.toHaveBeenCalled();
    act(() => updateSettings({ shortcuts: true }));
    fireEvent.keyDown(document, { key: 'j' });
    expect(onTab).toHaveBeenCalledWith('world');
  });
});

describe('설정의 순수한 함수', () => {
  it('저장해 둔 값을 읽는다. 모르는 값은 기본값', () => {
    expect(parseSettings(null)).toEqual(DEFAULT_SETTINGS);
    expect(parseSettings({ theme: 'neon', textSize: 'large', shortcuts: 'yes' })).toEqual({ theme: 'system', textSize: 'large', shortcuts: true });
    window.localStorage.setItem(KEY, '{"theme":"light"}');
    resetSettingsForTest();
    expect(getSettingsSnapshot()).toEqual({ settings: { ...DEFAULT_SETTINGS, theme: 'light' }, persistent: true });
  });
});
