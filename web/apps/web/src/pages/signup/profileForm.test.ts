// web/apps/web/src/pages/signup/profileForm.test.ts
// 가입 3단계의 미리 살피기와 보낼 모양. 서버의 규칙(아이디, 닉네임)과 같은지, 동의를 체크한 것만 보내는지 본다.

import { describe, expect, it } from 'vitest';
import type { ConsentDocument } from '../../api/signup';
import { canSubmit, EMPTY_DRAFT, missingRequired, profileHints, toSignupProfile, type ProfileDraft } from './profileForm';

const DOCUMENTS: ConsentDocument[] = [
  { item: 'terms', version: 2, effective_on: '2026-11-01', required: true },
  { item: 'privacy', version: 1, effective_on: '2026-10-20', required: true },
  { item: 'marketing', version: 1, effective_on: '2026-10-20', required: false },
];

const FILLED: ProfileDraft = {
  ...EMPTY_DRAFT,
  username: 'player_1',
  nickname: '모험가',
  password: 'long-enough-1',
  passwordAgain: 'long-enough-1',
  ageOver14: true,
  agreed: { terms: true, privacy: true },
};

describe('profileHints', () => {
  it.each([
    ['username', 'AB', '영문 소문자'],
    ['username', 'abc', '4~20자'],
    ['nickname', '모 험가', '띄어 쓸 수 없습니다'],
    ['nickname', 'a', '2~20자'],
  ])('%s=%s 이면 미리 알린다', (field, value, hint) => {
    expect(profileHints({ ...FILLED, [field]: value })[field]).toContain(hint);
  });

  it('아직 쓰지 않은 칸은 말하지 않는다', () => {
    expect(profileHints(EMPTY_DRAFT)).toEqual({});
  });

  it('비밀번호 확인이 다르면 알린다', () => {
    expect(profileHints({ ...FILLED, passwordAgain: 'other' }).passwordAgain).toBe('비밀번호가 서로 다릅니다.');
  });
});

describe('canSubmit', () => {
  it('모든 칸, 만 14세 이상, 필수 동의가 있으면 켠다', () => {
    expect(canSubmit(FILLED, DOCUMENTS)).toBe(true);
  });

  it('필수 동의 하나가 빠지면 끈다', () => {
    const draft = { ...FILLED, agreed: { terms: true } };
    expect(missingRequired(DOCUMENTS, draft.agreed)).toEqual(['privacy']);
    expect(canSubmit(draft, DOCUMENTS)).toBe(false);
  });

  it('만 14세 이상을 체크하지 않으면 끈다', () => {
    expect(canSubmit({ ...FILLED, ageOver14: false }, DOCUMENTS)).toBe(false);
  });

  it('형식이 틀린 칸이 있으면 끈다', () => {
    expect(canSubmit({ ...FILLED, username: 'Bad Name' }, DOCUMENTS)).toBe(false);
  });
});

describe('toSignupProfile', () => {
  it('체크한 항목과 화면이 보인 판만 보낸다', () => {
    const profile = toSignupProfile({ ...FILLED, agreed: { terms: true, privacy: true, marketing: false } }, DOCUMENTS);

    expect(profile).toEqual({
      username: 'player_1',
      nickname: '모험가',
      password: 'long-enough-1',
      age_over_14: true,
      consents: { terms: 2, privacy: 1 },
    });
  });
});
