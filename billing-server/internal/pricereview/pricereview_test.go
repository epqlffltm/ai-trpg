// billing-server/internal/pricereview/pricereview_test.go

// 할 일을 실제 PostgreSQL 의 테스트용 스키마(billing_test)에서 시험한다.
// 스키마에는 다른 테스트가 적은 할 일도 있다. 그래서 수를 세지 않고 이 테스트가 적은 번호를 찾아 본다.
package pricereview_test

import (
	"context"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricereview"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

// startedAt 은 테스트의 시계가 가리키는 시각이다.
var startedAt = time.Date(2026, 10, 17, 4, 0, 0, 0, time.UTC)

const day = 24 * time.Hour

// clock 은 테스트가 마음대로 돌리는 시계다.
type clock struct {
	mu  sync.Mutex
	now time.Time
}

func (c *clock) Now() time.Time {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.now
}

func (c *clock) Advance(d time.Duration) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.now = c.now.Add(d)
}

// fixture 는 테스트 하나가 쓰는 것들이다.
type fixture struct {
	t       *testing.T
	clock   *clock
	service *pricereview.Service
}

func setUp(t *testing.T) fixture {
	t.Helper()
	clock := &clock{now: startedAt}
	return fixture{t: t, clock: clock, service: pricereview.NewService(testenv.Pool(t), clock.Now)}
}

func ctx(t *testing.T) context.Context {
	t.Helper()
	limited, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	t.Cleanup(cancel)
	return limited
}

// add 는 지금부터 after 뒤에 값이 바뀌는 할 일을 적는다.
func (f fixture) add(after time.Duration) pricereview.Review {
	f.t.Helper()
	added, err := f.service.Add(ctx(f.t), pricereview.Draft{Subject: "테스트 모델 단가", ChangesAt: f.clock.Now().Add(after), Note: "https://example.com/pricing", CreatedBy: "test"})
	if err != nil {
		f.t.Fatalf("할 일을 적지 못했다: %v", err)
	}
	return added
}

// dueOf 는 지금 때가 된 할 일 가운데 그 번호의 것들이다.
func (f fixture) dueOf(id int64) []pricereview.Due {
	f.t.Helper()
	due, err := f.service.Due(ctx(f.t))
	if err != nil {
		f.t.Fatalf("때가 된 할 일을 읽지 못했다: %v", err)
	}
	var mine []pricereview.Due
	for _, d := range due {
		if d.ReviewID == id {
			mine = append(mine, d)
		}
	}
	return mine
}

// listed 는 목록에서 그 번호의 할 일을 찾는다.
func (f fixture) listed(all bool, id int64) (pricereview.Review, bool) {
	f.t.Helper()
	reviews, err := f.service.List(ctx(f.t), all)
	if err != nil {
		f.t.Fatalf("목록을 읽지 못했다: %v", err)
	}
	for _, r := range reviews {
		if r.ID == id {
			return r, true
		}
	}
	return pricereview.Review{}, false
}

func TestAddKeepsWhatWasWritten(t *testing.T) {
	f := setUp(t)
	added := f.add(35 * day)

	got, found := f.listed(false, added.ID)

	if !found || got.Subject != "테스트 모델 단가" || got.Note != "https://example.com/pricing" || got.CreatedBy != "test" {
		t.Fatalf("목록의 할 일 = %+v, 찾음 = %v", got, found)
	}
	if !got.ChangesAt.Equal(startedAt.Add(35*day)) || !got.CreatedAt.Equal(startedAt) || !got.Open() {
		t.Errorf("시각이나 열림이 틀렸다: %+v", got)
	}
}

