//go:build linux || darwin

package securefile

import (
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"slices"
	"testing"
	"time"

	"golang.org/x/sys/unix"
)

// requireModes stops a test that needs the kernel to apply mode bits.
func requireModes(t *testing.T) {
	t.Helper()
	if os.Geteuid() == 0 {
		t.Skip("root passes each mode check, so the test cannot see a refusal")
	}
}

// chmodPath sets the mode of name below root, and restores 0700 at the end of
// the test so that the cleanup can remove the tree.
func chmodPath(t *testing.T, root, name string, mode fs.FileMode) {
	t.Helper()
	path := filepath.Join(root, name)
	if err := os.Chmod(path, mode); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := os.Chmod(path, 0o700); err != nil && !errors.Is(err, fs.ErrNotExist) { //nolint:gosec // G302: 0700 gives the owner back a test directory, so that the cleanup can remove it.
			t.Error(err)
		}
	})
}

// modeOf returns the permission, sticky, and setgid bits of name below root.
func modeOf(t *testing.T, root, name string) fs.FileMode {
	t.Helper()
	info, err := os.Lstat(filepath.Join(root, name))
	if err != nil {
		t.Fatal(err)
	}
	return info.Mode() & (fs.ModePerm | fs.ModeSticky | fs.ModeSetgid)
}

func TestReadsThroughAnExecuteOnlyDirectory(t *testing.T) {
	requireModes(t)
	root, d := newTree(t)
	writeFile(t, root, "x/y/f", "through")
	chmodPath(t, root, "x", 0o111)
	got, err := d.ReadFile("x/y/f")
	if err != nil || string(got) != "through" {
		t.Errorf("ReadFile() = %q, %v, want the content through the execute-only directory", got, err)
	}
	_, err = d.ReadDirNames("x")
	wantReason(t, err, ReasonOpenFailed)
}

func TestADirectoryWithoutSearchIsOpenFailed(t *testing.T) {
	requireModes(t)
	root, d := newTree(t)
	writeFile(t, root, "locked/f", "x")
	chmodPath(t, root, "locked", 0o600)
	_, err := d.ReadFile("locked/f")
	wantReason(t, err, ReasonOpenFailed)
	if !errors.Is(err, unix.EACCES) {
		t.Errorf("error = %v, want the cause EACCES", err)
	}
}

func TestAFIFOLeafNeverBlocks(t *testing.T) {
	root, d := newTree(t)
	if err := unix.Mkfifo(filepath.Join(root, "fifo"), 0o600); err != nil {
		t.Fatal(err)
	}
	done := make(chan error, 3)
	go func() {
		_, err := d.Open("fifo")
		done <- err
		_, err = d.ReadFile("fifo")
		done <- err
		done <- d.ReplacePrivate("fifo", []byte("x"))
	}()
	for range 3 {
		select {
		case err := <-done:
			wantReason(t, err, ReasonNotRegularFile)
		case <-time.After(10 * time.Second):
			t.Fatal("an operation on a FIFO blocked")
		}
	}
}

func TestOpenReturnsABlockingFile(t *testing.T) {
	root, d := newTree(t)
	writeFile(t, root, "f", "x")
	file, err := d.Open("f")
	if err != nil {
		t.Fatal(err)
	}
	closeOnCleanup(t, file)
	raw, err := file.SyscallConn()
	if err != nil {
		t.Fatal(err)
	}
	var flags int
	var flagErr error
	if err := raw.Control(func(fd uintptr) { flags, flagErr = unix.FcntlInt(fd, unix.F_GETFL, 0) }); err != nil || flagErr != nil {
		t.Fatal(err, flagErr)
	}
	if flags&unix.O_NONBLOCK != 0 {
		t.Error("the opened file keeps O_NONBLOCK")
	}
}

