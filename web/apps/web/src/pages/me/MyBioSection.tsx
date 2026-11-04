// web/apps/web/src/pages/me/MyBioSection.tsx
// 마이페이지의 "제작자 소개"(#992). 제작자 페이지에 보일 소개 글을 고친다(200자까지, 비우면 소개가 없다).
// 표시 이름은 닉네임 그대로다. 저장하면 답을 내 정보에 넣고, 내 제작자 페이지로 가는 길을 둔다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import { BIO_MAX_LENGTH, updateMyProfile } from '../../api/creators';
import type { Me } from '../../api/types';
import { meQuery } from '../../auth/queries';
import { TextAreaField } from '../../components/TextAreaField';
import { putQueryData } from '../../queryClient';

type SaveState = 'idle' | 'saving' | 'saved' | 'failed';

export function MyBioSection() {
  const me = useQuery(meQuery());
  if (!me.data) return null;
  return <BioForm key={me.data.public_id} me={me.data} />;
}

function BioForm({ me }: { me: Me }) {
  const queryClient = useQueryClient();
  const [bio, setBio] = useState(me.bio ?? '');
  const [state, setState] = useState<SaveState>('idle');

  async function save() {
    setState('saving');
    try {
      const saved = await updateMyProfile({ bio });
      setBio(saved.bio);
      await putQueryData<Me>(queryClient, meQuery().queryKey, (current) => (current ? { ...current, bio: saved.bio } : current));
      await queryClient.invalidateQueries({ queryKey: ['auth', 'creators', me.public_id] });
      setState('saved');
    } catch {
      setState('failed');
    }
  }

  return (
    <section className="page-section" aria-labelledby="my-bio-heading">
      <h2 id="my-bio-heading">제작자 소개</h2>
      <p className="hint">
        작품의 "만든 사람"을 누르면 보이는 <Link to={`/creators/${me.public_id}`}>내 제작자 페이지</Link>에 나옵니다. 이름은 닉네임이 보입니다.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <TextAreaField
          label="소개"
          value={bio}
          maxLength={BIO_MAX_LENGTH}
          rows={3}
          hint={`${bio.length}/${BIO_MAX_LENGTH}자. 비우면 소개가 없습니다.`}
          onChange={(event) => {
            setBio(event.target.value);
            setState('idle');
          }}
        />
        {state === 'failed' ? <Notice tone="error">저장하지 못했습니다. 잠시 뒤에 다시 해 보세요.</Notice> : null}
        {state === 'saved' ? <p role="status">저장했습니다.</p> : null}
        <Button type="submit" disabled={state === 'saving'}>
          저장
        </Button>
      </form>
    </section>
  );
}