func TestAddRefusesBadDrafts(t *testing.T) {
	f := setUp(t)
	good := pricereview.Draft{Subject: "s", ChangesAt: startedAt.Add(day), CreatedBy: "test"}
	cases := map[string]struct {
		edit func(*pricereview.Draft)
		want error
	}{
		"이름이 없다":    {func(d *pricereview.Draft) { d.Subject = "" }, pricereview.ErrInvalidSubject},
		"이름이 길다":    {func(d *pricereview.Draft) { d.Subject = strings.Repeat("가", 201) }, pricereview.ErrInvalidSubject},
		"글이 길다":     {func(d *pricereview.Draft) { d.Note = strings.Repeat("a", 1001) }, pricereview.ErrInvalidNote},
		"적은 사람이 없다": {func(d *pricereview.Draft) { d.CreatedBy = "" }, pricereview.ErrMissingName},
		"이미 지났다":    {func(d *pricereview.Draft) { d.ChangesAt = startedAt.Add(-time.Second) }, pricereview.ErrPastChange},
		"바로 지금이다":   {func(d *pricereview.Draft) { d.ChangesAt = startedAt }, pricereview.ErrPastChange},
	}
	for name, tc := range cases {
		draft := good
		tc.edit(&draft)
		if _, err := f.service.Add(ctx(t), draft); !errors.Is(err, tc.want) {
			t.Errorf("%s: 오류 = %v, 기대 = %v", name, err, tc.want)
		}
	}
	// 길이는 글자 수로 센다. 한글 200자는 받는다
	edge := good
	edge.Subject = strings.Repeat("가", 200)
	if _, err := f.service.Add(ctx(t), edge); err != nil {
		t.Errorf("한글 200자를 받지 않았다: %v", err)
	}
}

func TestStepsBecomeDueAsTheDayComes(t *testing.T) {
	f := setUp(t)
	added := f.add(31 * day)
	if due := f.dueOf(added.ID); len(due) != 0 {
		t.Fatalf("31일 전인데 할 일이 나왔다: %+v", due)
	}

	f.clock.Advance(day)
	due := f.dueOf(added.ID)

	if len(due) != 1 || due[0].Step != pricereview.StepAnnounce || due[0].Stage != pricereview.StageD30 || due[0].DaysLeft != 30 {
		t.Errorf("30일 전의 할 일 = %+v. 첫 공지 하나여야 한다", due)
	}
}

func TestDoneStepsStopWarning(t *testing.T) {
	f := setUp(t)
	added := f.add(10 * day)
	if due := f.dueOf(added.ID); len(due) != 2 {
		t.Fatalf("10일 전인데 할 일 = %+v. 첫 공지와 자세한 공지 둘이어야 한다", due)
	}

	marked, err := f.service.Done(ctx(t), added.ID, pricereview.StepAnnounce, "ops", "https://example.com/notice/1")
	if err != nil {
		t.Fatalf("끝냈다고 적지 못했다: %v", err)
	}

	if mark, ok := marked.Done[pricereview.StepAnnounce]; !ok || mark.MarkedBy != "ops" || mark.Note != "https://example.com/notice/1" || !mark.MarkedAt.Equal(startedAt) {
		t.Errorf("돌려받은 표시 = %+v", marked.Done)
	}
	due := f.dueOf(added.ID)
	if len(due) != 1 || due[0].Step != pricereview.StepNotice {
		t.Errorf("남은 할 일 = %+v. 자세한 공지 하나여야 한다", due)
	}
}

func TestAStepIsMarkedOnlyOnce(t *testing.T) {
	f := setUp(t)
	added := f.add(10 * day)
	if _, err := f.service.Done(ctx(t), added.ID, pricereview.StepNotice, "ops", ""); err != nil {
		t.Fatalf("끝냈다고 적지 못했다: %v", err)
	}
	if _, err := f.service.Done(ctx(t), added.ID, pricereview.StepNotice, "other", "다시"); !errors.Is(err, pricereview.ErrAlreadyMarked) {
		t.Errorf("두 번째 표시 = %v. ErrAlreadyMarked 이어야 한다", err)
	}
	got, _ := f.listed(true, added.ID)
	if got.Done[pricereview.StepNotice].MarkedBy != "ops" {
		t.Errorf("처음 표시가 바뀌었다: %+v", got.Done)
	}
}

func TestAReviewWithEveryStepDoneLeavesTheOpenList(t *testing.T) {
	f := setUp(t)
	added := f.add(10 * day)
	for _, step := range []pricereview.Step{pricereview.StepFinal, pricereview.StepAnnounce, pricereview.StepNotice} {
		if _, err := f.service.Done(ctx(t), added.ID, step, "ops", ""); err != nil {
			t.Fatalf("%s 를 끝냈다고 적지 못했다: %v", step, err)
		}
	}
	f.clock.Advance(20 * day)

	if _, found := f.listed(false, added.ID); found {
		t.Error("셋을 다 끝낸 할 일이 열린 목록에 있다")
	}
	if _, found := f.listed(true, added.ID); !found {
		t.Error("셋을 다 끝낸 할 일이 모든 목록에서도 사라졌다")
	}
	if due := f.dueOf(added.ID); len(due) != 0 {
		t.Errorf("다 끝냈는데 경고가 나왔다: %+v", due)
	}
}

