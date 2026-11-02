// Package process runs local argument arrays within time and output limits.
// Cleanup owns the invocation's process group, not independent services.
package process

import (
	"context"
	"errors"
	"fmt"
	"path/filepath"
	"strings"
	"time"
)

// Supervision failures have safe fixed categories. Native errors can contain
// arguments, environment values, and paths, and must not escape this package.
var (
	ErrInvalid  = errors.New("invalid process request")
	ErrLaunch   = errors.New("process launch failed")
	ErrIO       = errors.New("process pipe or control operation failed")
	ErrOverflow = errors.New("process output exceeded the combined limit")
	ErrResidue  = errors.New("process cleanup left residue")
)

// Request supplies an admitted executable and explicit invocation values.
// Argv[0] and Dir must be absolute paths. Env never inherits the host environment.
// Secrets belong in Stdin or Env, never in Argv.
type Request struct {
	Argv           []string
	Dir            string
	Env            []string
	Stdin          []byte
	Timeout        time.Duration
	MaxOutputBytes int
}

// String withholds request content from diagnostic formatting.
func (r Request) String() string { return "process request (content withheld)" }

// GoString withholds request content from Go-syntax formatting.
func (r Request) GoString() string { return r.String() }

// Runner supplies cleanup bounds. Each zero field uses the reference default.
// Negative values are invalid. A Runner can be used concurrently.
type Runner struct {
	TerminationGrace time.Duration
	ShutdownGrace    time.Duration
	ReapTimeout      time.Duration
	ReleaseTimeout   time.Duration
}

// Residual identifies an observation, not proof that a helper is live.
type Residual string

// Cleanup observations retain the distinctions of the Python runner.
const (
	ProcessRunning   Residual = "process-not-reaped"
	StreamsHeld      Residual = "output-streams-held"
	GroupUnconfirmed Residual = "process-group-cleanup-unconfirmed"
)

// Cleanup reports separately timed cleanup without process content.
// ProcessGroup is a Unix PGID or the Windows root process ID of the owned job.
type Cleanup struct {
	ProcessGroup int
	Elapsed      time.Duration
	Residual     []Residual
	// GracefulStopRequested reports whether a cooperative stop was accepted.
	// Windows console control can be unavailable in a headless session.
	GracefulStopRequested bool
}

// Result contains sensitive output only after successful supervision.
// A nonzero ExitCode remains a result when cleanup succeeds.
type Result struct {
	ExitCode int
	Stdout   []byte
	Stderr   []byte
	Cleanup  Cleanup
}

// String describes a result without disclosing its output.
func (r Result) String() string {
	return fmt.Sprintf("process exit %d; stdout %d bytes; stderr %d bytes; cleanup %v", r.ExitCode, len(r.Stdout), len(r.Stderr), r.Cleanup)
}

// GoString withholds output from Go-syntax formatting.
func (r Result) GoString() string { return r.String() }

// Error withholds captured output and preserves the initiating category and
// cleanup observations. Unwrap exposes only a safe sentinel or context error.
type Error struct {
	Reason      error
	Cleanup     Cleanup
	StdoutBytes int
	StderrBytes int
}

// Error describes only safe failure facts.
func (e *Error) Error() string {
	return fmt.Sprintf("%v; withheld stdout %d bytes, stderr %d bytes; cleanup %v", e.Reason, e.StdoutBytes, e.StderrBytes, e.Cleanup)
}

// GoString withholds output from Go-syntax formatting.
func (e *Error) GoString() string { return e.Error() }

// Unwrap permits category checks with errors.Is.
func (e *Error) Unwrap() error { return e.Reason }

// Run executes one invocation and cleans up its owned group on every outcome.
// The execution deadline starts before launch. Cleanup has separate bounds.
// Kernel launch calls are synchronous and cannot be portably interrupted.
func (r Runner) Run(ctx context.Context, req Request) (Result, error) {
	r = r.defaults()
	if !r.valid(req) {
		return Result{}, ErrInvalid
	}
	ctx, cancel := context.WithTimeout(ctx, req.Timeout)
	defer cancel()
	if err := ctx.Err(); err != nil {
		return Result{}, fmt.Errorf("process: %w", err)
	}
	x, err := openExchange(req.MaxOutputBytes)
	if err != nil {
		return Result{}, err
	}
	c, err := launch(req, x.childFiles())
	x.closeChildFiles()
	if err != nil {
		x.close()
		return Result{}, ErrLaunch
	}
	x.sendInput(req.Stdin)
	reason := supervise(ctx, c, x)
	grace := r.TerminationGrace
	if exited, err := c.exited(); err == nil && exited {
		grace = r.ShutdownGrace
	}
	cleanup := r.cleanup(context.WithoutCancel(ctx), c, x, grace)
	if reason == nil && len(cleanup.Residual) > 0 {
		reason = ErrResidue
	}
	if reason != nil {
		return Result{}, &Error{Reason: reason, Cleanup: cleanup, StdoutBytes: len(x.stdout.data), StderrBytes: len(x.stderr.data)}
	}
	return Result{ExitCode: c.exitCode, Stdout: x.stdout.data, Stderr: x.stderr.data, Cleanup: cleanup}, nil
}

