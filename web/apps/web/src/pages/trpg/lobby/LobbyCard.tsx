// web/apps/web/src/pages/trpg/lobby/LobbyCard.tsx
// 로비의 테이블 하나. 들어가기 전에 알아야 할 설정을 모두 보인다(화면 명세 B3): 등급, 인원, 비밀번호, 문체,
// 라운드 시간 제한, 서술 모델(이름), 크레딧 기다리기, 쪽지 알림, 참고 자료.

import { Button } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import type { TableSummary } from '../../../api/types';
import { ratingBadge } from '../../home/labels';
import { durationLabel, narrationStyleLabel } from '../labels';
import { narrationModelsQuery } from '../queries';

type Props = { table: TableSummary; busy: boolean; disabled: boolean; onJoin: () => void };

export function LobbyCard({ table, busy, disabled, onJoin }: Props) {
  const modelName = useModelName(table.narration_model);
  const facts = tableFacts(table, modelName);
  return (
    <li className="lobby-card">
      <div className="lobby-card__body">
        <p className="lobby-card__title">
          {table.title}
          <span className="lobby-card__seats">
            {table.member_count}/{table.capacity}명
          </span>
        </p>
        <ul className="lobby-card__facts">
          {facts.map((fact) => (
            <li key={fact}>{fact}</li>
          ))}
        </ul>
      </div>
      <Button busy={busy} disabled={disabled && !busy} onClick={onJoin} aria-label={`${table.title}에 들어가기`}>
        들어가기
      </Button>
    </li>
  );
}

/** 카드에 보일 설정들. 켜진 것만 적는 것(비밀번호, 쪽지 알림, 참고 자료)과 늘 적는 것이 있다 */
export function tableFacts(table: TableSummary, modelName: string | null): string[] {
  const facts = [
    ratingBadge(table.rating),
    table.has_password ? '비밀번호' : null,
    `문체 ${narrationStyleLabel(table.narration_style)}`,
    `라운드 ${durationLabel(table.round_time_limit)}`,
    modelName ? `모델 ${modelName}` : null,
    `크레딧 기다림 ${durationLabel(table.credit_wait_seconds)}${table.remove_short_payers ? '' : '(빼지 않음)'}`,
    table.whisper_notice ? '쪽지 알림' : null,
    table.references_enabled ? '참고 자료' : null,
  ];
  return facts.filter((fact): fact is string => fact !== null);
}

/** 모델의 이름표를 보일 이름으로. 목록에 없으면(팔지 않음, 읽지 못함) 이름표 그대로 */
function useModelName(slug: string | null): string | null {
  const models = useQuery(narrationModelsQuery());
  if (!slug) return null;
  return models.data?.models.find((model) => model.slug === slug)?.display_name ?? slug;
}
