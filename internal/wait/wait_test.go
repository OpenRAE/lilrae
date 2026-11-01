package wait_test

import (
	"context"
	"errors"
	"slices"
	"testing"
	"testing/synctest"
	"time"

	"github.com/OpenRAE/lilrae/internal/wait"
)

// recorder is a probe that records the time of each call since start and
// reports ready from the call at index readyAt on, or never when it is
// negative. Each call takes cost.
type recorder struct {
	start   time.Time
	readyAt int
	cost    time.Duration
	calls   []time.Duration
}

func (r *recorder) ready(context.Context) bool {
	r.calls = append(r.calls, time.Since(r.start))
	time.Sleep(r.cost)
	return r.readyAt >= 0 && len(r.calls) > r.readyAt
}

func TestUntil(t *testing.T) {
	tests := []struct {
		name      string
		timeout   time.Duration
		interval  time.Duration
		readyAt   int
		cost      time.Duration
		wantCalls []time.Duration
		wantTook  time.Duration
		wantErr   error
	}{
		{"ready at once", time.Minute, 5 * time.Second, 0, 0, []time.Duration{0}, 0, nil},
		{"ready on the third call", time.Minute, 5 * time.Second, 2, 0, []time.Duration{0, 5 * time.Second, 10 * time.Second}, 10 * time.Second, nil},
		{
			"the last call runs at the deadline", 12 * time.Second, 5 * time.Second, -1, 0,
			[]time.Duration{0, 5 * time.Second, 10 * time.Second, 12 * time.Second}, 12 * time.Second, wait.ErrTimeout,
		},
		{
			"a slow probe shortens the last sleep", 12 * time.Second, 5 * time.Second, -1, 3 * time.Second,
			[]time.Duration{0, 8 * time.Second, 12 * time.Second}, 15 * time.Second, wait.ErrTimeout,
		},
		{"a zero timeout calls once", 0, time.Second, -1, 0, []time.Duration{0}, 0, wait.ErrTimeout},
	}
	for _, tt := range tests {
		synctest.Test(t, func(t *testing.T) {
			r := &recorder{start: time.Now(), readyAt: tt.readyAt, cost: tt.cost}
			took, err := wait.Until(t.Context(), tt.timeout, tt.interval, r.ready)
			if !errors.Is(err, tt.wantErr) || took != tt.wantTook || !slices.Equal(r.calls, tt.wantCalls) {
				t.Errorf("%s: Until = %v, %v with calls at %v; want %v, %v with calls at %v",
					tt.name, took, err, r.calls, tt.wantTook, tt.wantErr, tt.wantCalls)
			}
		})
	}
}

func TestUntilStopsWhenTheContextEnds(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		ctx, cancel := context.WithTimeout(t.Context(), 7*time.Second)
		defer cancel()
		r := &recorder{start: time.Now(), readyAt: -1}
		took, err := wait.Until(ctx, time.Minute, 5*time.Second, r.ready)
		if !errors.Is(err, context.DeadlineExceeded) || took != 7*time.Second || len(r.calls) != 2 {
			t.Errorf("Until = %v, %v with %d calls; want 7s, %v with 2 calls", took, err, len(r.calls), context.DeadlineExceeded)
		}
	})
}

func TestUntilDoesNotCallAfterTheContextEnded(t *testing.T) {
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	called := false
	if _, err := wait.Until(ctx, time.Minute, time.Second, func(context.Context) bool {
		called = true
		return true
	}); !errors.Is(err, context.Canceled) || called {
		t.Errorf("Until error = %v, called = %v; want %v and no call", err, called, context.Canceled)
	}
}

func TestUntilRejectsAnIntervalThatIsNotPositive(t *testing.T) {
	for _, interval := range []time.Duration{0, -time.Second} {
		if _, err := wait.Until(t.Context(), time.Minute, interval, func(context.Context) bool { return true }); err == nil {
			t.Errorf("Until with interval %v returned no error", interval)
		}
	}
}