func TestCreatedFilesAndDirectoriesArePrivate(t *testing.T) {
	root, d := newTree(t)
	if err := d.CreateOnce("c1/c2/f", []byte("x")); err != nil {
		t.Fatal(err)
	}
	if err := d.Replace("r1/f", []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	sub, err := d.MakeSubdir("m1/m2")
	if err != nil {
		t.Fatal(err)
	}
	if err := sub.Close(); err != nil {
		t.Error(err)
	}
	want := map[string]fs.FileMode{
		"c1": 0o700, "c1/c2": 0o700, "c1/c2/f": 0o600,
		"r1": 0o700, "r1/f": 0o644,
		"m1": 0o700, "m1/m2": 0o700,
	}
	for name, mode := range want {
		if got := modeOf(t, root, name); got != mode {
			t.Errorf("%s has the mode %v, want %v", name, got, mode)
		}
	}
}

func TestOpenLockFileIsPrivate(t *testing.T) {
	root, d := newTree(t)
	writeFile(t, root, "locks/old.lock", "")
	chmodPath(t, root, "locks/old.lock", 0o644)
	for _, name := range []string{"locks/old.lock", "new/dir/new.lock"} {
		file, err := d.OpenLockFile(name)
		if err != nil {
			t.Fatal(err)
		}
		if err := file.Close(); err != nil {
			t.Error(err)
		}
	}
	for name, want := range map[string]fs.FileMode{"locks/old.lock": 0o600, "new": 0o700, "new/dir": 0o700, "new/dir/new.lock": 0o600} {
		if got := modeOf(t, root, name); got != want {
			t.Errorf("%s has the mode %v, want %v", name, got, want)
		}
	}
	if err := unix.Mkfifo(filepath.Join(root, "locks", "fifo.lock"), 0o600); err != nil {
		t.Fatal(err)
	}
	_, err := d.OpenLockFile("locks/fifo.lock")
	wantReason(t, err, ReasonNotRegularFile)
}

func TestReplaceSetsTheExactMode(t *testing.T) {
	root, d := newTree(t)
	for _, perm := range []fs.FileMode{0o640, 0o600, 0o644, 0o400} {
		if err := d.Replace("f", []byte("x"), perm); err != nil {
			t.Fatal(err)
		}
		if got := modeOf(t, root, "f"); got != perm {
			t.Errorf("Replace(%v) gave the mode %v", perm, got)
		}
	}
}

func TestReplaceKeepsTheModesOfItsDirectories(t *testing.T) {
	root, d := newTree(t)
	mkdir(t, root, "open/dir")
	chmodPath(t, root, "open", 0o777)
	chmodPath(t, root, "open/dir", 0o755)
	if err := d.Replace("open/dir/f", []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	if got := modeOf(t, root, "open"); got != 0o777 {
		t.Errorf("Replace changed a directory to %v", got)
	}
	if got := modeOf(t, root, "open/dir"); got != 0o755 {
		t.Errorf("Replace changed the parent to %v", got)
	}
}

func TestChmodAndRestrictToOwner(t *testing.T) {
	root, d := newTree(t)
	writeFile(t, root, "pub", "x")
	writeFile(t, root, "key", "x")
	chmodPath(t, root, "key", 0o644)
	if err := d.Chmod("pub", 0o644); err != nil {
		t.Fatal(err)
	}
	if err := d.RestrictToOwner("key"); err != nil {
		t.Fatal(err)
	}
	if got := modeOf(t, root, "pub"); got != 0o644 {
		t.Errorf("Chmod gave the mode %v, want 0644", got)
	}
	if got := modeOf(t, root, "key"); got != 0o600 {
		t.Errorf("RestrictToOwner gave the mode %v, want 0600", got)
	}
	mkdir(t, root, "dir")
	wantReason(t, d.Chmod("dir", 0o600), ReasonNotRegularFile)
	wantReason(t, d.RestrictToOwner("missing"), ReasonNotFound)
}

func TestChmodRestoresAnUnreadableFile(t *testing.T) {
	requireModes(t)
	root, d := newTree(t)
	writeFile(t, root, "pub", "x")
	writeFile(t, root, "key", "x")
	chmodPath(t, root, "pub", 0)
	chmodPath(t, root, "key", 0)
	if err := d.Chmod("pub", 0o644); err != nil {
		t.Fatalf("Chmod() of a file without read access = %v, want nil", err)
	}
	if err := d.RestrictToOwner("key"); err != nil {
		t.Fatalf("RestrictToOwner() of a file without read access = %v, want nil", err)
	}
	if got := modeOf(t, root, "pub"); got != 0o644 {
		t.Errorf("Chmod gave the mode %v, want 0644", got)
	}
	if got := modeOf(t, root, "key"); got != 0o600 {
		t.Errorf("RestrictToOwner gave the mode %v, want 0600", got)
	}
}

func TestReplacePrivateMakesTheFileAndItsParentPrivate(t *testing.T) {
	root, d := newTree(t)
	writeFile(t, root, "state/env/node.env", "OLD=1\n")
	chmodPath(t, root, "state/env/node.env", 0o666)
	chmodPath(t, root, "state/env", 0o777)
	chmodPath(t, root, "state", fs.ModeSticky|0o777)
	chmodPath(t, root, ".", 0o777)
	if err := d.ReplacePrivate("state/env/node.env", []byte("NEW=1\n")); err != nil {
		t.Fatal(err)
	}
	if got := readFile(t, root, "state/env/node.env"); got != "NEW=1\n" {
		t.Errorf("the file holds %q, want the new content", got)
	}
	want := map[string]fs.FileMode{
		"state/env/node.env": 0o600,
		"state/env":          0o700,
		"state":              fs.ModeSticky | 0o755,
		".":                  0o777,
	}
	for name, mode := range want {
		if got := modeOf(t, root, name); got != mode {
			t.Errorf("%s has the mode %v, want %v", name, got, mode)
		}
	}
}

func TestReplacePrivateNeverChangesTheTrustedDirectory(t *testing.T) {
	root, d := newTree(t)
	chmodPath(t, root, ".", 0o755)
	if err := d.ReplacePrivate("top.env", []byte("x")); err != nil {
		t.Fatal(err)
	}
	if got := modeOf(t, root, "."); got != 0o755 {
		t.Errorf("the trusted directory has the mode %v, want 0755", got)
	}
	if got := modeOf(t, root, "top.env"); got != 0o600 {
		t.Errorf("the file has the mode %v, want 0600", got)
	}
}

func TestReplacePrivateCreatesPrivateDirectories(t *testing.T) {
	root, d := newTree(t)
	if err := d.ReplacePrivate("state/env/node.env", []byte("NEW=1\n")); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"state", "state/env"} {
		if got := modeOf(t, root, name); got != 0o700 {
			t.Errorf("%s has the mode %v, want 0700", name, got)
		}
	}
}

func TestPrivateSubdirRestrictsEachDirectory(t *testing.T) {
	root, d := newTree(t)
	mkdir(t, root, "p/q")
	chmodPath(t, root, "p", 0o777)
	chmodPath(t, root, "p/q", 0o777)
	sub, err := d.PrivateSubdir("p/q")
	if err != nil {
		t.Fatal(err)
	}
	if err := sub.Close(); err != nil {
		t.Error(err)
	}
	if got := modeOf(t, root, "p"); got != 0o755 {
		t.Errorf("p has the mode %v, want 0755", got)
	}
	if got := modeOf(t, root, "p/q"); got != 0o700 {
		t.Errorf("p/q has the mode %v, want 0700", got)
	}
}

func TestRestrictedMode(t *testing.T) {
	const me, other = 1000, 1001
	tests := []struct {
		mode, owner uint32
		forbidden   uint32
		owned       bool
		want        uint32
		ok          bool
	}{
		{0o777, me, groupOrOtherWrite, false, 0o755, true},
		{0o1777, me, groupOrOtherWrite, false, 0o1755, true},
		{0o755, me, groupOrOtherAccess, true, 0o700, true},
		{0o700, me, groupOrOtherAccess, true, 0o700, true},
		{0o755, other, groupOrOtherWrite, false, 0o755, true},
		{0o775, other, groupOrOtherWrite, false, 0, false},
		{0o755, other, groupOrOtherWrite, true, 0, false},
		{0o700, other, groupOrOtherAccess, true, 0, false},
	}
	for _, tt := range tests {
		got, ok := restrictedMode(tt.mode, tt.owner, me, tt.forbidden, tt.owned)
		if got != tt.want || ok != tt.ok {
			t.Errorf("restrictedMode(%o, %d, %o, %v) = %o, %v, want %o, %v", tt.mode, tt.owner, tt.forbidden, tt.owned, got, ok, tt.want, tt.ok)
		}
	}
}

func TestOnlyThePrivateRuleRequiresTheOwner(t *testing.T) {
	// A directory that another user owns shows this rule, but a test without
	// root cannot make one.
	for _, rule := range []dirRule{ruleSearch, ruleOpen, ruleCreate, ruleRestrict} {
		if rule.requiresOwner() {
			t.Errorf("rule %d requires the owner", rule)
		}
	}
	if !rulePrivate.requiresOwner() {
		t.Error("rulePrivate does not require the owner")
	}
}

// limitFileSize limits the size of each file that the process writes, until
// the end of the test.
func limitFileSize(t *testing.T, size uint64) {
	t.Helper()
	var old unix.Rlimit
	if err := unix.Getrlimit(unix.RLIMIT_FSIZE, &old); err != nil {
		t.Fatal(err)
	}
	limited := unix.Rlimit{Cur: size, Max: old.Max}
	if err := unix.Setrlimit(unix.RLIMIT_FSIZE, &limited); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := unix.Setrlimit(unix.RLIMIT_FSIZE, &old); err != nil {
			t.Error(err)
		}
	})
}

