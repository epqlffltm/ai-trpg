# game-server/app/catalog/errors.py

"""
모델 목록의 일이 거절되는 까닭들. 서비스가 던지고, 부른 쪽(관리 명령, 나중의 관리 API)이 알맞게 보인다.

  - ModelNotFoundError: 그런 이름표의 모델이 없다.
  - CatalogConflictError: 요청은 맞지만 목록의 지금 상태와 부딪힌다. 까닭은 Conflict 다.
  - InvalidModelError: 바꾸려는 값이 그 모델에 맞지 않는다(창구에 맞지 않는 출력 상한의 칸).
"""

import enum


class ModelNotFoundError(Exception):
    """그런 이름표의 모델이 없다."""

    def __init__(self, slug: str) -> None:
        super().__init__(f'{slug}: 그런 모델이 없다')
        self.slug = slug


class Conflict(enum.StrEnum):
    """요청은 맞지만 목록의 지금 상태와 부딪히는 이유."""

    # 그 이름표를 이미 쓴다
    SLUG_TAKEN = 'slug_taken'
    # 같은 창구의 같은 API 모델을 다른 이름표로 이미 넣었다
    API_MODEL_TAKEN = 'api_model_taken'
    # 켜려는데 그날의 원가 단가가 없다. 원가를 모르면 판매가가 맞는지 볼 수 없다
    NO_COST = 'no_cost'
    # 은퇴한 모델은 켜지 않는다
    RETIRED = 'retired'


CONFLICT_MESSAGES = {
    Conflict.SLUG_TAKEN: '그 이름표를 이미 쓴다',
    Conflict.API_MODEL_TAKEN: '같은 창구의 같은 API 모델을 이미 넣었다',
    Conflict.NO_COST: '오늘의 원가 단가가 없다. set-cost 로 먼저 적는다',
    Conflict.RETIRED: '은퇴한 모델이다',
}


class CatalogConflictError(Exception):
    """요청은 맞지만 목록의 지금 상태와 부딪힌다."""

    def __init__(self, slug: str, reason: Conflict) -> None:
        super().__init__(f'{slug}: {CONFLICT_MESSAGES[reason]}')
        self.slug = slug
        self.reason = reason


class InvalidModelError(Exception):
    """바꾸려는 값이 그 모델에 맞지 않는다."""
