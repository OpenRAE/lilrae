package projectstate

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"sync"
	"testing"

	"github.com/OpenRAE/lilrae/internal/securefile"
)

// newProject returns a new resolved directory that holds aptl.json.
func newProject(t *testing.T) string {
	t.Helper()
	root := resolvedTempDir(t)
	writeFile(t, filepath.Join(root, "aptl.json"), "{}")
	return root
}

// resolvedTempDir returns a new temporary directory with each link resolved,
// as ProjectRoot returns it. On macOS the temporary directory is below a
// link.
func resolvedTempDir(t *testing.T) string {
	t.Helper()
	root, err := securefile.Resolve(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	return root
}

func writeFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
}

func mkdir(t *testing.T, path string) {
	t.Helper()
	if err := os.MkdirAll(path, 0o700); err != nil {
		t.Fatal(err)
	}
}

func exists(t *testing.T, path string) bool {
	t.Helper()
	_, err := os.Lstat(path)
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		t.Fatal(err)
	}
	return err == nil
}

// noop is a callback that does nothing.
func noop(context.Context, string) error { return nil }

// mustNotRun is a callback that fails the test when it runs.
func mustNotRun(t *testing.T) func(context.Context, string) error {
	t.Helper()
	return func(context.Context, string) error {
		t.Error("the callback ran after a refusal")
		return nil
	}
}

// wantRefusal checks that err matches kind and has the fixed text.
func wantRefusal(t *testing.T, err, kind error, text string) {
	t.Helper()
	if !errors.Is(err, kind) {
		t.Fatalf("error = %v, want an error that matches %v", err, kind)
	}
	if err.Error() != text {
		t.Errorf("error text = %q, want %q", err.Error(), text)
	}
}

func TestProjectRootFindsTheNearestConfigOwner(t *testing.T) {
	root := newProject(t)
	nested := filepath.Join(root, "a", "b")
	mkdir(t, nested)
	for _, dir := range []string{root, nested, filepath.Join(nested, "missing", "deeper")} {
		got, err := ProjectRoot(dir)
		if err != nil {
			t.Fatal(err)
		}
		if got != root {
			t.Errorf("ProjectRoot(%q) = %q, want %q", dir, got, root)
		}
	}
}

func TestProjectRootPrefersTheNearestOwner(t *testing.T) {
	outer := newProject(t)
	inner := filepath.Join(outer, "inner")
	writeFile(t, filepath.Join(inner, "aptl.json"), "{}")
	got, err := ProjectRoot(filepath.Join(inner, "work"))
	if err != nil {
		t.Fatal(err)
	}
	if got != inner {
		t.Errorf("ProjectRoot() = %q, want the nearest owner %q", got, inner)
	}
}

func TestProjectRootWithoutConfigIsTheResolvedPath(t *testing.T) {
	dir := filepath.Join(resolvedTempDir(t), "work")
	mkdir(t, dir)
	got, err := ProjectRoot(dir)
	if err != nil {
		t.Fatal(err)
	}
	if got != dir {
		t.Errorf("ProjectRoot() = %q, want %q", got, dir)
	}
}

func TestProjectRootIgnoresADirectoryNamedAptlJSON(t *testing.T) {
	dir := resolvedTempDir(t)
	mkdir(t, filepath.Join(dir, "aptl.json"))
	got, err := ProjectRoot(dir)
	if err != nil {
		t.Fatal(err)
	}
	if got != dir {
		t.Errorf("ProjectRoot() = %q, want %q", got, dir)
	}
}

func TestProjectRootChangesNothing(t *testing.T) {
	root := newProject(t)
	if _, err := ProjectRoot(root); err != nil {
		t.Fatal(err)
	}
	if exists(t, filepath.Join(root, StateDir)) {
		t.Error("ProjectRoot created the state directory")
	}
}

