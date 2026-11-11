# shared/catalog-core/tests/test_errors.py

"""
모델 목록의 일이 거절되는 까닭(catalog_core/errors.py). 까닭마다 보일 말이 있고, 오류가 이름표와 까닭을 싣는다.
"""

from catalog_core.errors import CONFLICT_MESSAGES, CatalogConflictError, Conflict, ModelNotFoundError


def test_every_conflict_has_a_message():
    assert set(CONFLICT_MESSAGES) == set(Conflict)


def test_a_conflict_carries_the_slug_and_the_reason():
    error = CatalogConflictError('luna', Conflict.RETIRED)

    assert (error.slug, error.reason) == ('luna', Conflict.RETIRED)
    assert str(error) == 'luna: 은퇴한 모델이다'


def test_a_missing_model_carries_the_slug():
    error = ModelNotFoundError('nova')

    assert error.slug == 'nova'
    assert str(error) == 'nova: 그런 모델이 없다'
