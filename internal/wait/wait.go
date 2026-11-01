// Package wait waits for a condition until a deadline.
package wait

import (
	"context"
	"errors"
	"time"
)

var (
	// ErrTimeout reports that the condition did not hold before the deadline.
	ErrTimeout = errors.New("wait: the condition did not hold before the deadline")

	errInterval = errors.New("wait: the interval is not positive")
)

// Until calls ready until it returns true, the timeout passes, or ctx ends.
// It calls ready at once and then once each interval. It never sleeps past
// the deadline, so the last call runs at the deadline. ready gets ctx and
// bounds its own attempt. Until returns the time that the wait took, and
// ErrTimeout or the error of ctx when ready did not return true.
func Until(ctx context.Context, timeout, interval time.Duration, ready func(context.Context) bool) (time.Duration, error) {
	if interval <= 0 {
		return 0, errInterval
	}
	start := time.Now()
	deadline := start.Add(timeout)
	for {
		if err := ctx.Err(); err != nil {
			return time.Since(start), err
		}
		if ready(ctx) {
			return time.Since(start), nil
		}
		now := time.Now()
		if !now.Before(deadline) {
			return now.Sub(start), ErrTimeout
		}
		timer := time.NewTimer(min(interval, deadline.Sub(now)))
		select {
		case <-ctx.Done():
			timer.Stop()
			return time.Since(start), ctx.Err()
		case <-timer.C:
		}
	}
}
