// billing-server/cmd/prices/import.go

// 가격표에 여러 줄을 한꺼번에 넣는 일(import). 파일을 읽어 줄로 바꾸고, 미리 보여 주거나(기본) 한 트랜잭션으로 넣는다(-apply).
//
// 파일은 CSV 다. 첫 줄은 머리줄이고, # 로 시작하는 줄은 설명으로 보고 넘긴다.
//
//	code,credits,effective_at
//	# 새 모델
//	narration.claude-sonnet-5-5.i0.o0,120,
//	narration.gemini-4-argon.i0.o0,240,2026-12-01T00:00:00+09:00
//	narration.old-model.i0.o0,stop,
//
// credits 에 stop 을 적으면 판매를 멈추는 줄이다. effective_at 을 비우면 지금부터다.
package main

import (
	"context"
	"encoding/csv"
	"errors"
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/credit"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
)

// importHeader 는 파일의 첫 줄이다. 칸의 차례를 사람이 보고 알게 한다.
var importHeader = []string{"code", "credits", "effective_at"}

// stopWord 는 credits 칸에 적으면 판매를 멈추는 줄이 되는 낱말이다.
const stopWord = "stop"

// utf8BOM 은 파일 맨 앞에 붙는 표시(BOM)다. 윈도우의 엑셀이 "CSV UTF-8" 로 저장하면 붙는다.
// 떼지 않으면 머리줄의 첫 칸이 "\ufeffcode" 로 읽혀, 맞아 보이는 머리줄이 틀렸다고 나온다.
const utf8BOM = "\ufeff"

// readEntries 는 파일을 열어 넣을 줄들로 바꾼다.
func readEntries(path string) ([]pricing.Entry, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("파일을 열지 못했습니다: %w", err)
	}
	defer file.Close()
	return parseEntries(file)
}

// parseEntries 는 CSV 를 읽어 넣을 줄들로 바꾼다. 머리줄이 다르거나 칸이 틀리면 그 줄의 번호를 붙인 오류다.
func parseEntries(source io.Reader) ([]pricing.Entry, error) {
	reader := csv.NewReader(source)
	reader.Comment = '#'
	reader.FieldsPerRecord = len(importHeader)
	reader.TrimLeadingSpace = true
	records, err := reader.ReadAll()
	if err != nil {
		return nil, fmt.Errorf("CSV 를 읽지 못했습니다: %w", err)
	}
	if len(records) > 0 {
		records[0][0] = strings.TrimPrefix(records[0][0], utf8BOM)
	}
	if len(records) == 0 || strings.Join(records[0], ",") != strings.Join(importHeader, ",") {
		return nil, errors.New("첫 줄은 code,credits,effective_at 이어야 합니다")
	}
	entries := make([]pricing.Entry, 0, len(records)-1)
	for i, record := range records[1:] {
		entry, err := parseEntry(record)
		if err != nil {
			return nil, fmt.Errorf("%d번째 줄(%s): %w", i+1, record[0], err)
		}
		entries = append(entries, entry)
	}
	return entries, nil
}

// parseEntry 는 CSV 의 줄 하나(이름, 값, 적용 시각)를 넣을 줄로 바꾼다.
func parseEntry(record []string) (pricing.Entry, error) {
	entry := pricing.Entry{Code: strings.TrimSpace(record[0])}
	value := strings.TrimSpace(record[1])
	if value == stopWord {
		entry.Stop = true
	} else {
		amount, err := strconv.ParseInt(value, 10, 64)
		if err != nil {
			return pricing.Entry{}, errors.New("credits 는 정수나 stop 이어야 합니다")
		}
		entry.Credits = credit.Amount(amount)
	}
	if at := strings.TrimSpace(record[2]); at != "" {
		effective, err := time.Parse(time.RFC3339, at)
		if err != nil {
			return pricing.Entry{}, errors.New("effective_at 은 2026-12-01T00:00:00+09:00 모양이어야 합니다")
		}
		entry.EffectiveAt = effective
	}
	return entry, nil
}

// doImport 는 줄들을 미리 보여 주거나(apply 가 false) 넣고(true), 결과를 찍는다.
func doImport(ctx context.Context, list prices, req request, out io.Writer) error {
	if !req.apply {
		planned, err := list.Plan(ctx, req.entries, req.reason, req.by)
		if err != nil {
			return err
		}
		printPlan(out, planned)
		fmt.Fprintln(out, "미리 보기만 했습니다. 가격표는 바뀌지 않았습니다. 넣으려면 -apply 를 붙여 다시 실행하세요")
		return nil
	}
	planned, err := list.Import(ctx, req.entries, req.reason, req.by)
	if err != nil {
		return err
	}
	printPlan(out, planned)
	if changedLines(planned) == 0 {
		fmt.Fprintln(out, "바뀌는 줄이 없어 넣은 것이 없습니다. 가격표는 그대로입니다")
		return nil
	}
	fmt.Fprintln(out, "넣었습니다")
	return nil
}

// changedLines 는 실제로 넣는 줄(바뀌는 것이 있는 줄)의 수다. 같음(EffectSame)은 넣지 않는다.
func changedLines(planned []pricing.Planned) int {
	count := 0
	for _, line := range planned {
		if line.Effect != pricing.EffectSame {
			count++
		}
	}
	return count
}

// printPlan 은 줄마다 무엇이 바뀌는지 한 줄씩 찍고, 끝에 바뀌는 종류별로 센 수를 찍는다.
func printPlan(out io.Writer, planned []pricing.Planned) {
	counts := map[pricing.Effect]int{}
	for _, line := range planned {
		counts[line.Effect]++
		fmt.Fprintln(out, formatPlanned(line))
	}
	fmt.Fprintf(out, "새로 %d, 올림 %d, 내림 %d, 멈춤 %d, 같음(넣지 않음) %d\n",
		counts[pricing.EffectNew], counts[pricing.EffectRaise], counts[pricing.EffectLower],
		counts[pricing.EffectStop], counts[pricing.EffectSame])
}

// formatPlanned 는 계산한 줄 하나를 "이름  바뀜  전 → 후  언제" 모양의 글로 바꾼다.
func formatPlanned(line pricing.Planned) string {
	before := "-"
	if line.Before != nil {
		before = line.Before.Credits.String()
	}
	after := "판매 중지"
	if !line.Entry.Stop {
		after = line.Entry.Credits.String()
	}
	return fmt.Sprintf("%s  %s  %s → %s  %s 부터",
		line.Entry.Code, effectLabel(line.Effect), before, after, line.EffectiveAt.Local().Format(timeLayout))
}

// effectLabel 은 바뀌는 종류를 사람이 읽는 말로 바꾼다.
func effectLabel(effect pricing.Effect) string {
	switch effect {
	case pricing.EffectNew:
		return "새로"
	case pricing.EffectRaise:
		return "올림"
	case pricing.EffectLower:
		return "내림"
	case pricing.EffectStop:
		return "멈춤"
	default:
		return "같음"
	}
}
