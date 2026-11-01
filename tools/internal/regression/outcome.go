package regression

import (
	"encoding/json/jsontext"
	"encoding/json/v2"
	"errors"
	"fmt"
	"io"
	"strings"
)

// outcome is the result of one test in one run.
type outcome int

const (
	// notRun means that the run has no event for the test.
	notRun outcome = iota
	// unfinished means that the test started and has no result: a timeout, an
	// exit, or a panic in another goroutine.
	unfinished
	passed
	failed
	skipped
)

func (o outcome) String() string {
	switch o {
	case notRun:
		return "did not run"
	case unfinished:
		return "did not finish"
	case passed:
		return "passed"
	case failed:
		return "failed"
	case skipped:
		return "was skipped"
	}
	return fmt.Sprintf("outcome(%d)", int(o))
}

// testRun is the result of one "go test -json" run of one test.
type testRun struct {
	// buildFailed reports that the package or its tests did not build.
	buildFailed bool
	// buildOutput holds the first lines of the build output.
	buildOutput []string
	outcome     outcome
	// processFailed reports that the go command exited with a nonzero status.
	processFailed bool
}

// event holds the fields of a test2json event that the check reads.
type event struct {
	Action      string `json:"Action"`
	Test        string `json:"Test"`
	Output      string `json:"Output"`
	FailedBuild string `json:"FailedBuild"`
}

// maxBuildLines bounds the build output that a finding quotes.
const maxBuildLines = 5

// parseRun reads the event stream of a "go test -json" run and returns the
// result of the top-level test name.
func parseRun(r io.Reader, name string) (testRun, error) {
	var run testRun
	dec := jsontext.NewDecoder(r)
	for {
		var ev event
		if err := json.UnmarshalDecode(dec, &ev); err != nil {
			if errors.Is(err, io.EOF) {
				return run, nil
			}
			return testRun{}, fmt.Errorf("read a go test event: %w", err)
		}
		run.record(ev, name)
	}
}

// record updates the run with an event.
func (run *testRun) record(ev event, name string) {
	if ev.Action == "build-fail" || ev.FailedBuild != "" {
		run.buildFailed = true
	}
	if line := strings.TrimSpace(ev.Output); ev.Action == "build-output" && line != "" && len(run.buildOutput) < maxBuildLines {
		run.buildOutput = append(run.buildOutput, line)
	}
	if ev.Test == name {
		run.outcome = next(run.outcome, ev.Action)
	}
}

// next returns the outcome of a test after an event of the test.
func next(current outcome, action string) outcome {
	switch action {
	case "run":
		if current == notRun {
			return unfinished
		}
	case "pass":
		return passed
	case "fail":
		return failed
	case "skip":
		return skipped
	}
	return current
}
