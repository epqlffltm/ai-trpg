// web/apps/web/src/pages/trpg/room/character/PregenPicker.tsx
// 프리젠 고르기. 이름, 설명, 받는 숫자를 보이고, 남이 가져간 것과 이 테이블에서 죽은 것은 막는다.
// 막는 것은 안내다. 그 사이 남이 가져가면 서버가 409 pregen_taken 으로 거절한다.

import { Radio } from '@ai-trpg/ui';
import type { TableDetail } from '../../../../api/types';
import { pregenAvailable } from './characterForm';
import { SheetStats } from './SheetStats';

type Props = {
  table: TableDetail;
  myId: string;
  selected: number | null;
  onSelect: (index: number) => void;
  error?: string | undefined;
};

export function PregenPicker({ table, myId, selected, onSelect, error }: Props) {
  if (table.pregens.length === 0) return <p className="hint">이 시나리오에는 프리젠이 없습니다.</p>;
  return (
    <fieldset className="choice-list">
      <legend>프리젠</legend>
      {table.pregens.map((pregen, index) => (
        <Radio
          key={index}
          name="pregen_index"
          label={pregen.name}
          description={
            <div className="pregen-choice">
              {pregen.description ? <span className="prose">{pregen.description}</span> : null}
              <SheetStats rules={table.rules} abilities={pregen.sheet.abilities} maxHp={pregen.sheet.max_hp} />
              <PregenState pregen={pregen} myId={myId} />
            </div>
          }
          checked={selected === index}
          disabled={!pregenAvailable(pregen, myId)}
          onChange={() => onSelect(index)}
        />
      ))}
      {error ? <p className="ui-field__error">{error}</p> : null}
    </fieldset>
  );
}

function PregenState({ pregen, myId }: { pregen: TableDetail['pregens'][number]; myId: string }) {
  if (pregen.dead) return <span className="hint">이 테이블에서 죽은 캐릭터입니다.</span>;
  if (pregen.taken_by === myId) return <span className="hint">지금 내 캐릭터입니다.</span>;
  if (pregen.taken_by !== null) return <span className="hint">다른 사람이 골랐습니다.</span>;
  return null;
}
