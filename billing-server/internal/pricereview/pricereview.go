// billing-server/internal/pricereview/pricereview.go

// Package pricereview 는 공급사 가격 변경의 할 일이다. 공급사(AI 모델 회사)가 값을 바꾸는 날을 적어 두면,
// 그날에서 거꾸로 센 날짜마다 우리 쪽에서 할 일을 알린다.
//
//	announce  D-30  첫 공지
//	notice    D-14  자세한 공지, 그리고 새 값을 가격표에 미래 시각으로 넣는다
//	final     D-1   마지막 알림
//
// 이 패키지는 가격표를 바꾸지 않는다. 할 일을 적고, 때가 되었는지 셀 뿐이다.
// 새 값을 넣는 것은 운영자가 cmd/prices 로 한다. 값을 언제 얼마로 올릴지는 사람이 정할 일이다.
// 하루 한 번 도는 대사(internal/reconcile)가 Due 를 불러 때가 된 할 일을 경고한다.
package pricereview

import (
	"errors"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

const (
	// maxSubjectLength 는 할 일의 이름의 가장 긴 길이다. DB 의 CHECK 와 같은 값이다.
	maxSubjectLength = 200
	// maxNoteLength 는 덧붙이는 글의 가장 긴 길이다. DB 의 CHECK 와 같은 값이다.
	maxNoteLength = 1000
	// maxNameLength 는 적은 사람의 이름의 가장 긴 길이다.
	maxNameLength = 200
)

var (
	// ErrInvalidSubject 는 할 일의 이름이 비었거나 너무 길다는 오류다.
	ErrInvalidSubject = errors.New("무엇의 값이 바뀌는지 적어야 하고 200자 이하여야 합니다")
	// ErrInvalidNote 는 덧붙이는 글이 너무 길다는 오류다.
	ErrInvalidNote = errors.New("덧붙이는 글은 1000자 이하여야 합니다")
	// ErrMissingName 은 적은 사람의 이름이 비었거나 너무 길다는 오류다.
	ErrMissingName = errors.New("적은 사람의 이름은 비울 수 없고 200자 이하여야 합니다")
	// ErrPastChange 는 공급사가 값을 바꾸는 시각이 이미 지났다는 오류다. 지난 일에는 할 일이 없다.
	ErrPastChange = errors.New("공급사가 값을 바꾸는 시각은 지금보다 뒤여야 합니다")
	// ErrNotFound 는 그런 할 일이 없다는 오류다.
	ErrNotFound = errors.New("그런 할 일이 없습니다")
	// ErrUnknownStep 은 announce, notice, final 이 아닌 할 일을 끝냈다고 하려 했다는 오류다.
	ErrUnknownStep = errors.New("할 일은 announce, notice, final 가운데 하나여야 합니다")
	// ErrAlreadyMarked 는 이미 끝냈다고 적은 할 일이라는 오류다. 표시는 한 번만 한다.
	ErrAlreadyMarked = errors.New("이미 끝냈다고 적은 할 일입니다")
	// ErrClosed 는 이미 닫은(cancel) 할 일이라는 오류다.
	ErrClosed = errors.New("이미 닫은 할 일입니다")
	// ErrMissingReason 은 닫는 이유를 적지 않았다는 오류다.
	ErrMissingReason = errors.New("닫는 이유를 적어야 합니다")
)

// Step 은 공급사가 값을 바꾸기 전에 할 일 하나다. DB 의 price_review_marks.mark 에 이 글자가 그대로 적힌다.
type Step string

const (
	// StepAnnounce 는 첫 공지다. D-30 부터 할 일이다.
	StepAnnounce Step = "announce"
	// StepNotice 는 자세한 공지와 함께 새 값을 가격표에 미래 시각으로 넣는 것이다. D-14 부터 할 일이다.
	StepNotice Step = "notice"
	// StepFinal 은 마지막 알림이다. D-1 부터 할 일이다.
	StepFinal Step = "final"
)

// cancelMark 는 할 일을 닫았다는 표시다. 공급사가 인상을 거둬들였거나 잘못 적은 할 일이다.
const cancelMark = "cancel"

// Mark 는 할 일을 끝냈다는(또는 닫았다는) 표시 하나다.
type Mark struct {
	Note     string
	MarkedBy string
	MarkedAt time.Time
}

// Review 는 공급사 가격 변경 하나와 그 할 일들이다.
type Review struct {
	ID      int64
	Subject string
	// ChangesAt 은 공급사가 값을 바꾸는 시각이다.
	ChangesAt time.Time
	Note      string
	CreatedBy string
	CreatedAt time.Time
	// Done 은 끝낸 할 일들이다. 없는 할 일은 아직이다.
	Done map[Step]Mark
	// Cancelled 는 닫은 표시다. 닫지 않았으면 nil 이다.
	Cancelled *Mark
}

// Open 은 아직 할 일이 남았는지다. 닫았거나 셋을 다 끝냈으면 false 다.
func (r Review) Open() bool {
	return r.Cancelled == nil && len(r.Remaining()) > 0
}

// Remaining 은 끝내지 않은 할 일들이다. 닫았으면 없다. 차례(announce, notice, final)대로 돌려준다.
func (r Review) Remaining() []Step {
	if r.Cancelled != nil {
		return nil
	}
	var left []Step
	for _, w := range schedule {
		if _, done := r.Done[w.step]; !done {
			left = append(left, w.step)
		}
	}
	return left
}

// Draft 는 새로 적을 할 일이다.
type Draft struct {
	Subject   string
	ChangesAt time.Time
	Note      string
	CreatedBy string
}

// Service 는 할 일을 적고 읽는다.
type Service struct {
	pool *pgxpool.Pool
	now  func() time.Time
}

// NewService 는 Service 를 만든다. now 는 지금 시각을 돌려주는 함수다.
func NewService(pool *pgxpool.Pool, now func() time.Time) *Service {
	return &Service{pool: pool, now: now}
}

// clock 은 지금 시각을 DB 가 적는 모양(UTC, 백만분의 1초)으로 맞춰 돌려준다.
func (s *Service) clock() time.Time {
	return s.now().UTC().Truncate(time.Microsecond)
}