func TestACancelledReviewStaysClosed(t *testing.T) {
	f := setUp(t)
	added := f.add(10 * day)
	if _, err := f.service.Done(ctx(t), added.ID, pricereview.StepAnnounce, "ops", ""); err != nil {
		t.Fatalf("끝냈다고 적지 못했다: %v", err)
	}
	if _, err := f.service.Cancel(ctx(t), added.ID, "ops", ""); !errors.Is(err, pricereview.ErrMissingReason) {
		t.Errorf("이유 없이 닫기 = %v. ErrMissingReason 이어야 한다", err)
	}

	closed, err := f.service.Cancel(ctx(t), added.ID, "ops", "공급사가 인상을 거둬들임")

	if err != nil || closed.Cancelled == nil || closed.Cancelled.Note != "공급사가 인상을 거둬들임" || closed.Open() {
		t.Fatalf("닫은 할 일 = %+v, %v", closed, err)
	}
	// 이미 끝낸 표시는 그대로 남는다
	if _, kept := closed.Done[pricereview.StepAnnounce]; !kept {
		t.Error("닫으면서 끝낸 표시가 사라졌다")
	}
	if due := f.dueOf(added.ID); len(due) != 0 {
		t.Errorf("닫았는데 경고가 나왔다: %+v", due)
	}
	if _, err := f.service.Done(ctx(t), added.ID, pricereview.StepNotice, "ops", ""); !errors.Is(err, pricereview.ErrClosed) {
		t.Errorf("닫은 뒤 끝냈다고 적기 = %v. ErrClosed 이어야 한다", err)
	}
	if _, err := f.service.Cancel(ctx(t), added.ID, "ops", "또"); !errors.Is(err, pricereview.ErrClosed) {
		t.Errorf("두 번 닫기 = %v. ErrClosed 이어야 한다", err)
	}
}

func TestMarkingRefusesUnknownThings(t *testing.T) {
	f := setUp(t)
	added := f.add(10 * day)
	if _, err := f.service.Done(ctx(t), added.ID, "cancel", "ops", "x"); !errors.Is(err, pricereview.ErrUnknownStep) {
		t.Errorf("cancel 을 할 일로 끝내기 = %v. ErrUnknownStep 이어야 한다", err)
	}
	if _, err := f.service.Done(ctx(t), -1, pricereview.StepNotice, "ops", ""); !errors.Is(err, pricereview.ErrNotFound) {
		t.Errorf("없는 번호 = %v. ErrNotFound 이어야 한다", err)
	}
	if _, err := f.service.Done(ctx(t), added.ID, pricereview.StepNotice, "", ""); !errors.Is(err, pricereview.ErrMissingName) {
		t.Errorf("적은 사람이 없다 = %v. ErrMissingName 이어야 한다", err)
	}
	if _, err := f.service.Done(ctx(t), added.ID, pricereview.StepNotice, "ops", strings.Repeat("a", 1001)); !errors.Is(err, pricereview.ErrInvalidNote) {
		t.Errorf("글이 길다 = %v. ErrInvalidNote 이어야 한다", err)
	}
}

func TestListIsInTheOrderOfTheChanges(t *testing.T) {
	f := setUp(t)
	late := f.add(40 * day)
	early := f.add(20 * day)

	reviews, err := f.service.List(ctx(t), false)
	if err != nil {
		t.Fatalf("목록을 읽지 못했다: %v", err)
	}
	earlyAt, lateAt := -1, -1
	for i, r := range reviews {
		switch r.ID {
		case early.ID:
			earlyAt = i
		case late.ID:
			lateAt = i
		}
	}
	if earlyAt < 0 || lateAt < 0 || earlyAt > lateAt {
		t.Errorf("먼저 바뀌는 것이 먼저 나와야 한다: 이른 것 %d 번째, 늦은 것 %d 번째", earlyAt, lateAt)
	}
}
