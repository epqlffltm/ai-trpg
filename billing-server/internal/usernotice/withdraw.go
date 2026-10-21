// billing-server/internal/usernotice/withdraw.go

package usernotice

import (
	"context"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/usernotice/usernoticedb"
)

// CancelFor 는 그 사용자에게 아직 보내지 않은 알림을 보내지 않기로 한다(탈퇴, #603). 그렇게 한 수를 돌려준다.
//
// 줄은 지우지 않고 expired 로 둔다. 지우면 다음 바퀴의 적기가 거슬러 보는 기간(LookBack) 안의 결제와 환영 크레딧을 다시 찾아 적는다.
// 다른 끝난 것처럼 Retention(30일)이 지나면 지워진다. 알림 서버에 이미 보낸 것은 알림 서버가 지운다(그 서버의 탈퇴).
// 보내는 중이던 것(임대한 것)은 막지 못한다. 보낸 뒤 결과를 적을 때 pending 이 아니라 그대로 둔다.
func (s *Service) CancelFor(ctx context.Context, userID uuid.UUID) (int64, error) {
	return usernoticedb.New(s.pool).CancelUserNotices(ctx, userID)
}
