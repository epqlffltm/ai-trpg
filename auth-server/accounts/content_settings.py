# auth-server/accounts/content_settings.py

"""
목록을 거르는 내 설정(#986, #987). 성인 작품을 목록에 보일지와 성향(남성향, 여성향)이다.

인증 서버가 가지는 까닭: 여러 서비스(TRPG, chat, story)의 화면이 함께 읽고, 기기를 바꿔도 같아야 한다.
목록을 내는 서버(trpg-server, asset-server)는 이 값을 모른다.
실행 중에 인증 서버를 부르지 않는다(공용 코드 규칙의 원칙 2).
화면이 /me 에서 읽어 공개 목록을 부를 때 거르는 값으로 싣는다. 이미 연 대화와 테이블에는 미치지 않는다(목록만).

성인 작품을 "볼 수 있는지"는 본인인증(토큰의 adult_content)이 정한다. 이 설정은 볼 수 있는 사람이 목록에서 숨길지다.
볼 수 없는 사람이 켜는 것은 막는다. 켜도 목록 서버가 어차피 숨기지만, 켠 것처럼 보이는 상태를 남기지 않는다.
"""

from accounts.age import korean_today
from accounts.identity_status import identity_status_of
from accounts.models import User


class AdultContentRequiredError(Exception):
    """성인 확인을 하지 않은 계정이 성인 작품 표시를 켜려 했다."""


def update_content_settings(user: User, *, show_adult_content: bool | None, orientation: str | None) -> User:
    """보낸 것만 바꾼다. 성인 확인 전에 성인 작품 표시를 켜면 AdultContentRequiredError 다."""
    if show_adult_content and not identity_status_of(user, korean_today()).adult_content:
        raise AdultContentRequiredError
    fields = []
    if show_adult_content is not None:
        user.show_adult_content = show_adult_content
        fields.append('show_adult_content')
    if orientation is not None:
        user.orientation = orientation
        fields.append('orientation')
    if fields:
        user.save(update_fields=fields)
    return user


def content_settings_of(user: User) -> dict:
    """응답에 싣는 설정."""
    return {'show_adult_content': user.show_adult_content, 'orientation': user.orientation}
