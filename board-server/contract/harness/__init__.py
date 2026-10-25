# board-server/contract/harness/__init__.py

"""
게시판 서버의 계약 시험이 쓰는 도구. 서버의 코드를 가져오지 않는다.

서버는 바깥 프로세스로 띄우고(server.py) HTTP 로만 부른다. 그래서 같은 시험이 NestJS 로 쓰던 서버와
지금의 FastAPI 서버 둘 다에 돌았다(#785). 서버 밖에서 맞춰야 하는 것만 여기 있다.

  - auth.py: 인증 서버를 흉내 내는 작은 HTTP 서버(공개키 목록, 끊긴 세션의 목록)
  - tokens.py: 인증 서버가 발급하는 것과 같은 모양의 access 토큰
  - signing.py: 인증 서버가 서버끼리의 요청(탈퇴의 알림)에 하는 서명
  - database.py: 시험 사이에 DB 를 비우고, 시간이 흐른 것처럼 시각을 옮긴다(board_test 스키마)
  - server.py: 서버를 띄우고 뜰 때까지 기다린다
"""
