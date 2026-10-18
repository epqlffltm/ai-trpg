# game-server/app/notifications/__init__.py

"""
사람에게 보내는 알림을 알림 서버에 넣는다(#385).

알림을 정하는 일(무엇을, 누구에게)은 그 일을 한 곳이 한다. 이 모듈은 발송함에 적고, 뒤에서 알림 서버에 보낸다.
알림 서버를 부르는 동안 테이블을 잠그지 않고, 알림 서버가 죽어 있어도 게임의 일은 멈추지 않는다.

  - models.py, repository.py: 발송함(outgoing_notifications). 보낼 알림 한 줄씩
  - outbox.py: 발송함에 적는 것. 테이블의 이벤트를 방장에게 알리는 것도 여기 있다
  - client.py: 알림 서버를 부르는 것. 요청에 서명한다(결제 서버와 같은 모양, app/billing/signing.py)
  - dispatcher.py: 몇 초마다 보낼 차례가 된 알림을 보내는 작업
  - setup.py: 설정(NOTIFICATION_URL)으로 알림 서버를 부르는 것을 만든다. 비우면 적기만 한다
"""
