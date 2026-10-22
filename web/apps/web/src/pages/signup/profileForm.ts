// web/apps/web/src/pages/signup/profileForm.ts
// 가입 3단계의 입력을 미리 살피고 보낼 모양으로 바꾼다. 화면을 그리지 않는 순수한 함수들이다.
// 규칙은 인증 서버의 것과 같다(화면 명세 A2 의 "입력의 규칙"). 최종 판단은 서버가 한다. 화면은 미리 알려 줄 뿐이다.
// 비밀번호의 강도(흔한 것, 아이디와 비슷한 것)는 서버만 안다. 서버의 글을 그 칸에 보인다.

import type { ConsentDocument, SignupProfile } from '../../api/signup';

export const USERNAME_PATTERN = /^[a-z0-9_]{4,20}$/;
export const NICKNAME_PATTERN = /^[가-힣a-zA-Z0-9_]{2,20}$/;

export type ProfileDraft = {
  username: string;
  nickname: string;
  password: string;
  passwordAgain: string;
  ageOver14: boolean;
  /** 항목마다 체크했는가. 처음에는 모두 비어 있다(미리 체크하지 않는다) */
  agreed: Record<string, boolean>;
};

export const EMPTY_DRAFT: ProfileDraft = {
  username: '',
  nickname: '',
  password: '',
  passwordAgain: '',
  ageOver14: false,
  agreed: {},
};

/** 칸마다 미리 알려 줄 것. 아직 쓰지 않은 칸은 말하지 않는다 */
export function profileHints(draft: ProfileDraft): Record<string, string> {
  const hints: Record<string, string> = {};
  if (draft.username && !USERNAME_PATTERN.test(draft.username)) {
    hints.username = '영문 소문자, 숫자, 밑줄로 4~20자입니다.';
  }
  if (draft.nickname && !NICKNAME_PATTERN.test(draft.nickname)) {
    hints.nickname = '한글, 영문, 숫자, 밑줄로 2~20자입니다. 띄어 쓸 수 없습니다.';
  }
  if (draft.passwordAgain && draft.password !== draft.passwordAgain) {
    hints.passwordAgain = '비밀번호가 서로 다릅니다.';
  }
  return hints;
}

/** 체크하지 않은 필수 항목 */
export function missingRequired(documents: ConsentDocument[], agreed: Record<string, boolean>): string[] {
  return documents.filter((document) => document.required && !agreed[document.item]).map((document) => document.item);
}

/** 가입 버튼을 켤 수 있는가: 모든 칸, 만 14세 이상, 필수 동의 */
export function canSubmit(draft: ProfileDraft, documents: ConsentDocument[]): boolean {
  const filled = Boolean(draft.username && draft.nickname && draft.password && draft.passwordAgain);
  const valid = Object.keys(profileHints(draft)).length === 0;
  return filled && valid && draft.ageOver14 && missingRequired(documents, draft.agreed).length === 0;
}

/** 서버에 보낼 가입 내용. 동의는 체크한 항목과 화면이 보인 판이다 */
export function toSignupProfile(draft: ProfileDraft, documents: ConsentDocument[]): SignupProfile {
  const consents: Record<string, number> = {};
  for (const document of documents) {
    if (draft.agreed[document.item]) consents[document.item] = document.version;
  }
  return {
    username: draft.username,
    nickname: draft.nickname,
    password: draft.password,
    age_over_14: draft.ageOver14,
    consents,
  };
}
