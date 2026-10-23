// web/apps/web/src/pages/trpg/studio/bestiaries/BestiaryEditPage.tsx
// 몬스터 모음 하나(B9, /trpg/studio/bestiaries/:bestiaryId). 제목과 소개를 고치고, 몬스터를 종류로 걸러 보고 더하고 고치고 지운다.

import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router';
import { deleteMonster, fetchBestiary, updateBestiary } from '../../../../api/bestiaries';
import { CollectionEditPage } from '../collection/CollectionEditPage';
import { ItemsSection } from '../collection/ItemsSection';
import { preview } from '../collection/itemsView';
import { useItemActions } from '../collection/useItemActions';
import { monstersQuery } from './bestiaryQueries';
import { MonsterForm } from './MonsterForm';
import { BESTIARY_MAX_MONSTERS, MONSTER_KINDS } from './monsterForm';

export function BestiaryEditPage() {
  const { bestiaryId = '' } = useParams();
  return (
    <CollectionEditPage kind="bestiaries" assetId={bestiaryId} load={fetchBestiary} update={(body) => updateBestiary(bestiaryId, body)}>
      <Monsters bestiaryId={bestiaryId} />
    </CollectionEditPage>
  );
}

function Monsters({ bestiaryId }: { bestiaryId: string }) {
  const monsters = useQuery(monstersQuery(bestiaryId));
  const removing = useItemActions('bestiaries', bestiaryId);
  return (
    <ItemsSection
      label="몬스터"
      max={BESTIARY_MAX_MONSTERS}
      items={monsters.data}
      pending={monsters.isPending}
      failed={monsters.isError}
      retry={() => void monsters.refetch()}
      kindLabels={MONSTER_KINDS}
      summary={(monster) => (
        <>
          {monster.unique ? <span className="hint">네임드 · </span> : null}
          {preview(monster.content)}
        </>
      )}
      form={(monster, done) => <MonsterForm bestiaryId={bestiaryId} monster={monster} done={done} />}
      remove={(monster) => removing.run(() => deleteMonster(bestiaryId, monster.id))}
      removing={removing}
    />
  );
}
