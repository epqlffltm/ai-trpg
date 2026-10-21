# shared/server-core/src/server_core/testing/__init__.py

"""
서버들의 테스트가 함께 쓰는 도구. 가짜 인증 서버(tokens), span 과 메트릭을 메모리에 모으는 것(spans, metrics),
가짜 수집기(collector), 로그를 서버가 내보내는 모양으로 읽는 것(logs).

운영 코드는 이것을 가져오지 않는다(tests/test_boundary.py). pytest 에 기대지 않는다.
"""