func (r Runner) defaults() Runner {
	if r.TerminationGrace == 0 {
		r.TerminationGrace = time.Second
	}
	if r.ShutdownGrace == 0 {
		r.ShutdownGrace = 20 * time.Second
	}
	if r.ReapTimeout == 0 {
		r.ReapTimeout = time.Second
	}
	if r.ReleaseTimeout == 0 {
		r.ReleaseTimeout = time.Second
	}
	return r
}

func (r Runner) valid(req Request) bool {
	if req.Timeout <= 0 || req.MaxOutputBytes <= 0 || len(req.Argv) == 0 {
		return false
	}
	if r.TerminationGrace <= 0 || r.ShutdownGrace <= 0 || r.ReapTimeout <= 0 || r.ReleaseTimeout <= 0 {
		return false
	}
	if !filepath.IsAbs(req.Argv[0]) || !filepath.IsAbs(req.Dir) {
		return false
	}
	for _, s := range append([]string{req.Dir}, req.Argv...) {
		if strings.ContainsRune(s, 0) {
			return false
		}
	}
	keys := make(map[string]bool, len(req.Env))
	for _, entry := range req.Env {
		key, _, found := strings.Cut(entry, "=")
		key = environmentKey(key)
		if !found || key == "" || strings.ContainsRune(entry, 0) || keys[key] {
			return false
		}
		keys[key] = true
	}
	return true
}

const pollInterval = 5 * time.Millisecond

func supervise(ctx context.Context, c *child, x *exchange) error {
	for {
		if err := ctx.Err(); err != nil {
			return fmt.Errorf("process: %w", err)
		}
		exited, err := c.exited()
		if err != nil {
			return ErrIO
		}
		if exited {
			return x.pump(true, true)
		}
		if err := x.pump(true, false); err != nil {
			return err
		}
		timer := time.NewTimer(pollInterval)
		select {
		case <-ctx.Done():
			timer.Stop()
			return fmt.Errorf("process: %w", ctx.Err())
		case <-timer.C:
		}
	}
}

func (r Runner) cleanup(ctx context.Context, c *child, x *exchange, grace time.Duration) Cleanup {
	started := time.Now()
	x.stopInput()
	graceful := false
	// Ownership remains reserved until the final possible signal. A failed
	// observation cannot establish that the group is empty.
	if members, err := c.members(); err != nil || members {
		graceful = c.stop(false)
		ended := await(ctx, grace, func() bool {
			x.discard()
			members, err := c.members()
			return err == nil && !members
		})
		if !ended {
			c.stop(true)
		}
	}
	var residual []Residual
	reaped, gone := false, false
	await(ctx, r.ReapTimeout, func() bool {
		x.discard()
		reaped = c.reap()
		goneNow, err := c.gone()
		gone = err == nil && goneNow
		return reaped && gone
	})
	if !reaped {
		residual = append(residual, ProcessRunning)
	}
	if !gone {
		residual = append(residual, GroupUnconfirmed)
	}
	if !await(ctx, r.ReleaseTimeout, func() bool {
		x.discard()
		return x.stdout.closed && x.stderr.closed
	}) {
		residual = append(residual, StreamsHeld)
	}
	x.close()
	c.close()
	return Cleanup{ProcessGroup: c.pid, Elapsed: time.Since(started), Residual: residual, GracefulStopRequested: graceful}
}

func await(ctx context.Context, timeout time.Duration, probe func() bool) bool {
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	for {
		if probe() {
			return true
		}
		timer := time.NewTimer(pollInterval)
		select {
		case <-ctx.Done():
			timer.Stop()
			return false
		case <-timer.C:
		}
	}
}
