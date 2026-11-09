# auth-server/accounts/migrations/0039_inquiry_kinds.py

"""
문의(support 앱)가 쓰는 종류 둘을 더한다. 메일의 종류 inquiry_reply(답 메일), 보안 이벤트 inquiry_ip_limited(문의의 IP 시도 제한).
선택지만 바뀌어 DB 의 표는 그대로다.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0038_user_badges"),
    ]

    operations = [
        migrations.AlterField(
            model_name="outgoingmail",
            name="kind",
            field=models.CharField(
                choices=[
                    ("signup_code", "가입 인증 코드"),
                    ("login_code", "로그인 인증 코드"),
                    ("already_registered", "이미 가입된 이메일"),
                    ("password_reset", "비밀번호 재설정"),
                    ("password_changed", "비밀번호 변경 알림"),
                    ("security_digest", "보안 이벤트 요약"),
                    ("guardian_consent", "보호자 동의 요청"),
                    ("guardian_consented", "보호자 동의 확인"),
                    ("guardian_revoked", "보호자 동의 철회 확인"),
                    ("minor_guardian", "미성년자에게 보호자 동의 알림"),
                    ("guardian_payment", "보호자에게 결제 알림"),
                    ("payment_receipt", "결제한 본인에게 결제 확인"),
                    ("refund_receipt", "결제한 본인에게 청약철회 확인"),
                    ("withdrawal_requested", "탈퇴 요청 확인"),
                    ("withdrawal_reminder", "탈퇴 하루 전 알림"),
                    ("withdrawal_completed", "탈퇴를 마침"),
                    ("signup_refused", "가입을 받지 않는 이메일"),
                    ("inquiry_reply", "문의의 답"),
                    ("other", "그 밖"),
                ],
                default="other",
                max_length=40,
                verbose_name="종류",
            ),
        ),
        migrations.AlterField(
            model_name="securityevent",
            name="kind",
            field=models.CharField(
                choices=[
                    ("login_ip_limited", "로그인: IP 시도 제한"),
                    ("login_failures_limited", "로그인: 비밀번호 틀림 제한"),
                    (
                        "reserved_username_login",
                        "로그인: 예약어 아이디로 시도해 IP 차단",
                    ),
                    ("signup_ip_limited", "가입: IP 시도 제한"),
                    ("signup_resend_ip_limited", "가입 코드 재전송: IP 시도 제한"),
                    ("password_reset_ip_limited", "비밀번호 재설정: IP 시도 제한"),
                    (
                        "password_change_failures_limited",
                        "비밀번호 변경: 현재 비밀번호 틀림 제한",
                    ),
                    ("mail_discarded", "메일: 보내지 못하고 버림"),
                    ("account_suspended", "계정: 정지"),
                    ("account_restored", "계정: 정지를 풂"),
                    ("identity_under_age", "본인인증: 만 14세 미만이라 계정을 막음"),
                    ("identity_in_use", "본인인증: 다른 계정에서 인증한 사람"),
                    ("withdrawal_requested", "탈퇴: 요청"),
                    ("account_withdrawn", "탈퇴: 계정을 비움"),
                    ("return_blocked", "재가입: 정지된 채 탈퇴한 사람을 막음"),
                    ("inquiry_ip_limited", "문의: IP 시도 제한"),
                ],
                max_length=40,
                verbose_name="종류",
            ),
        ),
    ]
