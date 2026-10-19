# trpg-server/tests/test_shared_engine.py

"""
테스트가 DB 연결의 풀(엔진)을 함께 쓰는지 본다(#223).

테스트마다 풀을 새로 만들면 전체 한 번에 연결을 수천 번 새로 맺는다. Windows 의 Docker 에서 그 왕복이 가끔 막혀
테스트가 흩어져 실패했다. 함께 쓰는 것이 깨지면 테스트는 그대로 통과하지만 그 실패가 돌아온다. 그래서 따로 본다.
"""

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.main import create_app
from tests.conftest import make_test_settings


def test_the_app_of_a_test_uses_the_shared_pool(app: FastAPI, engine: AsyncEngine):
    assert app.state.engine is engine


def test_an_app_makes_its_own_pool_unless_given_one(engine: AsyncEngine):
    given = create_app(make_test_settings(), engine=engine)
    own = create_app(make_test_settings())

    # 서버로 뜰 때는 설정으로 자기 풀을 만든다. 만드는 것만으로는 DB 에 연결하지 않는다
    assert given.state.engine is engine
    assert own.state.engine is not engine
    # 받은 풀로 세션을 찍어 낸다
    assert given.state.session_factory.kw['bind'] is engine
