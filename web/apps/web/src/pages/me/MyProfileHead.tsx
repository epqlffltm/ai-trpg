// web/apps/web/src/pages/me/MyProfileHead.tsx
// 마이페이지의 맨 위 프로필(Stitch 10번). 프로필 그림 자리(닉네임의 첫 글자), 닉네임, 아이디, 성인이면 "성인 인증".
// 오른쪽에 "제작자 페이지"(제작자 탭으로)와 "회원정보 수정"(내 계정 탭으로). 가입 날짜는 서버가 주지 않아 두지 않는다.
// 계정을 읽지 못하면 제목만 둔다(계정 탭이 다시 시도를 보인다).

import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { meQuery } from '../../auth/queries';
import { myTabPath } from './myTabs';

export function MyProfileHead() {
  const me = useQuery(meQuery());
  const nickname = me.data?.nickname ?? '';
  return (
    <header className="my-head">
      <span className="my-head__avatar" aria-hidden="true">
        {nickname.slice(0, 1)}
      </span>
      <div className="my-head__info">
        <h1>{nickname || '내 정보'}</h1>
        {me.data ? (
          <p className="my-head__meta">
            <span className="my-head__handle">@{me.data.username}</span>
            {me.data.identity.legal_adult ? <span className="badge my-head__adult">성인 인증</span> : null}
          </p>
        ) : null}
      </div>
      <nav className="my-head__links" aria-label="프로필">
        <Link className="ui-button ui-button--secondary" to={myTabPath('creator')}>
          제작자 페이지
        </Link>
        <Link className="ui-button ui-button--primary" to={myTabPath('account')}>
          회원정보 수정
        </Link>
      </nav>
    </header>
  );
}
