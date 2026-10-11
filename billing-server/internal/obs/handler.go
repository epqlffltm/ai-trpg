// billing-server/internal/obs/handler.go

package obs

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"math"
	"sync"
	"time"
)

// ServiceName 은 이 서버의 이름이다. 모든 로그 줄의 service 칸에 적힌다.
const ServiceName = "billing-server"

// 공통 규격의 칸 이름들.
const (
	FieldOperation    = "operation"
	FieldResult       = "result"
	FieldErrorCode    = "error_code"
	FieldErrorType    = "error_type"
	FieldErrorMessage = "error_message"
	FieldStackTrace   = "stack_trace"
	FieldDurationMS   = "duration_ms"
)

// timestampLayout 은 timestamp 칸의 모양이다. RFC 3339, UTC, 천분의 1초까지다.
const timestampLayout = "2006-01-02T15:04:05.000Z"

// levelCritical 은 critical 로 적는 수준이다. slog 에는 error 까지만 있어서 그 위를 하나 정한다.
const levelCritical = slog.LevelError + 4

// reservedFields 는 이 처리기가 정하는 칸이다. 로그를 남기는 쪽이 같은 이름을 넘겨도 덮어쓰지 못한다.
var reservedFields = map[string]bool{
	"timestamp": true, "level": true, "service": true, "environment": true, "version": true,
	"message": true, "request_id": true, "trace_id": true, "job_id": true,
}

// ServiceInfo 는 모든 로그 줄에 실리는, 이 프로세스가 무엇인지다.
type ServiceInfo struct {
	// Service 는 서버의 이름이다.
	Service string
	// Environment 는 배포 환경이다(development, production 등). 비어 있으면 싣지 않는다.
	Environment string
	// Version 은 배포한 코드의 버전이다(git SHA 나 이미지 태그). 비어 있으면 싣지 않는다.
	Version string
}

// field 는 로그 한 줄의 칸 하나다. 순서를 지키려고 맵 대신 목록으로 모은다.
type field struct {
	name  string
	value any
}

// Handler 는 slog 의 기록을 공통 규격의 JSON 한 줄로 적는다.
type Handler struct {
	info      ServiceInfo
	threshold slog.Level
	// attrs 는 With 로 미리 붙여 둔 칸들이다
	attrs []slog.Attr
	// prefix 는 WithGroup 으로 정한 묶음의 이름이다. 칸의 이름 앞에 붙는다
	prefix string
	// out 과 mu 는 With 로 만든 처리기들이 함께 쓴다. 줄이 섞이지 않게 한 번에 한 줄만 쓴다
	out io.Writer
	mu  *sync.Mutex
}

// NewHandler 는 out 에 쓰는 처리기를 만든다. threshold 보다 낮은 수준은 내보내지 않는다.
func NewHandler(out io.Writer, info ServiceInfo, threshold slog.Level) *Handler {
	return &Handler{info: info, threshold: threshold, out: out, mu: &sync.Mutex{}}
}

// NewLogger 는 공통 규격으로 적는 로거를 만든다.
func NewLogger(out io.Writer, info ServiceInfo, threshold slog.Level) *slog.Logger {
	return slog.New(NewHandler(out, info, threshold))
}

// ParseLevel 은 LOG_LEVEL 설정의 값을 slog 의 수준으로 바꾼다. 모르는 값이면 false 다.
func ParseLevel(name string) (slog.Level, bool) {
	switch name {
	case "debug":
		return slog.LevelDebug, true
	case "info":
		return slog.LevelInfo, true
	case "warning":
		return slog.LevelWarn, true
	case "error":
		return slog.LevelError, true
	default:
		return slog.LevelInfo, false
	}
}

// Enabled 는 이 수준의 기록을 내보내는지 답한다.
func (h *Handler) Enabled(_ context.Context, level slog.Level) bool {
	return level >= h.threshold
}

// WithAttrs 는 칸들을 미리 붙여 둔 처리기를 돌려준다.
func (h *Handler) WithAttrs(attrs []slog.Attr) slog.Handler {
	clone := *h
	clone.attrs = append(append([]slog.Attr{}, h.attrs...), prefixed(h.prefix, attrs)...)
	return &clone
}

// WithGroup 은 이 뒤의 칸 이름 앞에 묶음의 이름을 붙이는 처리기를 돌려준다. 줄은 납작한 채로 둔다.
func (h *Handler) WithGroup(name string) slog.Handler {
	if name == "" {
		return h
	}
	clone := *h
	clone.prefix = h.prefix + name + "."
	return &clone
}

// Handle 은 기록 하나를 한 줄로 적는다.
func (h *Handler) Handle(ctx context.Context, record slog.Record) error {
	fields := h.baseFields(record)
	fields = append(fields, idFields(CurrentIDs(ctx))...)
	for _, attr := range h.attrs {
		fields = appendAttr(fields, "", attr)
	}
	record.Attrs(func(attr slog.Attr) bool {
		fields = appendAttr(fields, h.prefix, attr)
		return true
	})
	return h.write(encode(fields))
}

// baseFields 는 모든 줄에 있는 칸들이다.
func (h *Handler) baseFields(record slog.Record) []field {
	fields := []field{
		{"timestamp", timestampOf(record.Time)},
		{"level", levelName(record.Level)},
		{"service", h.info.Service},
	}
	if h.info.Environment != "" {
		fields = append(fields, field{"environment", h.info.Environment})
	}
	if h.info.Version != "" {
		fields = append(fields, field{"version", h.info.Version})
	}
	return append(fields, field{"message", ScrubText(record.Message, MaxMessageLength)})
}

// write 는 한 줄을 내보낸다.
func (h *Handler) write(line []byte) error {
	h.mu.Lock()
	defer h.mu.Unlock()
	_, err := h.out.Write(line)
	return err
}

