// billing-server/internal/eligibility/eligibility.go

// Package eligibility 는 결제 자격이다(#337). 누가 결제할 수 있는지를 적고 가른다.
//
// 결제할 수 있는 사람은 둘이다.
//   - 성년이다(민법: 만 19세 생일부터)
//   - 미성년자인데 보호자가 동의했다
//
// 본인인증을 하지 않은 사용자는 나이를 모르므로 결제하지 못한다.
// 이 서버는 사용자의 나이와 동의를 직접 알지 못한다. 인증 서버가 알려 준 것을 적어 두고(Apply), 결제할 때 그것만 본다(Check).
// 결제할 때 인증 서버를 부르지 않는다. 인증 서버가 죽어 있어도 결제는 멈추지 않는다.
package eligibility

import (
	"errors"
	"time"

	"github.com/google/uuid"
)

var (
	// ErrVerificationRequired 는 본인인증을 하지 않아 결제할 수 없다는 오류다.
	ErrVerificationRequired = errors.New("결제하려면 먼저 본인인증을 해야 합니다")
	// ErrGuardianConsentRequired 는 미성년자인데 보호자가 동의하지 않아 결제할 수 없다는 오류다.
	ErrGuardianConsentRequired = errors.New("만 19세 미만은 보호자가 동의해야 결제할 수 있습니다")
	// ErrInvalidUpdate 는 인증 서버가 보낸 상태가 틀렸다는 오류다(사용자가 없다, 버전이 0 이하다).
	ErrInvalidUpdate = errors.New("user_id 가 있어야 하고 version 은 1 이상이어야 합니다")
)

// korea 는 날짜를 자르는 시간대다. 사용자가 사는 곳이다. 한국은 일광 절약 시간이 없어 고정된 9시간으로 둔다.
// 시간대 데이터(tzdata)가 없는 이미지에서도 같게 돈다.
var korea = time.FixedZone("KST", 9*60*60)

// Update 는 인증 서버가 알려 준 한 사용자의 결제 자격이다.
type Update struct {
	UserID uuid.UUID
	// Version 은 인증 서버가 붙인 버전이다. 가진 것보다 높아야 받는다.
	Version int64
	// LegalAdultFrom 은 성년이 되는 날(한국 날짜, 0시 UTC 로 둔다)이다. nil 이면 이미 성년이다.
	LegalAdultFrom *time.Time
	// GuardianConsent 는 보호자가 동의했는지다.
	GuardianConsent bool
}

// Outcome 은 받은 상태를 적었는지다. 응답의 status 에 이 글자가 그대로 나간다.
type Outcome string

const (
	// Applied 는 받아 적었다는 것이다.
	Applied Outcome = "applied"
	// Stale 은 이미 같거나 높은 버전을 가지고 있어 적지 않았다는 것이다. 인증 서버에는 끝난 일이다.
	Stale Outcome = "stale"
)

// Record 는 적어 둔 한 사용자의 결제 자격이다.
type Record struct {
	LegalAdultFrom  *time.Time
	GuardianConsent bool
}

// Decide 는 적어 둔 것(record)으로 today 에 결제할 수 있는지 가른다. 없으면(nil) 본인인증 전이다. DB 를 보지 않는다.
func Decide(record *Record, today time.Time) error {
	if record == nil {
		return ErrVerificationRequired
	}
	if record.LegalAdultFrom == nil || !record.LegalAdultFrom.After(today) {
		return nil
	}
	if record.GuardianConsent {
		return nil
	}
	return ErrGuardianConsentRequired
}

// KoreanDate 는 now 의 한국 날짜를 0시 UTC 의 시각으로 돌려준다. DB 의 DATE 를 읽은 값과 같은 모양이라 바로 견줄 수 있다.
func KoreanDate(now time.Time) time.Time {
	year, month, day := now.In(korea).Date()
	return time.Date(year, month, day, 0, 0, 0, 0, time.UTC)
}

// checkUpdate 는 받은 상태의 모양을 본다.
func checkUpdate(update Update) error {
	if update.UserID == uuid.Nil || update.Version <= 0 {
		return ErrInvalidUpdate
	}
	return nil
}
