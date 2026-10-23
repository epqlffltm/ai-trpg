# shared/server-core/src/server_core/notifications/__init__.py

"""
사람에게 보내는 알림을 알림 서버에 넣는 발송함(outbox). 알림을 보내는 FastAPI 서버가 함께 쓴다.

알림을 정하는 일(무엇을, 누구에게)은 서버가 그 일을 한 트랜잭션에서 한다. 이 패키지는 발송함의 모양과
뒤에서 알림 서버에 보내는 작업을 준다. 알림 서버를 부르는 동안 DB 를 잡지 않고,
알림 서버가 죽어 있어도 서버의 일은 멈추지 않는다(trpg-server 의 app/notifications/ 에서 뽑았다).

  - models.py: 발송함의 칸(OutgoingNotificationColumns). 표는 서버가 자기 Base 로 만든다
  - repository.py: 발송함의 쿼리. 적기(put)와 탈퇴한 사람의 것 지우기(drop_for_user)는 서버가 제 트랜잭션에서 부른다
  - store.py: 보내는 작업이 쓰는 발송함. 부를 때마다 제 세션을 열고 저장한다
  - client.py: 알림 서버를 부르는 것. 요청에 서명한다(server_core/service_auth/signing.py)
  - dispatcher.py: 몇 초마다 보낼 차례가 된 알림을 보내는 작업
  - settings.py: 설정의 칸(NOTIFICATION_URL, NOTIFICATION_SECRET, NOTIFICATION_TIMEOUT_SECONDS)
  - setup.py: 설정으로 알림 서버를 부르는 것을 만든다. 주소를 비우면 적기만 한다

서버마다 다른 것은 알림 서버에 넣는 서버의 이름(source, 주소에 들어간다)과 알림의 종류와 내용이다.
알림의 종류는 알림 서버의 목록(notification-server/app/notifications/catalog.py)에 있어야 받는다.
"""