// timestampOf 는 기록의 시각을 규격의 모양으로 적는다. 시각이 없으면 지금이다.
func timestampOf(at time.Time) string {
	if at.IsZero() {
		at = time.Now()
	}
	return at.UTC().Format(timestampLayout)
}

// levelName 은 slog 의 수준을 규격의 이름으로 바꾼다.
func levelName(level slog.Level) string {
	switch {
	case level >= levelCritical:
		return "critical"
	case level >= slog.LevelError:
		return "error"
	case level >= slog.LevelWarn:
		return "warning"
	case level >= slog.LevelInfo:
		return "info"
	default:
		return "debug"
	}
}

// idFields 는 걸려 있는 식별자들이다. 없는 것은 빈 글자로 채우지 않고 싣지 않는다.
func idFields(ids IDs) []field {
	var fields []field
	if ids.RequestID != "" {
		fields = append(fields, field{"request_id", ids.RequestID})
	}
	if ids.Trace.ID != "" {
		fields = append(fields, field{"trace_id", ids.Trace.ID})
	}
	if ids.JobID != "" {
		fields = append(fields, field{"job_id", ids.JobID})
	}
	return fields
}

// prefixed 는 칸들의 이름 앞에 묶음의 이름을 붙인다.
func prefixed(prefix string, attrs []slog.Attr) []slog.Attr {
	if prefix == "" {
		return attrs
	}
	renamed := make([]slog.Attr, len(attrs))
	for i, attr := range attrs {
		renamed[i] = slog.Attr{Key: prefix + attr.Key, Value: attr.Value}
	}
	return renamed
}

// appendAttr 는 칸 하나를 더한다. 이름이 없거나, 이 처리기가 정하는 칸이거나, 이미 있는 이름이면 버린다.
// 같은 이름이 두 번 나가면 읽는 쪽마다 다른 값을 고른다.
func appendAttr(fields []field, prefix string, attr slog.Attr) []field {
	name := prefix + attr.Key
	if attr.Key == "" || reservedFields[name] || hasField(fields, name) {
		return fields
	}
	return append(fields, field{name, safeValue(name, attr.Value.Resolve())})
}

// hasField 는 그 이름의 칸이 이미 있는지 본다.
func hasField(fields []field, name string) bool {
	for _, item := range fields {
		if item.name == name {
			return true
		}
	}
	return false
}

// safeValue 는 값을 로그에 적어도 되는 모양으로 바꾼다.
//   - 이름이 민감하면 가린다
//   - 글은 비밀로 보이는 모양을 가리고 자른다
//   - 숫자, 참거짓, 시각, 걸린 시간은 그대로 적는다
//   - 그 밖의 것(구조체, 맵, 목록, 묶음)은 풀어 적지 않고 종류의 이름만 적는다.
//     무엇이 들었는지 모르는 것을 통째로 적으면 그 안의 비밀이 따라 나간다
func safeValue(name string, value slog.Value) any {
	if IsSensitiveName(name) {
		return Redacted
	}
	switch value.Kind() {
	case slog.KindString:
		return ScrubText(value.String(), limitOf(name))
	case slog.KindInt64:
		return value.Int64()
	case slog.KindUint64:
		return value.Uint64()
	case slog.KindFloat64:
		return safeFloat(value.Float64())
	case slog.KindBool:
		return value.Bool()
	case slog.KindDuration:
		return value.Duration().String()
	case slog.KindTime:
		return timestampOf(value.Time())
	case slog.KindGroup:
		return "[group]"
	default:
		return safeAny(name, value.Any())
	}
}

// safeAny 는 slog 가 종류를 모르는 값을 적는다. 오류는 그 글을, 그 밖의 것은 종류의 이름만 적는다.
func safeAny(name string, value any) any {
	switch typed := value.(type) {
	case nil:
		return nil
	case error:
		return ScrubText(typed.Error(), limitOf(name))
	case fmt.Stringer:
		return ScrubText(typed.String(), limitOf(name))
	default:
		return fmt.Sprintf("[%T]", value)
	}
}

// safeFloat 는 JSON 에 없는 숫자(NaN, 무한대)를 글자로 바꾼다.
func safeFloat(value float64) any {
	if math.IsNaN(value) || math.IsInf(value, 0) {
		return fmt.Sprint(value)
	}
	return value
}

// limitOf 는 그 칸에 적는 글의 가장 긴 길이다.
func limitOf(name string) int {
	if name == FieldStackTrace {
		return MaxStackLength
	}
	return MaxValueLength
}

// encode 는 칸들을 순서대로 JSON 한 줄로 적는다. 끝에 줄바꿈이 하나 붙는다.
// 값 안의 줄바꿈과 따옴표는 JSON 이 \n, \" 로 바꿔 적는다. 그래서 한 줄에 JSON 하나다.
func encode(fields []field) []byte {
	var line bytes.Buffer
	line.WriteByte('{')
	for i, item := range fields {
		if i > 0 {
			line.WriteByte(',')
		}
		line.Write(jsonOf(item.name))
		line.WriteByte(':')
		line.Write(jsonOf(item.value))
	}
	line.WriteString("}\n")
	return line.Bytes()
}

// jsonOf 는 값 하나를 JSON 으로 적는다. <, >, & 를 < 처럼 바꾸지 않는다. 로그는 HTML 이 아니다.
func jsonOf(value any) []byte {
	var buffer bytes.Buffer
	encoder := json.NewEncoder(&buffer)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(value); err != nil {
		return []byte(`"[unencodable]"`)
	}
	// Encode 는 끝에 줄바꿈을 붙인다
	return bytes.TrimRight(buffer.Bytes(), "\n")
}