// openParent opens the parent of the leaf of name below d, as the write
// operations do before they publish.
func openParent(t *testing.T, d *Dir, name string) (parent int, leaf string) {
	t.Helper()
	parts, err := components("replace", name)
	if err != nil {
		t.Fatal(err)
	}
	parent, leaf, err = d.h.walkParent("replace", name, parts, ruleCreate)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := closeFd("replace", name, parent); err != nil {
			t.Error(err)
		}
	})
	return parent, leaf
}

func TestALeafSwappedForALinkIsReplacedNotFollowed(t *testing.T) {
	root, d := newTree(t)
	writeFile(t, root, "outside.txt", "keep")
	mkdir(t, root, "env")
	parent, leaf := openParent(t, d, "env/node.env")
	symlink(t, root, filepath.Join(root, "outside.txt"), "env/node.env")
	if err := publish("replace", "env/node.env", parent, leaf, []byte("NEW=1\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if got := readFile(t, root, "outside.txt"); got != "keep" {
		t.Errorf("the link target holds %q, want keep", got)
	}
	info, err := os.Lstat(filepath.Join(root, "env", "node.env"))
	if err != nil || !info.Mode().IsRegular() {
		t.Fatalf("the leaf is not a regular file: %v", err)
	}
	if got := readFile(t, root, "env/node.env"); got != "NEW=1\n" {
		t.Errorf("the file holds %q, want the new content", got)
	}
}

func TestADirectorySwappedMidWriteKeepsTheWriteInTheOpenedOne(t *testing.T) {
	root, d := newTree(t)
	mkdir(t, root, "outside")
	mkdir(t, root, "env")
	parent, leaf := openParent(t, d, "env/node.env")
	rename(t, root, "env", "moved")
	symlink(t, root, "outside", "env")
	if err := publish("replace", "env/node.env", parent, leaf, []byte("NEW=1\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if got := names(t, root, "outside"); len(got) != 0 {
		t.Errorf("the link target holds %q, want nothing", got)
	}
	if got := readFile(t, root, "moved/node.env"); got != "NEW=1\n" {
		t.Errorf("the opened directory holds %q, want the new content", got)
	}
}

func TestAnInterruptedReplacementKeepsThePreviousFile(t *testing.T) {
	root, d := newTree(t)
	writeFile(t, root, "env/node.env", "OLD=1\n")
	// A file size limit of 2 bytes makes the write of the temporary file fail
	// with EFBIG after its first bytes. The Go runtime ignores SIGXFSZ.
	limitFileSize(t, 2)
	err := d.Replace("env/node.env", []byte("NEW=1\n"), 0o600)
	if !errors.Is(err, unix.EFBIG) {
		t.Fatalf("Replace() = %v, want the cause EFBIG", err)
	}
	if got := readFile(t, root, "env/node.env"); got != "OLD=1\n" {
		t.Errorf("the file holds %q, want the previous content", got)
	}
	if got, want := names(t, root, "env"), []string{"node.env"}; !slices.Equal(got, want) {
		t.Errorf("the directory holds %q, want %q and no temporary file", got, want)
	}
}

func TestAFailedRenameRemovesTheTemporaryFile(t *testing.T) {
	root, d := newTree(t)
	mkdir(t, root, "env")
	parent, leaf := openParent(t, d, "env/node.env")
	writeFile(t, root, "env/node.env/inside", "x")
	err := publish("replace", "env/node.env", parent, leaf, []byte("NEW=1\n"), 0o600)
	if err == nil {
		t.Fatal("publish() = nil, want the error of the rename onto a directory")
	}
	if got, want := names(t, root, "env"), []string{"node.env"}; !slices.Equal(got, want) {
		t.Errorf("the directory holds %q, want %q and no temporary file", got, want)
	}
}

func TestWritesInAReadOnlyDirectoryFail(t *testing.T) {
	requireModes(t)
	root, d := newTree(t)
	writeFile(t, root, "ro/f", "x")
	chmodPath(t, root, "ro", 0o500)
	wantReason(t, d.Replace("ro/f", []byte("y"), 0o600), ReasonOpenFailed)
	wantReason(t, d.CreateOnce("ro/g", []byte("y")), ReasonOpenFailed)
	if err := d.Remove("ro/f"); err == nil || !errors.Is(err, unix.EACCES) {
		t.Errorf("Remove() = %v, want the cause EACCES", err)
	}
	if err := d.RemoveAll("ro/f"); err == nil || !errors.Is(err, unix.EACCES) {
		t.Errorf("RemoveAll() = %v, want the cause EACCES", err)
	}
	if got := readFile(t, root, "ro/f"); got != "x" {
		t.Errorf("the file holds %q, want x", got)
	}
}

func TestAClosedDirNeverReachesAReusedDescriptor(t *testing.T) {
	root, d := newTree(t)
	other := t.TempDir()
	writeFile(t, other, "secret", "other")
	sub, err := d.MakeSubdir("sub")
	if err != nil {
		t.Fatal(err)
	}
	number := int(sub.h.f.Fd())
	if err := sub.Close(); err != nil {
		t.Fatal(err)
	}
	// The kernel gives the closed number to the next open of another
	// directory. An operation of the closed Dir must not reach it.
	reused := reuseDescriptor(t, other, number)
	t.Cleanup(func() {
		if err := unix.Close(reused); err != nil {
			t.Error(err)
		}
	})
	if data, err := sub.ReadFile("secret"); err == nil {
		t.Fatalf("ReadFile() through a closed Dir = %q, want an error", data)
	}
	if err := sub.CreateOnce("planted", []byte("x")); err == nil {
		t.Fatal("CreateOnce() through a closed Dir = nil, want an error")
	}
	if got := names(t, other, "."); len(got) != 1 {
		t.Errorf("the other directory holds %q, want only its own file", got)
	}
	if got := names(t, root, "sub"); len(got) != 0 {
		t.Errorf("the closed directory holds %q, want nothing", got)
	}
}

// reuseDescriptor opens dir until the kernel hands out the number n, closes
// the other descriptors, and returns the descriptor with the number n.
func reuseDescriptor(t *testing.T, dir string, n int) int {
	t.Helper()
	var extra []int
	defer func() {
		for _, fd := range extra {
			if err := unix.Close(fd); err != nil {
				t.Error(err)
			}
		}
	}()
	for range n + 1 {
		fd, err := unix.Open(dir, unix.O_RDONLY|unix.O_DIRECTORY|unix.O_CLOEXEC, 0)
		if err != nil {
			t.Fatal(err)
		}
		if fd == n {
			return fd
		}
		extra = append(extra, fd)
	}
	t.Fatalf("the kernel did not give the number %d again", n)
	return -1
}

// openRaw opens the directory name below root as a descriptor that the test
// closes.
func openRaw(t *testing.T, root, name string) int {
	t.Helper()
	fd, err := unix.Open(filepath.Join(root, name), unix.O_RDONLY|unix.O_DIRECTORY|unix.O_CLOEXEC, 0)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := unix.Close(fd); err != nil {
			t.Error(err)
		}
	})
	return fd
}

