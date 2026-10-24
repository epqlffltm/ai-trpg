// web/apps/web/src/pages/guardian/useLinkToken.ts
// 보호자의 링크가 여는 화면에서 # 뒤의 글자를 처음 그릴 때 한 번 읽어 두고 주소에서 지운다.
// 방문 기록이나 화면 공유에 글자가 남지 않게 한다(재설정 링크의 화면과 같다).

import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { parseGuardianLink } from './guardianLink';

export function useLinkToken(): string | null {
  const location = useLocation();
  const navigate = useNavigate();
  const [token] = useState(() => parseGuardianLink(location.hash));

  useEffect(() => {
    if (location.hash) void navigate({ pathname: location.pathname }, { replace: true });
  }, [location.hash, location.pathname, navigate]);

  return token;
}
