// Package projectstate names the layout of the .aptl project state
// directory, finds the lifecycle project root, and takes the lifecycle locks
// of core/lifecycle_guard.py.
//
// Ownership comes from the operating system lock on the open LockFile,
// never from the existence of a file or a stored process ID. An acquisition
// does not wait: a conflict returns an error that matches ErrBusy. A Go lock
// and a Python lock on one project exclude each other. A project path locates
// state. It does not authorize a credential read or a Docker operation
// (ADR-055).
package projectstate

import (
	"errors"
	"path/filepath"

	"github.com/OpenRAE/lilrae/internal/config"
	"github.com/OpenRAE/lilrae/internal/securefile"
)

// The layout of the project state directory, relative to the project root.
// Each later owner of a file below StateDir keeps its own location and mode
// rule.
const (
	// StateDir holds the project state.
	StateDir = ".aptl"
	// LifecycleDir holds the lifecycle state.
	LifecycleDir = ".aptl/lifecycle"
	// LockFile is the rendezvous file of the lifecycle locks. The package
	// never replaces, truncates, or removes it.
	LockFile = ".aptl/lifecycle/.lock"
	// TrialFence holds the owner of an unresolved trial. The runtime owner
	// writes it, and a new mutation lock reads it.
	TrialFence = ".aptl/lifecycle/trial-owner"
)

// The categories of a refused lock. An error of the package matches one of
// them with [errors.Is], and it keeps its cause for [errors.Is] and [errors.As].
var (
	// ErrBusy reports that another owner holds the lifecycle lock, or that
	// an unresolved trial owns the placement.
	ErrBusy = errors.New("projectstate: busy")
	// ErrUnavailable reports that the lock or the trial fence cannot be
	// opened or read safely.
	ErrUnavailable = errors.New("projectstate: unavailable")
)

// The texts of the refusals. They are the texts of the Python release, and
// they hold no path, native message, or fence value.
const (
	textBusy             = "another lifecycle owner is active for this project"
	textTrialBusy        = "an unresolved trial owns this placement"
	textUnavailable      = "safe lifecycle ownership is unavailable"
	textTrialUnavailable = "safe trial ownership is unavailable"
)

// refusal is a refused lock. Its text is one fixed text, and it unwraps to
// its category and its cause.
type refusal struct {
	text  string
	kind  error
	cause error
}

func (e *refusal) Error() string { return e.text }

func (e *refusal) Unwrap() []error {
	if e.cause == nil {
		return []error{e.kind}
	}
	return []error{e.kind, e.cause}
}

// ProjectRoot returns the lifecycle project root of dir: the nearest
// directory, from the resolved dir up, that holds aptl.json. With no such
// directory it returns the resolved dir. It changes nothing.
func ProjectRoot(dir string) (string, error) {
	candidate, err := securefile.Resolve(dir)
	if err != nil {
		return "", err
	}
	for current := candidate; ; current = filepath.Dir(current) {
		if _, ok := config.Find(current); ok {
			return current, nil
		}
		if filepath.Dir(current) == current {
			return candidate, nil
		}
	}
}

// OpenProjectRoot opens the resolved project root root, which comes from
// ProjectRoot or [securefile.Resolve]. It opens root as an entry of its parent,
// so it refuses a root that is a link or another reparse point, as the
// Windows lock of the Python release does. A volume root opens directly. The
// caller closes the Dir.
func OpenProjectRoot(root string) (dir *securefile.Dir, err error) {
	parent, name := filepath.Dir(root), filepath.Base(root)
	if parent == root {
		return securefile.OpenDir(root)
	}
	above, err := securefile.OpenDir(parent)
	if err != nil {
		return nil, err
	}
	dir, err = above.Subdir(name)
	err = errors.Join(err, above.Close())
	// Subdir returns no Dir with its error, so only a failed close of the
	// parent leaves a Dir to close.
	if err != nil && dir != nil {
		return nil, errors.Join(err, dir.Close())
	}
	return dir, err
}
