# trpg-server/app/catalog/errors.py

"""
모델 목록의 일이 거절되는 까닭들. 서비스가 던지고, 부른 쪽(관리 명령, 나중의 관리 API)이 알맞게 보인다.

  - ModelNotFoundError: 그런 이름표의 모델이 없다.
  - CatalogConflictError: 요청은 맞지만 목록의 지금 상태와 부딪힌다. 까닭은 Conflict 다.

모델 목록의 파일이 틀린 것은 여기 없다. 파일을 읽을 때 알린다(ai_core/catalog_file.py 의 CatalogFileError).
"""

import enum


class ModelNotFoundError(Exception):
    """그런 이름표의 모델이 없다."""

    def __init__(self, slug: str) -> None:
        super().__init__(f'{slug}: 그런 모델이 없다')
        self.slug = slug


class Conflict(enum.StrEnum):
    """요청은 맞지만 목록의 지금 상태와 부딪히는 이유."""

    # 같은 창구의 같은 API 모델을 다른 이름표로 이미 넣었다(파일에 없는 표의 모델이 쓴다)
    API_MODEL_TAKEN = 'api_model_taken'
    # 켜려는데 그날의 원가 단가가 없다. 원가를 모르면 판매가가 맞는지 볼 수 없다
    NO_COST = 'no_cost'
    # 은퇴한 모델은 켜지 않는다
    RETIRED = 'retired'
    # 파일의 창구가 표의 것과 다르다. 창구는 바꾸지 않는다(이름표를 새로 정한다)
    PROVIDER_CHANGED = 'provider_changed'


CONFLICT_MESSAGES = {
    Conflict.API_MODEL_TAKEN: '같은 창구의 같은 API 모델을 이미 넣었다',
    Conflict.NO_COST: '오늘의 원가 단가가 없다. 모델 목록의 파일에 단가를 적고 sync 로 들여온다',
    Conflict.RETIRED: '은퇴한 모델이다',
    Conflict.PROVIDER_CHANGED: '창구는 바꾸지 않는다. 다른 창구로 부르려면 이름표를 새로 정한다',
}


class CatalogConflictError(Exception):
    """요청은 맞지만 목록의 지금 상태와 부딪힌다."""

    def __init__(self, slug: str, reason: Conflict) -> None:
        super().__init__(f'{slug}: {CONFLICT_MESSAGES[reason]}')
        self.slug = slug
        self.reason = reason
