// web/apps/web/src/pages/trpg/room/character/CharacterPanel.tsx
// 대기실의 "내 캐릭터"(B5). 정하지 않았으면 입력을, 정했으면 요약과 "바꾸기"를 보인다.
// 모집 중에만 바꿀 수 있다. 진행 중에 죽은 뒤 새 캐릭터를 들이는 것과 보관함은 다음이다.

import { Button } from '@ai-trpg/ui';
import { useState } from 'react';
import type { TableDetail, TableMember } from '../../../../api/types';
import { characterModeLabel } from '../../labels';
import { CharacterForm } from './CharacterForm';
import { maxHpPreview } from './characterForm';
import { SheetStats } from './SheetStats';

export function CharacterPanel({ table, member }: { table: TableDetail; member: TableMember }) {
  const [editing, setEditing] = useState(false);
  const hasCharacter = member.character !== null;
  return (
    <section className="character-panel" aria-labelledby="character-heading">
      <h3 id="character-heading" className="waiting-room__label">
        내 캐릭터
      </h3>
      {hasCharacter && !editing ? (
        <CharacterSummary table={table} member={member} onEdit={() => setEditing(true)} />
      ) : (
        <CharacterForm
          table={table}
          member={member}
          onDone={() => setEditing(false)}
          onCancel={hasCharacter ? () => setEditing(false) : undefined}
        />
      )}
    </section>
  );
}

function CharacterSummary({ table, member, onEdit }: { table: TableDetail; member: TableMember; onEdit: () => void }) {
  const numbers = startingNumbers(table, member);
  return (
    <div className="pregen character-summary">
      <p className="pregen__name">{member.character?.name}</p>
      {member.character?.description ? (
        <p className="pregen__description prose">{member.character.description}</p>
      ) : null}
      {numbers ? (
        <SheetStats rules={table.rules} abilities={numbers.abilities} maxHp={numbers.maxHp} estimated={numbers.estimated} />
      ) : null}
      <p className="hint">
        {member.character_mode ? `${characterModeLabel(member.character_mode)} · ` : ''}시작하면 이 숫자로 시트를 받습니다.
      </p>
      <Button variant="secondary" onClick={onEdit}>
        바꾸기
      </Button>
    </div>
  );
}

type Numbers = { abilities: Record<string, number>; maxHp: number | null; estimated: boolean };

/** 시작할 때 받을 숫자. 프리젠은 그 시트, 직접 쓰기는 기본 시트, 능력치를 정했으면 그 점수와 최대 HP 의 어림 */
export function startingNumbers(table: TableDetail, member: TableMember): Numbers | null {
  if (member.character_mode === 'pregen' && member.pregen_index !== null) {
    const sheet = table.pregens[member.pregen_index]?.sheet;
    return sheet ? { abilities: sheet.abilities, maxHp: sheet.max_hp, estimated: false } : null;
  }
  if (member.abilities) {
    const maxHp = maxHpPreview(table.rules, table.player_made_hp, member.abilities);
    return { abilities: member.abilities, maxHp, estimated: true };
  }
  const sheet = table.default_sheet;
  return sheet ? { abilities: sheet.abilities, maxHp: sheet.max_hp, estimated: false } : null;
}