func TestMutateAnchorsADescendantToTheConfigOwner(t *testing.T) {
	root := newProject(t)
	descendant := filepath.Join(root, "nested", "work")
	mkdir(t, descendant)
	var got string
	err := Mutate(t.Context(), descendant, "", func(_ context.Context, r string) error {
		got = r
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if got != root {
		t.Errorf("Mutate gave the root %q, want %q", got, root)
	}
	if !exists(t, filepath.Join(root, filepath.FromSlash(LockFile))) {
		t.Error("the lock file is not below the config owner")
	}
	if exists(t, filepath.Join(descendant, StateDir)) {
		t.Error("Mutate created state below the descendant")
	}
}

func TestMutatePlacementLocksTheExactRoot(t *testing.T) {
	parent := newProject(t)
	placement := filepath.Join(parent, "placement")
	mkdir(t, placement)
	var got string
	err := MutatePlacement(t.Context(), placement, "", func(_ context.Context, r string) error {
		got = r
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if got != placement {
		t.Errorf("MutatePlacement gave the root %q, want %q", got, placement)
	}
	if !exists(t, filepath.Join(placement, filepath.FromSlash(LockFile))) {
		t.Error("the lock file is not below the placement")
	}
	if exists(t, filepath.Join(parent, StateDir)) {
		t.Error("MutatePlacement searched for the config owner")
	}
}

func TestMutateReturnsTheErrorOfTheCallback(t *testing.T) {
	root := newProject(t)
	want := errors.New("callback failed")
	err := Mutate(t.Context(), root, "", func(context.Context, string) error { return want })
	if !errors.Is(err, want) {
		t.Fatalf("Mutate() = %v, want %v", err, want)
	}
	if err := Mutate(t.Context(), root, "", noop); err != nil {
		t.Fatalf("Mutate() after a failed callback = %v, want nil", err)
	}
}

// holdWhile runs Mutate on root in a goroutine with the test context, and
// runs inside in its callback with the derived context. It returns after
// inside returns, while the lock is held, with a function that releases the
// lock and returns the error of Mutate. inside runs on another goroutine, so
// it reports with [testing.T.Error].
func holdWhile(t *testing.T, root string, inside func(ctx context.Context)) (release func() error) {
	t.Helper()
	held, done := make(chan struct{}), make(chan struct{})
	result := make(chan error, 1)
	go func() {
		result <- Mutate(t.Context(), root, "", func(ctx context.Context, _ string) error {
			inside(ctx)
			close(held)
			<-done
			return nil
		})
	}()
	select {
	case <-held:
	case err := <-result:
		t.Fatalf("Mutate() = %v, want nil", err)
	}
	release = sync.OnceValue(func() error {
		close(done)
		return <-result
	})
	t.Cleanup(func() {
		if err := release(); err != nil {
			t.Error(err)
		}
	})
	return release
}

func nothing(context.Context) {}

func TestANestedMutationJoinsTheHeldLock(t *testing.T) {
	root := newProject(t)
	release := holdWhile(t, root, func(ctx context.Context) {
		if err := Mutate(ctx, root, "", noop); err != nil {
			t.Errorf("a nested Mutate() = %v, want nil", err)
		}
		if err := MutatePlacement(ctx, root, "", noop); err != nil {
			t.Errorf("a nested MutatePlacement() = %v, want nil", err)
		}
	})
	// The nested exits left the outer lock held.
	wantRefusal(t, Mutate(t.Context(), root, "", mustNotRun(t)), ErrBusy, textBusy)
	if err := release(); err != nil {
		t.Fatal(err)
	}
	if err := Mutate(t.Context(), root, "", noop); err != nil {
		t.Fatalf("Mutate() after the outer exit = %v, want nil", err)
	}
}

func TestAnUnrelatedGoroutineGetsBusy(t *testing.T) {
	root := newProject(t)
	holdWhile(t, root, nothing)
	wantRefusal(t, Mutate(t.Context(), root, "", mustNotRun(t)), ErrBusy, textBusy)
	wantRefusal(t, MutatePlacement(t.Context(), root, "", mustNotRun(t)), ErrBusy, textBusy)
}

func TestAGoroutineWithTheContextJoinsTheLock(t *testing.T) {
	root := newProject(t)
	err := Mutate(t.Context(), root, "", func(ctx context.Context, _ string) error {
		result := make(chan error)
		go func() { result <- Mutate(ctx, root, "", noop) }()
		return <-result
	})
	if err != nil {
		t.Fatalf("Mutate() from a goroutine with the context = %v, want nil", err)
	}
}

func TestAStaleContextCannotReviveAReleasedLock(t *testing.T) {
	root := newProject(t)
	contexts := make(chan context.Context, 1)
	if err := Mutate(t.Context(), root, "", func(ctx context.Context, _ string) error {
		contexts <- ctx
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	stale := <-contexts
	release := holdWhile(t, root, nothing)
	wantRefusal(t, Mutate(stale, root, "", mustNotRun(t)), ErrBusy, textBusy)
	if err := release(); err != nil {
		t.Fatal(err)
	}
	if err := Mutate(stale, root, "", noop); err != nil {
		t.Errorf("Mutate() with a stale context and no holder = %v, want nil", err)
	}
}

func TestProjectsAreIndependent(t *testing.T) {
	first, second := newProject(t), newProject(t)
	holdWhile(t, first, func(ctx context.Context) {
		// The context carries only the lock of first.
		if err := Mutate(ctx, second, "", noop); err != nil {
			t.Errorf("Mutate() of another project = %v, want nil", err)
		}
	})
	holdWhile(t, second, nothing)
	wantRefusal(t, Mutate(t.Context(), first, "", mustNotRun(t)), ErrBusy, textBusy)
	wantRefusal(t, Mutate(t.Context(), second, "", mustNotRun(t)), ErrBusy, textBusy)
}

func TestTheTrialFence(t *testing.T) {
	owner := "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
	other := "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
	tests := []struct {
		name, fence, owner string
		absent             bool
		kind               error
		text               string
	}{
		{name: "absent", absent: true},
		{name: "absent with an owner", absent: true, owner: owner},
		{name: "the same owner", fence: owner, owner: owner},
		{name: "another owner", fence: other, owner: owner, kind: ErrBusy, text: textTrialBusy},
		{name: "an owner and no caller owner", fence: owner, kind: ErrBusy, text: textTrialBusy},
		{name: "upper case", fence: "0123456789ABCDEF0123456789abcdef0123456789abcdef0123456789abcdef", kind: ErrUnavailable, text: textTrialUnavailable},
		{name: "one digit short", fence: owner[1:], owner: owner[1:], kind: ErrUnavailable, text: textTrialUnavailable},
		{name: "one byte long", fence: owner + "0", owner: owner, kind: ErrUnavailable, text: textTrialUnavailable},
		{name: "a final line feed", fence: owner + "\n", owner: owner, kind: ErrUnavailable, text: textTrialUnavailable},
		{name: "empty", fence: "", kind: ErrUnavailable, text: textTrialUnavailable},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			root := newProject(t)
			fence := filepath.Join(root, filepath.FromSlash(TrialFence))
			if !tt.absent {
				writeFile(t, fence, tt.fence)
			}
			if tt.kind == nil {
				if err := Mutate(t.Context(), root, tt.owner, noop); err != nil {
					t.Fatalf("Mutate() = %v, want nil", err)
				}
				return
			}
			wantRefusal(t, Mutate(t.Context(), root, tt.owner, mustNotRun(t)), tt.kind, tt.text)
			wantReleasedAfterRefusal(t, root, fence, tt.owner)
		})
	}
}

// wantReleasedAfterRefusal checks that a refusal for the fence released the
// lock.
func wantReleasedAfterRefusal(t *testing.T, root, fence, owner string) {
	t.Helper()
	if err := os.Remove(fence); err != nil {
		t.Fatal(err)
	}
	if err := Mutate(t.Context(), root, owner, noop); err != nil {
		t.Fatalf("Mutate() after the refusal = %v, want nil", err)
	}
}

func TestAMalformedFenceKeepsItsCause(t *testing.T) {
	root := newProject(t)
	writeFile(t, filepath.Join(root, filepath.FromSlash(TrialFence)), "invalid")
	if err := Mutate(t.Context(), root, "", mustNotRun(t)); !errors.Is(err, errInvalidFence) {
		t.Fatalf("Mutate() = %v, want an error that matches errInvalidFence", err)
	}
}

func TestADirectoryAtTheFenceIsUnavailable(t *testing.T) {
	root := newProject(t)
	mkdir(t, filepath.Join(root, filepath.FromSlash(TrialFence)))
	wantRefusal(t, Mutate(t.Context(), root, "", mustNotRun(t)), ErrUnavailable, textTrialUnavailable)
}

func TestANestedMutationDoesNotReadTheFenceAgain(t *testing.T) {
	root := newProject(t)
	other := "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
	err := Mutate(t.Context(), root, "", func(ctx context.Context, _ string) error {
		writeFile(t, filepath.Join(root, filepath.FromSlash(TrialFence)), other)
		return Mutate(ctx, root, "", noop)
	})
	if err != nil {
		t.Fatalf("a nested Mutate() after a new fence = %v, want nil", err)
	}
	wantRefusal(t, Mutate(t.Context(), root, "", mustNotRun(t)), ErrBusy, textTrialBusy)
}

func TestADirectoryAtTheLockPathIsUnavailable(t *testing.T) {
	root := newProject(t)
	mkdir(t, filepath.Join(root, filepath.FromSlash(LockFile)))
	wantRefusal(t, Mutate(t.Context(), root, "", mustNotRun(t)), ErrUnavailable, textUnavailable)
	if err := Observe(root, func(string) error {
		t.Error("the callback ran after a refusal")
		return nil
	}); !errors.Is(err, ErrUnavailable) {
		t.Errorf("Observe() = %v, want an error that matches ErrUnavailable", err)
	}
}

func TestAMissingRootIsUnavailable(t *testing.T) {
	root := filepath.Join(resolvedTempDir(t), "missing")
	err := MutatePlacement(t.Context(), root, "", mustNotRun(t))
	wantRefusal(t, err, ErrUnavailable, textUnavailable)
	if exists(t, root) {
		t.Error("MutatePlacement created the missing root")
	}
}

func TestOpenProjectRootOpensTheRoot(t *testing.T) {
	root := newProject(t)
	dir, err := OpenProjectRoot(root)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if closeErr := dir.Close(); closeErr != nil {
			t.Error(closeErr)
		}
	})
	data, err := dir.ReadFile("aptl.json")
	if err != nil || string(data) != "{}" {
		t.Errorf("ReadFile(aptl.json) = %q, %v, want {}", data, err)
	}
}

func TestOpenProjectRootOpensAVolumeRoot(t *testing.T) {
	volume := filepath.VolumeName(resolvedTempDir(t)) + string(filepath.Separator)
	dir, err := OpenProjectRoot(volume)
	if err != nil {
		t.Fatalf("OpenProjectRoot(%q) = %v, want nil", volume, err)
	}
	if err := dir.Close(); err != nil {
		t.Fatal(err)
	}
}
