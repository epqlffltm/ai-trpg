# auth-server/accounts/mail.py

"""
accounts 앱이 보내는 메일.

메일의 문구와 발송만 맡는다. 코드를 만들거나 검증하지 않는다(email_codes.py).
"""

from django.core.mail import send_mail

from accounts.email_codes import CODE_LIFETIME
from accounts.models import EmailCodePurpose, User

# 용도별 메일 제목과 안내 문구
EMAIL_CODE_MESSAGES = {
    EmailCodePurpose.SIGNUP: ('가입 인증 코드', '회원가입을 마치려면 아래 코드를 입력해 주세요.'),
    EmailCodePurpose.LOGIN: ('로그인 인증 코드', '로그인을 마치려면 아래 코드를 입력해 주세요.'),
    EmailCodePurpose.PASSWORD_RESET: (
        '비밀번호 재설정 코드',
        '비밀번호를 다시 설정하려면 아래 코드를 입력해 주세요.',
    ),
}


def build_email_code_message(*, purpose: str, code: str) -> tuple[str, str]:
    """인증 코드 메일의 제목과 본문을 만든다."""
    title, guide = EMAIL_CODE_MESSAGES[EmailCodePurpose(purpose)]
    minutes = int(CODE_LIFETIME.total_seconds() // 60)
    body = (
        f'{guide}\n\n'
        f'    {code}\n\n'
        f'이 코드는 {minutes}분 동안만 쓸 수 있습니다.\n'
        '요청한 적이 없다면 이 메일을 무시해 주세요. 코드를 다른 사람에게 알려 주지 마세요.'
    )
    return f'[AI TRPG] {title}', body


def send_email_code(*, user: User, purpose: str, code: str) -> None:
    """
    회원의 이메일로 인증 코드를 보낸다.

    보내는 주소는 settings 의 DEFAULT_FROM_EMAIL 이다.
    개발 환경에서는 실제로 보내지 않고 서버를 띄운 터미널에 출력한다.
    """
    subject, body = build_email_code_message(purpose=purpose, code=code)
    send_mail(
        subject=subject,
        message=body,
        from_email=None,
        recipient_list=[user.email],
    )
    
def send_already_registered_notice(*, user: User) -> None:
    """
    이미 가입된 이메일로 누군가 가입을 시도했음을 그 주소의 주인에게 알린다.

    가입 화면에서는 이 사실을 알려 주지 않는다. 화면에 알리면 누구나
    특정 이메일의 가입 여부를 확인할 수 있게 된다. 메일은 주소의 주인만 본다.
    """
    send_mail(
        subject='[AI TRPG] 이미 가입된 이메일입니다',
        message=(
            '이 이메일 주소로 회원가입 요청이 들어왔습니다.\n'
            '이 주소는 이미 가입되어 있어 새 계정을 만들지 않았습니다.\n\n'
            '본인이 요청했다면 기존 계정으로 로그인해 주세요.\n'
            '요청한 적이 없다면 이 메일을 무시해 주세요. 계정에는 아무 변화가 없습니다.'
        ),
        from_email=None,
        recipient_list=[user.email],
    )