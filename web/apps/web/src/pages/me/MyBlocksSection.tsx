// web/apps/web/src/pages/me/MyBlocksSection.tsx
// 마이페이지의 "차단"(#988). 막은 제작자와 태그를 보고 풀고, 태그를 더한다. 제작자는 제작자 페이지의 "차단하기"로 막는다.
// 막은 제작자의 작품과 막은 태그가 붙은 작품은 공개 목록, 검색, 랭킹, 배너에서 빠진다. 소개를 직접 열면 보인다.
// 제작자의 이름은 인증 서버에 공개 ID 로 묻는다. 탈퇴한 제작자는 인증 서버가 막은 것을 지운다.

import { Button, TextField } from '@ai-trpg/ui';
import { useState } from 'react';
import { Link } from 'react-router';
import { BLOCKED_TAG_MAX_LENGTH, MAX_BLOCKED_CREATORS, MAX_BLOCKED_TAGS } from '../../api/blocks';
import { useBlocks, type BlockActions } from '../../hooks/useBlocks';
import { usePublicNames } from '../../hooks/usePublicNames';

export function MyBlocksSection() {
  const actions = useBlocks();
  return (
    <section className="page-section" aria-labelledby="my-blocks-heading">
      <h2 id="my-blocks-heading">차단</h2>
      <p className="hint">막은 제작자의 작품과 막은 태그가 붙은 작품은 목록, 검색, 랭킹, 배너에서 빠집니다.</p>
      <BlockedCreators actions={actions} />
      <BlockedTags actions={actions} />
      {actions.failure ? <p role="alert">{actions.failure}</p> : null}
    </section>
  );
}

function BlockedCreators({ actions }: { actions: BlockActions }) {
  const { creators } = actions.blocks;
  const nameOf = usePublicNames([creators]);
  return (
    <>
      <h3>
        막은 제작자 {creators.length}/{MAX_BLOCKED_CREATORS}
      </h3>
      {creators.length === 0 ? (
        <p className="hint">없습니다. 제작자 페이지에서 "차단하기"를 누르면 여기에 들어옵니다.</p>
      ) : (
        <ul>
          {creators.map((publicId) => (
            <li key={publicId}>
              <Link to={`/creators/${encodeURIComponent(publicId)}`}>{nameOf(publicId) ?? '이름을 읽는 중'}</Link>{' '}
              <Button variant="quiet" disabled={actions.busy} onClick={() => void actions.setCreator(publicId, false)}>
                풀기
              </Button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function BlockedTags({ actions }: { actions: BlockActions }) {
  const { tags } = actions.blocks;
  const [draft, setDraft] = useState('');
  const tag = draft.trim();

  async function add() {
    await actions.setTag(tag, true);
    setDraft('');
  }

  return (
    <>
      <h3>
        막은 태그 {tags.length}/{MAX_BLOCKED_TAGS}
      </h3>
      {tags.length === 0 ? <p className="hint">없습니다.</p> : null}
      <ul>
        {tags.map((blocked) => (
          <li key={blocked}>
            #{blocked}{' '}
            <Button variant="quiet" disabled={actions.busy} onClick={() => void actions.setTag(blocked, false)}>
              풀기
            </Button>
          </li>
        ))}
      </ul>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void add();
        }}
      >
        <TextField label="막을 태그" value={draft} maxLength={BLOCKED_TAG_MAX_LENGTH} onChange={(event) => setDraft(event.target.value)} />
        <Button type="submit" variant="secondary" disabled={actions.busy || tag === ''}>
          태그 막기
        </Button>
      </form>
    </>
  );
}
