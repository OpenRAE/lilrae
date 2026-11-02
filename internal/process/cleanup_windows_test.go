package process

import (
	"os"
	"os/signal"
	"slices"
	"testing"
	"time"

	"golang.org/x/sys/windows"
)

// TestWindowsBlockedProcess is the finite child of the cleanup-permission test.
func TestWindowsBlockedProcess(t *testing.T) {
	if os.Getenv("LILRAE_PROCESS_TEST_SLEEP") != "1" {
		return
	}
	interrupts := make(chan os.Signal, 4)
	signal.Notify(interrupts, os.Interrupt)
	defer signal.Stop(interrupts)
	if _, err := os.Stdout.WriteString("ready"); err != nil {
		t.Fatal(err)
	}
	time.Sleep(time.Minute)
}

func TestWindowsReportsDeniedCleanup(t *testing.T) {
	exe, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	req := Request{Argv: []string{exe, "-test.run=^TestWindowsBlockedProcess$"}, Dir: t.TempDir(), Env: []string{"LILRAE_PROCESS_TEST_SLEEP=1"}}
	x, err := openExchange(128)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(x.close)
	c, err := launch(req, x.childFiles())
	x.closeChildFiles()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(c.close)
	x.sendInput(nil)
	ready := await(t.Context(), 10*time.Second, func() bool {
		if pumpErr := x.pump(true, false); pumpErr != nil {
			return false
		}
		return string(x.stdout.data) == "ready"
	})
	if !ready {
		t.Fatal("child did not become ready")
	}
	observer := duplicateHandle(t, c.process, 0, windows.DUPLICATE_SAME_ACCESS)
	t.Cleanup(func() { releaseObservedChild(t, observer) })
	// JOB_OBJECT_QUERY permits observations but excludes JOB_OBJECT_TERMINATE.
	// This is a real access-denied condition, not a substituted Windows call.
	queryOnly := duplicateHandle(t, c.job, 0x0004, 0)
	if closeErr := windows.CloseHandle(c.job); closeErr != nil {
		t.Fatal(closeErr)
	}
	c.job = queryOnly
	r := Runner{TerminationGrace: 30 * time.Millisecond, ReapTimeout: 40 * time.Millisecond, ReleaseTimeout: 40 * time.Millisecond}
	started := time.Now()
	report := r.cleanup(t.Context(), c, x, r.TerminationGrace)
	for _, want := range []Residual{ProcessRunning, GroupUnconfirmed, StreamsHeld} {
		if !slices.Contains(report.Residual, want) {
			t.Fatalf("cleanup = %v, missing %s", report, want)
		}
	}
	if time.Since(started) > 3*time.Second {
		t.Fatal("denied cleanup exceeded its bounds")
	}
	// The final close of the owned job still invokes kill-on-close.
	state, waitErr := windows.WaitForSingleObject(observer, 3000)
	if waitErr != nil || state != windows.WAIT_OBJECT_0 {
		t.Fatalf("job close did not stop the child: %d, %v", state, waitErr)
	}
}

func duplicateHandle(t *testing.T, handle windows.Handle, access, options uint32) windows.Handle {
	t.Helper()
	var duplicate windows.Handle
	if err := windows.DuplicateHandle(windows.CurrentProcess(), handle, windows.CurrentProcess(), &duplicate, access, false, options); err != nil {
		t.Fatal(err)
	}
	return duplicate
}

func releaseObservedChild(t *testing.T, handle windows.Handle) {
	t.Helper()
	if err := windows.TerminateProcess(handle, 1); err != nil {
		t.Logf("child already ended or could not be stopped: %v", err)
	}
	if _, err := windows.WaitForSingleObject(handle, 3000); err != nil {
		t.Errorf("child wait: %v", err)
	}
	if err := windows.CloseHandle(handle); err != nil {
		t.Errorf("observer close: %v", err)
	}
}
