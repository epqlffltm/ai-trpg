# game-server/app/assets/ratings.py

"""
이용 등급을 가르는 곳(#59, #390). 누가 어느 등급을 보고 쓸 수 있는지는 여기서만 정한다.

공개 목록, 로비, 테이블 만들기와 들어오기, 시나리오 쓰기와 공개가 모두 이것을 부른다.
토큰의 값(app/auth/tokens.py 의 AccessClaims)만 보고 DB 를 모른다.
"""

from collections.abc import Sequence

from app.assets.models import Rating
from app.auth.tokens import AccessClaims


class AdultContentRequiredError(Exception):
    """
    성인용인데 성인용 내용을 볼 수 없는 사람이다(#59, #390). 403 이다.

    그것이 있다는 것을 이미 아는 경우에만 던진다. 자기 시나리오를 쓰거나 공개하는 사람, 초대 코드를 받은 사람,
    자기 시나리오로 테이블을 만드는 사람이다. 공개 목록과 로비에서는 던지지 않는다. 그쪽에서는 없는 것으로 보인다.
    """


# 등급을 받지 않고 부른 쓰기가 쓸 수 있는 등급.
# 토큰을 거치지 않은 호출(테스트, 서버 안의 작업)이 성인용을 쓰는 일이 없게
ALL_AGES_ONLY: tuple[Rating, ...] = (Rating.ALL,)


def allowed_ratings(viewer: AccessClaims) -> list[Rating]:
    """
    이 사람이 보고 쓸 수 있는 등급. 등급을 가르는 곳은 이 함수 하나다(#59, #390).

    토큰이 성인용 내용을 볼 수 있다고 하거나(adult_content) 운영자면 전체 이용가와 성인용, 아니면 전체 이용가만이다.
    목록, 상세, 로비, 테이블 만들기와 들어오기, 시나리오 쓰기와 공개가 모두 이것을 본다. 들어온 뒤에는 다시 보지 않는다.
    인증 서버가 생년월일로 정하는 값이라, 한 번 볼 수 있게 되면 그 뒤로 계속 볼 수 있기 때문이다.
    """
    if viewer.adult_content or viewer.is_operator:
        return [Rating.ALL, Rating.ADULT]
    return [Rating.ALL]


def require_rating(rating: str, allowed: Sequence[Rating]) -> None:
    """그 등급이 allowed 에 없으면 AdultContentRequiredError. allowed 는 allowed_ratings 의 답이다."""
    if rating not in allowed:
        raise AdultContentRequiredError
