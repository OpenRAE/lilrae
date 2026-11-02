package process_test

import (
	"context"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"testing"
	"time"

	"github.com/OpenRAE/lilrae/internal/process"
)

func stopProcess(t *testing.T, p *os.Process) {
	t.Helper()
	if err := p.Kill(); err != nil && !errors.Is(err, os.ErrProcessDone) {
		t.Errorf("fixture stop: %v", err)
	}
	if _, err := p.Wait(); err != nil {
		t.Logf("fixture wait: %v", err)
	}
}

func TestOwnedHelpersAndIndependentService(t *testing.T) {
	executable := binary(t)
	outside := exec.CommandContext(t.Context(), executable, "sleep") //nolint:gosec // G204: executable is the harmless fixture built into the test temporary directory.
	if err := outside.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { stopProcess(t, outside.Process) })
	for _, ending := range []string{"exit", "nonzero", "hang", "overflow", "cancel"} {
		t.Run(ending, func(t *testing.T) {
			runLifecycleCase(t, executable, ending)
			if err := independentAlive(outside.Process); err != nil {
				t.Fatalf("independent service affected: %v", err)
			}
		})
	}
}

func cancelWhenReady(ctx context.Context, ready string, cancel context.CancelFunc) {
	defer cancel()
	for {
		if _, err := os.Stat(ready); err == nil {
			return
		}
		select {
		case <-ctx.Done():
			return
		case <-time.After(time.Millisecond):
		}
	}
}

func runLifecycleCase(t *testing.T, executable, ending string) {
	t.Helper()
	dir := t.TempDir()
	ready := filepath.Join(dir, "helper.pid")
	mode := ending
	if ending == "cancel" {
		mode = "hang"
	}
	req := request(executable, dir, "spawn", "stubborn", mode, ready)
	req.MaxOutputBytes = 16
	if ending == "hang" {
		req.Timeout = 500 * time.Millisecond
	}
	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	if ending == "cancel" {
		go cancelWhenReady(ctx, ready, cancel)
	}
	started := time.Now()
	got, err := runner().Run(ctx, req)
	cleanup := checkEnding(t, ending, got, err)
	if len(cleanup.Residual) != 0 {
		t.Fatalf("cleanup = %v", cleanup)
	}
	if cleanup.Elapsed < runner().TerminationGrace || time.Since(started) > 4*time.Second {
		t.Fatalf("cleanup duration = %v", cleanup.Elapsed)
	}
}

func checkEnding(t *testing.T, ending string, got process.Result, err error) process.Cleanup {
	t.Helper()
	if ending == "exit" || ending == "nonzero" {
		if err != nil {
			t.Fatal(err)
		}
		if ending == "exit" && (got.ExitCode != 0 || string(got.Stdout) != "result") {
			t.Fatalf("result = %v", got)
		}
		if ending == "nonzero" && got.ExitCode != 7 {
			t.Fatalf("exit = %d", got.ExitCode)
		}
		return got.Cleanup
	}
	reason := ending
	if ending == "hang" {
		reason = "timeout"
	}
	return checkFailure(t, err, reason, 16).Cleanup
}

func TestNaturalExitAllowsGracefulHelperShutdown(t *testing.T) {
	executable := binary(t)
	dir := t.TempDir()
	ready := filepath.Join(dir, "helper.pid")
	req := request(executable, dir, "spawn", "graceful", "exit", ready)
	got, err := runner().Run(t.Context(), req)
	if err != nil {
		t.Fatal(err)
	}
	if got.Cleanup.Elapsed < 120*time.Millisecond {
		t.Fatal("did not wait for graceful shutdown")
	}
	if runtime.GOOS == "windows" && !got.Cleanup.GracefulStopRequested {
		if got.Cleanup.Elapsed < runner().ShutdownGrace {
			t.Fatal("headless cleanup skipped the grace period")
		}
		return
	}
	if _, err := os.Stat(ready + ".finished"); err != nil {
		t.Fatalf("helper did not finish shutdown: %v", err)
	}
}
