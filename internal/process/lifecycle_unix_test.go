//go:build linux || darwin

package process_test

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strconv"
	"syscall"
	"testing"
	"time"

	"github.com/OpenRAE/lilrae/internal/process"
)

func independentAlive(p *os.Process) error {
	if err := p.Signal(syscall.Signal(0)); err != nil {
		return fmt.Errorf("independent service: %w", err)
	}
	return nil
}

func TestEscapedStreamHolderIsReported(t *testing.T) {
	executable := binary(t)
	dir := t.TempDir()
	ready := filepath.Join(dir, "escaped.pid")
	req := request(executable, dir, "spawn", "detached", "exit", ready)
	started := time.Now()
	_, err := runner().Run(t.Context(), req)
	p := helperProcess(t, ready)
	t.Cleanup(func() {
		if stopErr := p.Kill(); stopErr != nil && !errors.Is(stopErr, os.ErrProcessDone) {
			t.Errorf("escaped fixture stop: %v", stopErr)
		}
		if closeErr := p.Release(); closeErr != nil {
			t.Errorf("escaped fixture release: %v", closeErr)
		}
	})
	expectStreamResidue(t, err)
	if time.Since(started) > 3*time.Second {
		t.Fatal("stream holder extended capture")
	}
	var failure *process.Error
	if !errors.As(err, &failure) {
		t.Fatal(err)
	}
	if failure.StdoutBytes != len("result") || failure.StderrBytes != 0 {
		t.Fatal("capture changed after parent exit")
	}
}

func TestSignalExitCode(t *testing.T) {
	executable := binary(t)
	got, err := runner().Run(t.Context(), request(executable, t.TempDir(), "signal"))
	if err != nil {
		t.Fatal(err)
	}
	if got.ExitCode != -int(syscall.SIGTERM) {
		t.Fatalf("exit code = %d, want %d", got.ExitCode, -int(syscall.SIGTERM))
	}
}

func helperProcess(t *testing.T, ready string) *os.Process {
	t.Helper()
	data, err := os.ReadFile(ready) //nolint:gosec // G304: ready is the fixture PID file in this test temporary directory.
	if err != nil {
		t.Fatal(err)
	}
	pid, err := strconv.Atoi(string(data))
	if err != nil {
		t.Fatal(err)
	}
	p, err := os.FindProcess(pid)
	if err != nil {
		t.Fatal(err)
	}
	return p
}

func expectStreamResidue(t *testing.T, err error) {
	t.Helper()
	var failure *process.Error
	if !errors.As(err, &failure) || !errors.Is(err, process.ErrResidue) {
		t.Fatalf("failure = %v", err)
	}
	if !slices.Contains(failure.Cleanup.Residual, process.StreamsHeld) {
		t.Fatalf("cleanup = %v", failure.Cleanup)
	}
}
