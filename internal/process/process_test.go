package process_test

import (
	"bytes"
	"context"
	"encoding/json/v2"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/OpenRAE/lilrae/internal/process"
)

func binary(t *testing.T) string {
	t.Helper()
	name := filepath.Join(t.TempDir(), "child with spaces.exe")
	cmd := exec.CommandContext(t.Context(), "go", "build", "-o", name, "./testdata/child") //nolint:gosec // G204: fixed compiler and fixture; output is inside the test temporary directory.
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("build process fixture: %v: %s", err, out)
	}
	return name
}

func runner() process.Runner {
	return process.Runner{TerminationGrace: 80 * time.Millisecond, ShutdownGrace: 300 * time.Millisecond, ReapTimeout: time.Second, ReleaseTimeout: 100 * time.Millisecond}
}

func request(executable, dir, mode string, args ...string) process.Request {
	return process.Request{Argv: append([]string{executable, mode}, args...), Dir: dir, Env: []string{}, Timeout: 10 * time.Second, MaxOutputBytes: 1 << 20}
}

func TestSharedCases(t *testing.T) {
	executable := binary(t)
	data, err := os.ReadFile("../../conformance/testdata/process-cases.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []processCase
	if err := json.Unmarshal(data, &cases, json.RejectUnknownMembers(true)); err != nil {
		t.Fatal(err)
	}
	for _, tc := range cases {
		t.Run(tc.ID, func(t *testing.T) { runSharedCase(t, executable, tc) })
	}
}

type processCase struct {
	ID         string   `json:"id"`
	Mode       string   `json:"mode"`
	Args       []string `json:"args"`
	Input      string   `json:"input"`
	InputSize  int      `json:"input_size"`
	TimeoutMS  int      `json:"timeout_ms"`
	Limit      int      `json:"limit"`
	Stdout     string   `json:"stdout"`
	StdoutSize int      `json:"stdout_size"`
	Stderr     string   `json:"stderr"`
	ExitCode   int      `json:"exit_code"`
	Failure    string   `json:"failure"`
}

func runSharedCase(t *testing.T, executable string, tc processCase) {
	t.Helper()
	req := request(executable, t.TempDir(), tc.Mode, tc.Args...)
	req.Stdin = []byte(tc.Input)
	if tc.InputSize > 0 {
		req.Stdin = bytes.Repeat([]byte("x"), tc.InputSize)
	}
	if tc.TimeoutMS > 0 {
		req.Timeout = time.Duration(tc.TimeoutMS) * time.Millisecond
	}
	req.MaxOutputBytes = tc.Limit
	got, err := runner().Run(t.Context(), req)
	if tc.Failure != "" {
		failure := checkFailure(t, err, tc.Failure, tc.Limit)
		if failure == nil {
			t.Fatal("expected a bounded failure")
		}
		return
	}
	if err != nil {
		t.Fatal(err)
	}
	stdout := []byte(tc.Stdout)
	if tc.StdoutSize > 0 {
		stdout = bytes.Repeat([]byte("x"), tc.StdoutSize)
	}
	if got.ExitCode != tc.ExitCode || !bytes.Equal(got.Stdout, stdout) || string(got.Stderr) != tc.Stderr {
		t.Fatalf("unexpected result for case %s: exit %d, stdout %d bytes, stderr %d bytes", tc.ID, got.ExitCode, len(got.Stdout), len(got.Stderr))
	}
	if got.Cleanup.ProcessGroup <= 0 || got.Cleanup.Elapsed < 0 || len(got.Cleanup.Residual) != 0 {
		t.Fatalf("cleanup = %v", got.Cleanup)
	}
}

func checkFailure(t *testing.T, err error, reason string, limit int) *process.Error {
	t.Helper()
	want := map[string]error{"timeout": context.DeadlineExceeded, "overflow": process.ErrOverflow, "cancel": context.Canceled}[reason]
	if !errors.Is(err, want) {
		t.Fatalf("failure = %v, want %v", err, want)
	}
	var failure *process.Error
	if !errors.As(err, &failure) || len(failure.Cleanup.Residual) != 0 {
		t.Fatalf("cleanup = %v", err)
	}
	if failure.StdoutBytes+failure.StderrBytes > limit {
		t.Fatal("retained output exceeds budget")
	}
	return failure
}

func TestDeadlineAndCancellation(t *testing.T) {
	executable := binary(t)
	for _, mode := range []string{"sleep", "flood"} {
		t.Run(mode, func(t *testing.T) {
			req := request(executable, t.TempDir(), mode)
			req.Timeout = time.Minute
			req.MaxOutputBytes = 32 << 20
			ctx, cancel := context.WithTimeout(t.Context(), 200*time.Millisecond)
			defer cancel()
			started := time.Now()
			_, err := runner().Run(ctx, req)
			if !errors.Is(err, context.DeadlineExceeded) {
				t.Fatalf("failure = %v", err)
			}
			if time.Since(started) > 3*time.Second {
				t.Fatal("caller deadline was not applied")
			}
		})
	}
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	_, err := runner().Run(ctx, request(executable, t.TempDir(), "sleep"))
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("pre-cancel = %v", err)
	}
}

