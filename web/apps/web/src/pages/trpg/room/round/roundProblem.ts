// web/apps/web/src/pages/trpg/room/round/roundProblem.ts
// 선언 내기와 라운드 닫기의 실패를 화면에 보일 것으로 바꾼다. 순수한 함수다.
//
// 게임 서버의 답(trpg-server/app/rounds/router.py, errors.py):
//   - 409: 테이블이나 라운드의 지금 상태와 부딪힌다. 까닭은 reason(ApiError.code)
//   - 422: 행동이 규칙에 없는 것을 가리키거나(action.<칸> 가 이 테이블의 규칙에 없습니다), 겨눌 수 없는 대상이다.
//     어느 칸인지는 글(detail)에만 있어 하나로 알리고 다시 읽는다
//   - 403: 방장이 아니다(닫기)
// refresh 가 켜지면 라운드를 다시 읽는다(그 사이 마감했거나 다음 라운드가 열렸다).

import { ApiError } from '../../../../api/errors';
import { commonProblem, unknownProblem, type FormProblem } from '../../../../auth/problem';

export type RoundProblem = FormProblem & { refresh?: boolean };

const FAILED = '처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.';

const CONFLICTS: Record<string, RoundProblem> = {
  round_closing: { message: '그 사이에 선언을 마감했습니다. 결과를 기다려 주세요.', refresh: true },
  not_playing: { message: '진행 중인 테이블이 아닙니다.', refresh: true },
  not_started: { message: '아직 시작하지 않은 테이블입니다.', refresh: true },
  character_downed: { message: '캐릭터가 쓰러져 있어 판정을 붙일 수 없습니다. 글만 낼 수 있습니다.' },
  character_incapacitated: { message: '캐릭터가 입은 부상 때문에 판정을 붙일 수 없습니다. 글만 낼 수 있습니다.' },
  character_dead: { message: '캐릭터가 죽어 선언을 낼 수 없습니다.', refresh: true },
  character_arriving: { message: '이번 라운드에 들어온 캐릭터입니다. 다음 라운드부터 선언합니다.', refresh: true },
  // 행동의 대상과 물건. 그 사이에 바뀌었을 수 있어 다시 읽는다
  npc_dead: { message: '그 인물은 이미 죽었습니다.', refresh: true },
  monster_dead: { message: '그 몬스터는 이미 쓰러졌습니다.', refresh: true },
  already_injured: { message: '대상이 이미 그 부상을 입고 있습니다.', refresh: true },
  target_immune: { message: '그 몬스터는 그런 부상을 입지 않습니다. 다른 부상을 노려 주세요.' },
  not_injured: { message: '대상이 그 부상을 입고 있지 않습니다.', refresh: true },
  patient_dead: { message: '치료하려는 캐릭터가 이미 죽었습니다.', refresh: true },
  already_named: { message: '그 인물의 진짜 이름은 이미 드러났습니다.', refresh: true },
  item_not_held: { message: '그 물건을 그만큼 가지고 있지 않습니다.', refresh: true },
  recipient_dead: { message: '받을 캐릭터가 이미 죽었습니다.', refresh: true },
  recipient_full: { message: '그 물건을 더 가질 수 없습니다(한 가지 99개까지).', refresh: true },
  not_on_map: { message: '맵에 서 있지 않아 가거나 찾을 수 없습니다.', refresh: true },
  target_not_down: { message: '대상이 쓰러지지 않았습니다. 그때는 훔치기입니다.', refresh: true },
  weapon_not_worn: { message: '고른 무기를 착용하고 있지 않습니다. 장비를 확인해 주세요.', refresh: true },
  // 돈(#278)
  not_merchant: { message: '그 인물은 상인이 아닙니다.', refresh: true },
  merchant_unavailable: { message: '상인이 쓰러졌거나 적대해 거래하지 않습니다.', refresh: true },
  out_of_stock: { message: '상인에게 그만큼이 없습니다.', refresh: true },
  not_enough_money: { message: '돈이 모자랍니다.', refresh: true },
  too_much_money: { message: '받을 쪽이 돈을 더 가질 수 없습니다.', refresh: true },
};

/** 선언 내기(PUT .../rounds/current/declaration) */
export function describeDeclarationProblem(error: unknown): RoundProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 404) return { message: '이 테이블에 앉아 있지 않습니다.', refresh: true };
  if (error.status === 409) return CONFLICTS[error.code ?? ''] ?? unknownProblem(error, FAILED);
  if (error.status === 422) return { message: '고른 행동이 이 테이블의 규칙이나 지금 장면과 맞지 않습니다. 다시 읽은 값으로 골라 주세요.', refresh: true };
  return unknownProblem(error, FAILED);
}

/** 라운드 닫기와 서술 다시 맡기기(방장, POST .../rounds/current/close) */
export function describeCloseProblem(error: unknown): RoundProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 403) return { message: '방장만 라운드를 닫을 수 있습니다.', refresh: true };
  if (error.status === 409) return { ...(CONFLICTS[error.code ?? ''] ?? { message: FAILED }), refresh: true };
  return unknownProblem(error, FAILED);
}
