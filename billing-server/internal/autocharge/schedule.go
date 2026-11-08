// billing-server/internal/autocharge/schedule.go

package autocharge

import (
	"context"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgtype"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/autocharge/autochargedb"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/catalog"
)

// 날짜 기준(#1167). 매달 정한 날(한국 날짜의 1~28일)에 정한 상품을 산다.
// 결제 작업이 한 바퀴를 돌 때마다 먼저 부른다(ChargeRound). 오늘이 그날인 사람마다 충전할 일을 적고, 그 바퀴에서 결제한다.
//
//   - 그날 한 번만 산다. 일에 그날(charge_date)을 적고, 한 사람에게 한 날의 일은 하나다(색인 auto_charge_requests_one_per_day).
//     결제 작업이 멈췄다 다시 떠도, 둘이 함께 돌아도, 그날 다시 켜도 다시 적지 않는다. 끝난 일(거절, 그만둠)도 그날은 센다
//   - 그날 안에만 산다. 결제 작업이 그날 내내 멈춰 있었으면 그 달은 건너뛴다(2026-11-08 결정). 다음 날 적지 않고,
//     그날 적었지만 보내지 못한 일은 다음 날 보내지 않는다(prepare 의 stale). 며칠 늦게 사서 사용자가 놀라지 않게 한다
//   - 켠 날이 그날이면 그날 산다. 그날 이미 산 사람이 날을 바꿔도 그달에 한 번 더 살 수 있다. 한 달 상한이 막는다
//   - 끝나지 않은 일(잔액 기준에서 바꾸기 전의 것)이 있으면 그 일이 끝난 뒤의 바퀴에서 적는다
//   - 상품의 값은 적는 때의 목록에서 옮겨 적는다. 목록에서 없어진 상품이면 적지 않는다(잔액 기준과 같다)

// QueueScheduled 는 오늘(now 의 한국 날짜)이 그날인 날짜 기준의 설정마다 충전할 일을 limit 개까지 적고, 적은 수를 돌려준다.
func (s *Service) QueueScheduled(ctx context.Context, now time.Time, limit int) (int, error) {
	queries := autochargedb.New(s.pool)
	today := KoreaDate(now)
	due, err := queries.ListScheduledDue(ctx, autochargedb.ListScheduledDueParams{
		Day: int16(today.Day()), ChargeDate: pgdateOf(today), RowLimit: int32(limit),
	})
	if err != nil {
		return 0, err
	}
	queued := 0
	for _, row := range due {
		inserted, err := queueScheduled(ctx, queries, row, today, now)
		if err != nil {
			return queued, err
		}
		if inserted {
			queued++
		}
	}
	return queued, nil
}

// queueScheduled 는 한 사람의 그날의 일을 적는다. 그날의 일이나 끝나지 않은 일이 이미 있으면 적지 않는다(false).
func queueScheduled(ctx context.Context, queries *autochargedb.Queries, row autochargedb.ListScheduledDueRow, today time.Time, now time.Time) (bool, error) {
	product, ok := catalog.Find(row.ProductID)
	if !ok {
		return false, nil
	}
	inserted, err := queries.InsertScheduledRequest(ctx, autochargedb.InsertScheduledRequestParams{
		ID: uuid.New(), UserID: row.UserID, ProductID: product.ID, Price: product.Price, Credits: product.Credits,
		ChargeDate: pgdateOf(today), Now: now,
	})
	return inserted > 0, err
}

// KoreaDate 는 그 시각의 한국 날짜다. 시각은 0 시이고 시간대는 UTC 다(DB 의 DATE 와 같은 값이 되게).
func KoreaDate(at time.Time) time.Time {
	local := at.In(korea)
	return time.Date(local.Year(), local.Month(), local.Day(), 0, 0, 0, 0, time.UTC)
}

// PastChargeDate 는 날짜 기준의 일을 그날(chargeDate, KoreaDate 의 값)이 지나 지금은 보내지 않는지다.
func PastChargeDate(chargeDate time.Time, now time.Time) bool {
	return KoreaDate(now).After(chargeDate)
}

// pastScheduledDay 는 그 일이 날짜 기준의 일이고 그날이 지났는지다. 잔액 기준의 일은 false 다.
func pastScheduledDay(request autochargedb.AutoChargeRequest, now time.Time) bool {
	return request.ChargeDate.Valid && PastChargeDate(request.ChargeDate.Time, now)
}

// requestMode 는 그 일을 적은 방식이다. 그날이 적힌 일은 날짜 기준이다.
func requestMode(request autochargedb.AutoChargeRequest) Mode {
	if request.ChargeDate.Valid {
		return ModeDate
	}
	return ModeBalance
}

// pgdateOf 는 날짜를 DB 의 날짜로 바꾼다.
func pgdateOf(day time.Time) pgtype.Date {
	return pgtype.Date{Time: day, Valid: true}
}
