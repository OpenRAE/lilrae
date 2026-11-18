package projectstate

import (
	"context"
	"errors"
	"fmt"
	"io"
	"maps"
	"os"
	"sync"

	"github.com/OpenRAE/lilrae/internal/filelock"
	"github.com/OpenRAE/lilrae/internal/securefile"
)

// The trial fence holds 64 lowercase hexadecimal digits. A read of one more
// byte finds a longer value.
const (
	fenceLength    = 64
	fenceReadLimit = fenceLength + 1
)

// errInvalidFence is the cause of a refusal for a malformed trial fence.
var errInvalidFence = errors.New("projectstate: the trial fence is not 64 lowercase hexadecimal digits")

// leaseKey is the context key of the leases that a context holds.
type leaseKey struct{}

// leases maps a project root to the lease of a held mutation lock. A context
// holds one map, and a derived context gets a copy with one more lease.
type leases map[string]*lease

// lease is one held mutation lock and its count of references. A count of
// zero means that the lock is released, so a stale context cannot join it.
type lease struct {
	mu    sync.Mutex
	file  *os.File
	count int
}

// join adds one reference while the lease holds the lock.
func (l *lease) join() bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.count == 0 {
		return false
	}
	l.count++
	return true
}

// leave removes one reference. The last reference releases the lock.
func (l *lease) leave() error {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.count--
	if l.count > 0 {
		return nil
	}
	return release(l.file)
}

// Mutate holds the exclusive lifecycle lock of the project root of dir while
// fn runs, and returns the error of fn. fn gets that root and a context that
// carries the lock. A call of Mutate or MutatePlacement with that context,
// also from another goroutine, joins the lock while it is held. Another call
// gets an error that matches ErrBusy at once.
//
// A new lock reads the trial fence. When the fence names an owner other than
// trialOwner, Mutate returns an error that matches ErrBusy. An empty
// trialOwner names no owner. fn does not run after a refusal.
func Mutate(ctx context.Context, dir, trialOwner string, fn func(ctx context.Context, root string) error) error {
	root, err := ProjectRoot(dir)
	if err != nil {
		return unavailable(err)
	}
	return mutate(ctx, root, trialOwner, fn)
}

// MutatePlacement is Mutate for the exact root, with no search for
// aptl.json.
func MutatePlacement(ctx context.Context, root, trialOwner string, fn func(ctx context.Context, root string) error) error {
	resolved, err := securefile.Resolve(root)
	if err != nil {
		return unavailable(err)
	}
	return mutate(ctx, resolved, trialOwner, fn)
}

func mutate(ctx context.Context, root, trialOwner string, fn func(ctx context.Context, root string) error) (err error) {
	var held leases
	if value, ok := ctx.Value(leaseKey{}).(leases); ok {
		held = value
	}
	current := held[root]
	if current == nil || !current.join() {
		file, acquireErr := acquire(root, filelock.Exclusive, func(dir *securefile.Dir) error {
			return checkTrialOwner(dir, trialOwner)
		})
		if acquireErr != nil {
			return acquireErr
		}
		current = &lease{file: file, count: 1}
	}
	defer func() { err = errors.Join(err, current.leave()) }()
	next := maps.Clone(held)
	if next == nil {
		next = leases{}
	}
	next[root] = current
	return fn(context.WithValue(ctx, leaseKey{}, next), root)
}

// Observe holds the shared lifecycle lock of the project root of dir while
// fn runs, and returns the error of fn. Observers overlap, and they exclude
// a mutation. Observe does not join a held lock. Windows has no shared lock,
// so there Observe returns an error that matches both ErrBusy, as in the
// Python release, and errors.ErrUnsupported.
func Observe(dir string, fn func(root string) error) (err error) {
	root, err := ProjectRoot(dir)
	if err != nil {
		return unavailable(err)
	}
	file, err := acquire(root, filelock.Shared, nil)
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, release(file)) }()
	return fn(root)
}

// acquire opens the lock file below root, locks it in mode at once, and runs
// check with the opened root. It releases the lock after each failure.
func acquire(root string, mode filelock.Mode, check func(*securefile.Dir) error) (file *os.File, err error) {
	dir, err := OpenProjectRoot(root)
	if err != nil {
		return nil, unavailable(err)
	}
	defer func() {
		if closeErr := dir.Close(); closeErr != nil {
			if err == nil {
				err = unavailable(closeErr)
			} else {
				err = errors.Join(err, closeErr)
			}
		}
		if err != nil && file != nil {
			err = errors.Join(err, release(file))
			file = nil
		}
	}()
	file, err = lockFile(dir, mode)
	if err != nil || check == nil {
		return file, err
	}
	return file, check(dir)
}

// lockFile opens the lock file and locks it in mode at once.
func lockFile(dir *securefile.Dir, mode filelock.Mode) (*os.File, error) {
	file, err := dir.OpenLockFile(LockFile)
	if err != nil {
		return nil, unavailable(err)
	}
	if prepareErr := prepareLockFile(file); prepareErr != nil {
		return nil, unavailable(errors.Join(prepareErr, file.Close()))
	}
	if lockErr := filelock.TryLock(file, mode); lockErr != nil {
		cause := errors.Join(lockErr, file.Close())
		// Python reports a missing shared lock as busy too.
		if errors.Is(lockErr, filelock.ErrBusy) || errors.Is(lockErr, errors.ErrUnsupported) {
			return nil, &refusal{text: textBusy, kind: ErrBusy, cause: cause}
		}
		return nil, unavailable(cause)
	}
	return file, nil
}

// unavailable reports that the lock cannot be taken safely because of cause.
func unavailable(cause error) error {
	return &refusal{text: textUnavailable, kind: ErrUnavailable, cause: cause}
}

// release unlocks and closes a held lock file.
func release(file *os.File) error {
	return errors.Join(filelock.Unlock(file), file.Close())
}

// checkTrialOwner refuses the lock when the trial fence names an owner other
// than owner, or when the fence is malformed or unsafe. An absent fence
// names no owner.
func checkTrialOwner(dir *securefile.Dir, owner string) error {
	retained, err := readTrialFence(dir)
	switch {
	case securefile.IsReason(err, securefile.ReasonNotFound):
		return nil
	case err != nil:
		return &refusal{text: textTrialUnavailable, kind: ErrUnavailable, cause: err}
	case !validTrialOwner(retained):
		return &refusal{text: textTrialUnavailable, kind: ErrUnavailable, cause: errInvalidFence}
	case string(retained) != owner:
		return &refusal{text: textTrialBusy, kind: ErrBusy}
	}
	return nil
}

// readTrialFence reads at most fenceReadLimit bytes of the trial fence,
// without following a link.
func readTrialFence(dir *securefile.Dir) (retained []byte, err error) {
	file, err := dir.Open(TrialFence)
	if err != nil {
		return nil, err
	}
	defer func() { err = errors.Join(err, file.Close()) }()
	retained, err = io.ReadAll(io.LimitReader(file, fenceReadLimit))
	if err != nil {
		return nil, fmt.Errorf("projectstate: read %s: %w", TrialFence, err)
	}
	return retained, nil
}

// validTrialOwner reports whether value is 64 lowercase hexadecimal digits.
func validTrialOwner(value []byte) bool {
	if len(value) != fenceLength {
		return false
	}
	for _, c := range value {
		if (c < '0' || c > '9') && (c < 'a' || c > 'f') {
			return false
		}
	}
	return true
}
