# shared/server-core/src/server_core/__init__.py

"""
FastAPI 서버들이 함께 쓰는 공통부(docs/architecture/shared-code.md 의 "서버의 공통부").

토큰 검증(auth), 관측(observability), 서버끼리의 서명(service_auth), DB 연결(database), 뒤에서 도는 일의 틀(loops),
설정의 공통 칸(settings)이다. 서버의 모듈(app.*)을 가져오지 않는다(tests/test_boundary.py).
서버는 설정 값, 주입, 정해 둔 자리로만 바꿔 쓴다. 상속해 덮어쓰거나 복사해 고치지 않는다.
"""