func TestEnvironmentDirectoryAndSafeErrors(t *testing.T) {
	executable := binary(t)
	dir := t.TempDir()
	req := request(executable, dir, "environment")
	req.Env = []string{"CANARY=process-canary"}
	t.Setenv("LILRAE_PROCESS_AMBIENT", "must-not-inherit")
	got, err := runner().Run(t.Context(), req)
	if err != nil {
		t.Fatal(err)
	}
	if string(got.Stdout) != dir+"\nprocess-canary\n\n" {
		t.Fatal("directory or explicit environment changed")
	}
	req.Argv = []string{filepath.Join(dir, "process-canary")}
	_, err = runner().Run(t.Context(), req)
	if !errors.Is(err, process.ErrLaunch) {
		t.Fatalf("launch = %v", err)
	}
	for _, value := range []any{req, got, err} {
		for _, format := range []string{"%v", "%+v", "%#v"} {
			if strings.Contains(fmt.Sprintf(format, value), "process-canary") {
				t.Fatal("diagnostic formatting leaked a secret")
			}
		}
	}
}

func TestInvalidRequestsHaveNoEffects(t *testing.T) {
	executable := binary(t)
	dir := t.TempDir()
	marker := filepath.Join(dir, "must-not-exist")
	base := request(executable, dir, "touch", marker)
	mutations := map[string]func(*process.Request){
		"no-executable":         func(r *process.Request) { r.Argv = nil },
		"relative-executable":   func(r *process.Request) { r.Argv = []string{"child"} },
		"relative-directory":    func(r *process.Request) { r.Dir = "." },
		"nul-directory":         func(r *process.Request) { r.Dir += "\x00canary" },
		"nul-argument":          func(r *process.Request) { r.Argv = append(r.Argv, "\x00canary") },
		"environment-no-value":  func(r *process.Request) { r.Env = []string{"canary"} },
		"environment-empty-key": func(r *process.Request) { r.Env = []string{"=canary"} },
		"environment-nul":       func(r *process.Request) { r.Env = []string{"KEY=\x00canary"} },
		"environment-duplicate": func(r *process.Request) { r.Env = []string{"KEY=one", "KEY=two"} },
		"zero-timeout":          func(r *process.Request) { r.Timeout = 0 },
		"negative-timeout":      func(r *process.Request) { r.Timeout = -1 },
		"zero-limit":            func(r *process.Request) { r.MaxOutputBytes = 0 },
		"negative-limit":        func(r *process.Request) { r.MaxOutputBytes = -1 },
	}
	for name, mutate := range mutations {
		t.Run(name, func(t *testing.T) {
			req := base
			mutate(&req)
			_, err := runner().Run(t.Context(), req)
			if !errors.Is(err, process.ErrInvalid) {
				t.Fatalf("validation = %v", err)
			}
		})
	}
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	if _, err := runner().Run(ctx, base); !errors.Is(err, context.Canceled) {
		t.Fatalf("pre-cancel = %v", err)
	}
	if _, err := os.Stat(marker); !errors.Is(err, os.ErrNotExist) {
		t.Fatal("an invalid or pre-cancelled request launched a process")
	}
}

func TestConcurrentRunsKeepBudgetsSeparate(t *testing.T) {
	executable := binary(t)
	r := runner()
	done := make(chan error, 8)
	for i := range 8 {
		req := request(executable, t.TempDir(), "echo")
		req.Stdin = bytes.Repeat([]byte{byte(i)}, 4096)
		req.MaxOutputBytes = len(req.Stdin)
		go func() {
			got, err := r.Run(t.Context(), req)
			if err == nil && !bytes.Equal(got.Stdout, req.Stdin) {
				err = errors.New("concurrent output changed")
			}
			done <- err
		}()
	}
	for range 8 {
		if err := <-done; err != nil {
			t.Error(err)
		}
	}
}