func TestRemovalGoesOnAfterAnEntryThatAnotherProcessRemoved(t *testing.T) {
	root, _ := newTree(t)
	writeFile(t, root, "tree/a", "x")
	writeFile(t, root, "tree/c/d", "x")
	// Readdirnames listed the entry b, and another process removed it before
	// the removal reached it.
	if err := removeEntries("remove all", "tree", openRaw(t, root, "tree"), []string{"a", "b", "c"}); err != nil {
		t.Fatalf("removeEntries() = %v, want nil", err)
	}
	if got := names(t, root, "tree"); len(got) != 0 {
		t.Errorf("the directory holds %q, want nothing", got)
	}
}

func TestADirectoryThatAnotherProcessRemovedIsDone(t *testing.T) {
	root, _ := newTree(t)
	// An earlier lstat saw the directory gone, and another process removed it
	// before the open.
	if err := removeEntry("remove all", "tree", openRaw(t, root, "."), "gone", true); err != nil {
		t.Errorf("removeEntry() = %v, want nil", err)
	}
}

func TestIgnoringEINTR(t *testing.T) {
	calls := 0
	err := ignoringEINTR(func() error {
		calls++
		if calls < 3 {
			return unix.EINTR
		}
		return unix.EBADF
	})
	if !errors.Is(err, unix.EBADF) || calls != 3 {
		t.Errorf("ignoringEINTR() = %v after %d calls, want EBADF after 3", err, calls)
	}
	calls = 0
	fd, err := ignoringEINTR2(func() (int, error) {
		calls++
		if calls < 2 {
			return -1, unix.EINTR
		}
		return 7, nil
	})
	if fd != 7 || err != nil || calls != 2 {
		t.Errorf("ignoringEINTR2() = %d, %v after %d calls, want 7, nil after 2", fd, err, calls)
	}
}
