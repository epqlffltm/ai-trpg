// web/apps/web/src/pages/trpg/tables/createForm.ts
// 테이블 만들기(B4)의 입력. 처음 값, 보내기 전의 검사, 서버에 보낼 본문. 화면을 그리지 않는 순수한 함수다.
// 처음 값은 서버의 기본값을 따른다(로비에 보이지 않음, 라운드 5분, 크레딧 5분 기다리고 모자란 사람은 빼기, 쪽지 알림 끔).
// 정원만 시나리오의 추천 인원의 최대로 둔다.

import type { CharacterMode, NarrationStyle, PublicListingDetail, TableCreate } from '../../../api/types';

export type CreateDraft = {
  openingIndex: number;
  capacity: number;
  isPublic: boolean;
  password: string;
  characterModes: CharacterMode[];
  /** 비우면 시나리오의 추천 문체 */
  narrationStyle: NarrationStyle | '';
  /** 초. null 이면 제한 없음 */
  roundTimeLimit: number | null;
  /** 비우면 시나리오의 추천 모델(쓸 수 없으면 같은 회사의 대체 모델) */
  narrationModel: string;
  creditWaitSeconds: number;
  removeShortPayers: boolean;
  whisperNotice: boolean;
  referencesEnabled: boolean;
};

/** 라운드 시간 제한으로 고를 것(서버: 30초~1시간, 또는 제한 없음) */
export const ROUND_LIMITS: (number | null)[] = [60, 180, 300, 600, 1800, 3600, null];
/** 크레딧이 모자란 사람을 기다리는 시간으로 고를 것(서버: 30초~1시간) */
export const CREDIT_WAITS = [60, 180, 300, 600, 1800, 3600];

const PASSWORD_MIN = 4;
const PASSWORD_MAX = 64;

export function initialDraft(listing: PublicListingDetail): CreateDraft {
  return {
    openingIndex: 0,
    capacity: listing.recommended_players.max,
    isPublic: false,
    password: '',
    characterModes: [...listing.character_modes],
    narrationStyle: '',
    roundTimeLimit: 300,
    narrationModel: '',
    creditWaitSeconds: 300,
    removeShortPayers: true,
    whisperNotice: false,
    referencesEnabled: false,
  };
}

/** 보내기 전에 알릴 것. 칸 이름 → 글. 비었으면 보낼 수 있다 */
export function draftHints(draft: CreateDraft): Record<string, string> {
  const hints: Record<string, string> = {};
  const length = draft.password.length;
  if (draft.isPublic && length > 0 && (length < PASSWORD_MIN || length > PASSWORD_MAX)) {
    hints.password = `비밀번호는 ${PASSWORD_MIN}~${PASSWORD_MAX}자입니다.`;
  }
  if (draft.characterModes.length === 0) hints.character_modes = '캐릭터를 얻는 방식을 하나 이상 고르세요.';
  return hints;
}

/**
 * 서버에 보낼 본문. 비운 것은 보내지 않아 서버가 시나리오의 것을 쓴다.
 * 비밀번호는 로비에 보이는 테이블에만 건다(비공개면 보내지 않는다). 앞뒤 공백을 떼지 않는다.
 * 캐릭터 방식은 시나리오가 허용한 것을 모두 고르면 보내지 않는다(판의 것 그대로).
 */
export function toTableCreate(draft: CreateDraft, listing: PublicListingDetail): TableCreate {
  const narrowed = draft.characterModes.length < listing.character_modes.length;
  return {
    scenario_id: listing.scenario_id,
    opening_index: draft.openingIndex,
    capacity: draft.capacity,
    is_public: draft.isPublic,
    password: draft.isPublic && draft.password !== '' ? draft.password : null,
    character_modes: narrowed ? listing.character_modes.filter((mode) => draft.characterModes.includes(mode)) : null,
    narration_style: draft.narrationStyle === '' ? null : draft.narrationStyle,
    round_time_limit: draft.roundTimeLimit,
    narration_model: draft.narrationModel === '' ? null : draft.narrationModel,
    // 서술의 입력·출력 단계(#387)는 아직 화면에서 고르지 않는다. 기본 단계다
    input_step: 0,
    output_step: 0,
    credit_wait_seconds: draft.creditWaitSeconds,
    remove_short_payers: draft.removeShortPayers,
    whisper_notice: draft.whisperNotice,
    references_enabled: listing.references_allowed && draft.referencesEnabled,
  };
}
