// web/apps/web/src/api/tableHost.ts
// 방장의 운영(B6 의 ⑤). 내보내기, 방장 넘기기, "한 번 더 굴리기" 주기, 테이블 끝내기, 진행의 설정 바꾸기.
// 모두 방장만 한다(아니면 403). 모두 바뀐 테이블(TableDetail)을 돌려준다. 다른 사람은 스트림의 이벤트로 다시 읽는다.
// 서술 모델과 단계(B8)도 여기서 바꾼다. 모집 중에만, 시작한 뒤에는 지금 모델이나 단계를 쓸 수 없을 때만 된다.

import { apiRequest } from './http';
import type { NarrationStyle, TableDetail } from './types';

function tablePath(tableId: string, rest: string): string {
  return `/api/v1/game/tables/${encodeURIComponent(tableId)}${rest}`;
}

/** 참가자를 내보낸다. 초대 코드가 새로 만들어진다(응답에 새 코드). 진행 중이면 그 사람만 기다리던 라운드가 닫힌다 */
export function kickMember(tableId: string, userId: string): Promise<TableDetail> {
  return apiRequest<TableDetail>(tablePath(tableId, `/members/${encodeURIComponent(userId)}`), { method: 'DELETE' });
}

/** 방장을 다른 참가자에게 넘긴다 */
export function transferHost(tableId: string, userId: string): Promise<TableDetail> {
  return apiRequest<TableDetail>(tablePath(tableId, '/host'), { method: 'PUT', body: { user_id: userId } });
}

/** 한 사람에게 "한 번 더 굴리기"를 준다. 제작자가 허락한 테이블에서, 지금 캐릭터를 위해 굴린 사람에게만 */
export function grantReroll(tableId: string, userId: string): Promise<TableDetail> {
  return apiRequest<TableDetail>(tablePath(tableId, `/members/${encodeURIComponent(userId)}/reroll`), { method: 'POST' });
}

/** 테이블을 끝낸다. 되돌릴 수 없다 */
export function endTable(tableId: string): Promise<TableDetail> {
  return apiRequest<TableDetail>(tablePath(tableId, '/end'), { method: 'POST' });
}

/** 서술 문체. null 이면 시나리오의 추천 문체. 다음 서술부터 */
export function changeNarrationStyle(tableId: string, style: NarrationStyle | null): Promise<TableDetail> {
  return apiRequest<TableDetail>(tablePath(tableId, '/narration-style'), { method: 'PUT', body: { narration_style: style } });
}

/** 라운드의 시간 제한(초). null 이면 없앤다. 다음 라운드부터(지금 열린 라운드의 마감은 그대로) */
export function changeRoundTimeLimit(tableId: string, seconds: number | null): Promise<TableDetail> {
  return apiRequest<TableDetail>(tablePath(tableId, '/round-time-limit'), { method: 'PUT', body: { round_time_limit: seconds } });
}

/** 크레딧이 모자란 사람을 기다리는 시간(초)과, 지나면 그 사람을 빼는가. 지금 기다리는 라운드에도 바로 */
export function changeCreditWait(tableId: string, seconds: number, removeShortPayers: boolean): Promise<TableDetail> {
  return apiRequest<TableDetail>(tablePath(tableId, '/credit-wait'), {
    method: 'PUT',
    body: { credit_wait_seconds: seconds, remove_short_payers: removeShortPayers },
  });
}

/** 쪽지를 보낸 사실을 모두에게 알리는가 */
export function changeWhisperNotice(tableId: string, enabled: boolean): Promise<TableDetail> {
  return apiRequest<TableDetail>(tablePath(tableId, '/whisper-notice'), { method: 'PUT', body: { whisper_notice: enabled } });
}

/** 참고 자료를 서술에 넣는가. 모집 중에만, 판의 세계관이 허용할 때만(아니면 422) */
export function changeReferences(tableId: string, enabled: boolean): Promise<TableDetail> {
  return apiRequest<TableDetail>(tablePath(tableId, '/references'), { method: 'PUT', body: { references_enabled: enabled } });
}

/**
 * 서술 모델과 단계를 바꾼다. 모집 중에만, 시작한 뒤에는 지금 쓰는 것을 쓸 수 없을 때만(아니면 409 narration_model_locked).
 * 목록에 없는 모델이면 422 narration_model, 그 모델이 팔지 않는 단계면 422 narration_steps 다. 다음 라운드부터 쓴다
 */
export function changeNarrationModel(tableId: string, model: string, inputStep: number, outputStep: number): Promise<TableDetail> {
  return apiRequest<TableDetail>(tablePath(tableId, '/narration-model'), {
    method: 'PUT',
    body: { narration_model: model, input_step: inputStep, output_step: outputStep },
  });
}
