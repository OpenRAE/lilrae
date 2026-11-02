package clock_test

import (
	"encoding/json/v2"
	"os"
	"testing"
	"time"

	"github.com/OpenRAE/lilrae/internal/clock"
)

// timeCorpus is the vector file of a timestamp scheme of Go port 04. The
// input of a case is the instant that the clock reads.
type timeCorpus struct {
	Corpus  int    `json:"corpus"`
	Scheme  string `json:"scheme"`
	Version string `json:"version"`
	Owner   string `json:"owner"`
	Cases   []struct {
		ID     string `json:"id"`
		Input  string `json:"input"`
		Note   string `json:"note,omitzero"`
		Expect struct {
			Text string `json:"text"`
		} `json:"expect"`
	} `json:"cases"`
}

func checkVectors(t *testing.T, scheme string, form func(time.Time) string) {
	t.Helper()
	root, err := os.OpenRoot("../../conformance/testdata/vectors")
	if err != nil {
		t.Fatal(err)
	}
	data, err := root.ReadFile(scheme + ".json")
	if closeErr := root.Close(); closeErr != nil {
		t.Fatal(closeErr)
	}
	if err != nil {
		t.Fatal(err)
	}
	var c timeCorpus
	if err := json.Unmarshal(data, &c, json.RejectUnknownMembers(true)); err != nil {
		t.Fatal(err)
	}
	if c.Scheme != scheme || len(c.Cases) == 0 {
		t.Fatalf("the vector file names scheme %q and has %d cases", c.Scheme, len(c.Cases))
	}
	for _, tc := range c.Cases {
		instant, err := time.Parse(time.RFC3339Nano, tc.Input)
		if err != nil {
			t.Fatalf("%s: %v", tc.ID, err)
		}
		if got := form(instant); got != tc.Expect.Text {
			t.Errorf("%s: %s, want %s", tc.ID, got, tc.Expect.Text)
		}
	}
}

func TestISOVectors(t *testing.T) {
	checkVectors(t, "continuity-now", clock.ISO)
}

func TestISOZVectors(t *testing.T) {
	checkVectors(t, "utc-now", clock.ISOZ)
}

func TestFormsDropNanoseconds(t *testing.T) {
	instant := time.Date(2026, 3, 24, 2, 0, 0, 999, time.UTC)
	if got := clock.ISOZ(instant); got != "2026-03-24T02:00:00Z" {
		t.Errorf("ISOZ = %s, want the whole second", got)
	}
	instant = time.Date(2026, 3, 24, 2, 0, 0, 1999, time.UTC)
	if got := clock.ISO(instant); got != "2026-03-24T02:00:00.000001+00:00" {
		t.Errorf("ISO = %s, want one microsecond", got)
	}
}

func TestSystemNowIsUTC(t *testing.T) {
	before := time.Now()
	now := clock.System{}.Now()
	if now.Location() != time.UTC || now.Before(before.Add(-time.Second)) || now.After(time.Now().Add(time.Second)) {
		t.Errorf("System.Now = %v, want the current instant in UTC", now)
	}
}
