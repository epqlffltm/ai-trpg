// web/apps/web/src/pages/trpg/room/round/action/AidSelect.tsx
// 행동에 붙여 쓸 물건(#277, #802, 거들기)의 칸. 치료, 따기, 고치기, 부수기, 넘기가 함께 쓴다.
// 지닌 것 가운데 그 행동을 거드는 물건만 보인다(actionOptions.ts 의 aidItems). 없으면 칸을 두지 않는다.
// 다른 종류에서 고른 물건이 남아 있을 수 있어, 거드는 물건이 아니면 비운 것으로 보인다(보낼 때도 빠진다, actionDraft.ts).

import { aidItems, type ActionContext } from './actionOptions';
import { ChoiceSelect } from './ChoiceSelect';

type Props = {
  act: 'treat' | 'pick' | 'repair' | 'force' | 'cross';
  value: string;
  ctx: ActionContext;
  onChange: (item: string) => void;
  /** 도구가 있어야 하는 문이면 참. 비워 둘 수 없다고 알린다 */
  required?: boolean;
};

const HINT = '그 판정에 보정이 더해집니다. 굴린 뒤 물건에 적힌 대로 없어지거나 부러집니다.';

export function AidSelect({ act, value, ctx, onChange, required = false }: Props) {
  const aids = aidItems(ctx, act);
  if (aids.length === 0) return required ? <p className="hint">이 문은 도구가 있어야 합니다. 거들 물건을 지니고 있지 않습니다.</p> : null;
  return (
    <ChoiceSelect
      label={required ? '쓸 도구' : '붙여 쓸 물건(선택)'}
      value={aids.some((choice) => choice.value === value) ? value : ''}
      choices={aids}
      empty={required ? '고르기' : '쓰지 않음'}
      hint={required ? `이 문은 도구가 있어야 합니다. ${HINT}` : HINT}
      onChange={onChange}
    />
  );
}
