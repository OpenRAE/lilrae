package securefile

import (
	"bytes"
	"errors"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"runtime"
	"slices"
	"strings"
	"syscall"
	"testing"
)

// newTree returns a new temporary directory and a Dir of it.
func newTree(t *testing.T) (string, *Dir) {
	t.Helper()
	root := t.TempDir()
	d, err := OpenDir(root)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := d.Close(); err != nil {
			t.Error(err)
		}
	})
	return root, d
}

// writeFile writes content to the file name below root, and creates its
// directories.
func writeFile(tb testing.TB, root, name, content string) {
	tb.Helper()
	path := filepath.Join(root, filepath.FromSlash(name))
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		tb.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		tb.Fatal(err)
	}
}

// readFile returns the content of the file name below root.
func readFile(tb testing.TB, root, name string) string {
	tb.Helper()
	data, err := fs.ReadFile(os.DirFS(root), name)
	if err != nil {
		tb.Fatal(err)
	}
	return string(data)
}

// symlink makes the link name below root to target.
func symlink(tb testing.TB, root, target, name string) {
	tb.Helper()
	if err := os.Symlink(filepath.FromSlash(target), filepath.Join(root, filepath.FromSlash(name))); err != nil {
		tb.Fatal(err)
	}
}

// closeOnCleanup closes c at the end of the test.
func closeOnCleanup(tb testing.TB, c io.Closer) {
	tb.Helper()
	tb.Cleanup(func() {
		if err := c.Close(); err != nil {
			tb.Error(err)
		}
	})
}

// rename renames the entry oldName below root to newName.
func rename(tb testing.TB, root, oldName, newName string) {
	tb.Helper()
	if err := os.Rename(filepath.Join(root, filepath.FromSlash(oldName)), filepath.Join(root, filepath.FromSlash(newName))); err != nil {
		tb.Fatal(err)
	}
}

func mkdir(tb testing.TB, root, name string) {
	tb.Helper()
	if err := os.MkdirAll(filepath.Join(root, filepath.FromSlash(name)), 0o700); err != nil {
		tb.Fatal(err)
	}
}

func wantReason(tb testing.TB, err error, want Reason) {
	tb.Helper()
	if !IsReason(err, want) {
		tb.Fatalf("error = %v, want the reason %s", err, want)
	}
}

func names(tb testing.TB, root, name string) []string {
	tb.Helper()
	entries, err := os.ReadDir(filepath.Join(root, filepath.FromSlash(name)))
	if err != nil {
		tb.Fatal(err)
	}
	var out []string
	for _, entry := range entries {
		out = append(out, entry.Name())
	}
	return out
}

func TestCheckPath(t *testing.T) {
	windows := runtime.GOOS == "windows"
	tests := []struct {
		name string
		want Reason // "" for a valid path
	}{
		{"a", ""},
		{"a/b/c.txt", ""},
		{"..a/b..", ""},
		{".hidden", ""},
		{"", ReasonEmptyComponent},
		{"\x00", ReasonNULByte},
		{"/\x00", ReasonNULByte},
		{"a/b\x00", ReasonNULByte},
		{"/a", ReasonNotRelative},
		{"//a", ReasonNotRelative},
		{"a//b", ReasonEmptyComponent},
		{"a/", ReasonEmptyComponent},
		{".", ReasonDotComponent},
		{"a/./b", ReasonDotComponent},
		{"..", ReasonTraversal},
		{"a/../b", ReasonTraversal},
		{"a/..", ReasonTraversal},
		{"./..", ReasonDotComponent},
		{"../.", ReasonTraversal},
		{"a/\xff", ReasonInvalidName},
		{`a\b`, map[bool]Reason{true: ReasonInvalidName}[windows]},
		{`\a`, map[bool]Reason{true: ReasonInvalidName}[windows]},
		{"C:a", map[bool]Reason{true: ReasonInvalidName}[windows]},
		{"a/b:c", map[bool]Reason{true: ReasonInvalidName}[windows]},
		{"a/NUL", map[bool]Reason{true: ReasonInvalidName}[windows]},
		{`a\..\..\b`, map[bool]Reason{true: ReasonInvalidName}[windows]},
	}
	for _, tt := range tests {
		err := CheckPath(tt.name)
		if tt.want == "" {
			if err != nil {
				t.Errorf("CheckPath(%q) = %v, want nil", tt.name, err)
			}
			continue
		}
		var e *Error
		if !errors.As(err, &e) || e.Reason != tt.want || e.Op != "check" || e.Path != tt.name || e.Err != nil {
			t.Errorf("CheckPath(%q) = %#v, want the reason %s", tt.name, err, tt.want)
		}
	}
}

func TestErrorText(t *testing.T) {
	cause := errors.New("cause")
	err := &Error{Op: "replace", Path: "a/b", Reason: ReasonSymlink, Err: cause}
	if got, want := err.Error(), "securefile: replace a/b: symlink: cause"; got != want {
		t.Errorf("Error() = %q, want %q", got, want)
	}
	if !errors.Is(err, cause) {
		t.Error("the error does not unwrap to its cause")
	}
	bare := &Error{Op: "open", Path: "x", Reason: ReasonNotFound}
	if got, want := bare.Error(), "securefile: open x: not_found"; got != want {
		t.Errorf("Error() = %q, want %q", got, want)
	}
	if !IsReason(errors.Join(cause, bare), ReasonNotFound) || IsReason(bare, ReasonSymlink) || IsReason(cause, ReasonNotFound) {
		t.Error("IsReason does not match the reason of the error")
	}
}

func TestOpenReason(t *testing.T) {
	tests := []struct {
		err    error
		isLink bool
		want   Reason
	}{
		{syscall.ELOOP, false, ReasonSymlink},
		{fs.ErrNotExist, true, ReasonSymlink},
		{syscall.ENOTDIR, true, ReasonSymlink},
		{errors.New("other"), true, ReasonSymlink},
		{fs.ErrNotExist, false, ReasonNotFound},
		{syscall.ENOTDIR, false, ReasonNotFound},
		{fs.ErrPermission, false, ReasonOpenFailed},
	}
	for _, tt := range tests {
		if got := openReason(tt.err, tt.isLink); got != tt.want {
			t.Errorf("openReason(%v, %v) = %s, want %s", tt.err, tt.isLink, got, tt.want)
		}
	}
}

func TestFailure(t *testing.T) {
	if err := failure("op", "p", nil); err != nil {
		t.Errorf("failure(nil) = %v, want nil", err)
	}
	refused := &Error{Op: "op", Path: "p", Reason: ReasonSymlink}
	if err := failure("other", "q", refused); err == nil || err.Error() != refused.Error() {
		t.Errorf("failure(*Error) = %v, want the error unchanged", err)
	}
	err := failure("op", "p", fs.ErrPermission)
	if got, want := err.Error(), "securefile: op p: "+fs.ErrPermission.Error(); got != want || !errors.Is(err, fs.ErrPermission) {
		t.Errorf("failure() = %q, want %q that wraps the cause", got, want)
	}
}

func TestTempName(t *testing.T) {
	a, b := tempName("leaf"), tempName("leaf")
	if a == b {
		t.Errorf("two temporary names are equal: %q", a)
	}
	if !strings.HasPrefix(a, ".leaf.") || !strings.HasSuffix(a, ".tmp") || len(a) < len(".leaf..tmp")+26 {
		t.Errorf("tempName() = %q, want .leaf.<26 random characters>.tmp", a)
	}
}

func TestOpenDirRefusesAMissingDirectory(t *testing.T) {
	path := filepath.Join(t.TempDir(), "missing")
	_, err := OpenDir(path)
	wantReason(t, err, ReasonBaseDirUnavailable)
	if !strings.Contains(err.Error(), "open dir "+path) {
		t.Errorf("error = %v, want the operation and the path", err)
	}
}

func TestCloseReportsASecondClose(t *testing.T) {
	d, err := OpenDir(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if err := d.Close(); err != nil {
		t.Fatal(err)
	}
	if err := d.Close(); !errors.Is(err, fs.ErrClosed) || !strings.HasPrefix(err.Error(), "securefile: close dir .: ") {
		t.Errorf("second Close() = %v, want an error of the package that matches fs.ErrClosed", err)
	}
}

func TestAClosedDirRefusesEachOperation(t *testing.T) {
	root := t.TempDir()
	writeFile(t, root, "f", "x")
	d, err := OpenDir(root)
	if err != nil {
		t.Fatal(err)
	}
	if err := d.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err := d.ReadFile("f"); err == nil {
		t.Error("ReadFile() after Close = nil error, want an error")
	}
	if err := d.Replace("f", []byte("y"), 0o600); err == nil {
		t.Error("Replace() after Close = nil, want an error")
	}
	if _, err := d.Subdir("missing"); err == nil {
		t.Error("Subdir() after Close = nil error, want an error")
	}
	if got := readFile(t, root, "f"); got != "x" {
		t.Errorf("the file holds %q after Close, want x", got)
	}
}

func TestReadFile(t *testing.T) {
	root, d := newTree(t)
	writeFile(t, root, "top.txt", "top")
	writeFile(t, root, "x/y/z.txt", "nested")
	for name, want := range map[string]string{"top.txt": "top", "x/y/z.txt": "nested"} {
		got, err := d.ReadFile(name)
		if err != nil || string(got) != want {
			t.Errorf("ReadFile(%q) = %q, %v, want %q", name, got, err, want)
		}
	}
	tests := []struct {
		name string
		want Reason
	}{
		{"missing.txt", ReasonNotFound},
		{"missing/z.txt", ReasonNotFound},
		{"top.txt/z.txt", ReasonNotFound},
		{"x/y", ReasonNotRegularFile},
		{"../x", ReasonTraversal},
	}
	for _, tt := range tests {
		_, err := d.ReadFile(tt.name)
		wantReason(t, err, tt.want)
		if e, ok := errors.AsType[*Error](err); !ok || e.Op != "read" || e.Path != tt.name {
			t.Errorf("ReadFile(%q) error = %#v, want the operation read and the path", tt.name, err)
		}
	}
}

func TestOpenReadsTheFileThatItOpened(t *testing.T) {
	root, d := newTree(t)
	writeFile(t, root, "f", "original")
	file, err := d.Open("f")
	if err != nil {
		t.Fatal(err)
	}
	closeOnCleanup(t, file)
	rename(t, root, "f", "moved")
	writeFile(t, root, "f", "swapped")
	got, err := io.ReadAll(file)
	if err != nil || string(got) != "original" {
		t.Errorf("read %q, %v, want the original bytes", got, err)
	}
}

func TestReadDirNames(t *testing.T) {
	root, d := newTree(t)
	for _, name := range []string{"dir/c", "dir/a", "dir/b/x"} {
		writeFile(t, root, name, "")
	}
	got, err := d.ReadDirNames("dir")
	if want := []string{"a", "b", "c"}; err != nil || !slices.Equal(got, want) {
		t.Errorf("ReadDirNames() = %q, %v, want %q", got, err, want)
	}
	_, err = d.ReadDirNames("missing")
	wantReason(t, err, ReasonNotFound)
	_, err = d.ReadDirNames("dir/a")
	wantReason(t, err, ReasonNotFound)
	_, err = d.ReadDirNames("dir//b")
	wantReason(t, err, ReasonEmptyComponent)
}

func TestSubdir(t *testing.T) {
	root, d := newTree(t)
	writeFile(t, root, "x/y/f", "inside")
	sub, err := d.Subdir("x/y")
	if err != nil {
		t.Fatal(err)
	}
	got, err := sub.ReadFile("f")
	if err != nil || string(got) != "inside" {
		t.Errorf("ReadFile() through the subdirectory = %q, %v", got, err)
	}
	if err := sub.Close(); err != nil {
		t.Error(err)
	}
	for name, want := range map[string]Reason{"missing": ReasonNotFound, "x/y/f": ReasonNotFound, "x/../x": ReasonTraversal} {
		_, err := d.Subdir(name)
		wantReason(t, err, want)
	}
}

func TestMakeSubdir(t *testing.T) {
	root, d := newTree(t)
	for range 2 {
		sub, err := d.MakeSubdir("p/q")
		if err != nil {
			t.Fatal(err)
		}
		if err := sub.CreateOnce("f", []byte("made")); err != nil && !errors.Is(err, fs.ErrExist) {
			t.Fatal(err)
		}
		if err := sub.Close(); err != nil {
			t.Error(err)
		}
	}
	if got := readFile(t, root, "p/q/f"); got != "made" {
		t.Errorf("the file holds %q, want made", got)
	}
	writeFile(t, root, "file", "")
	_, err := d.MakeSubdir("file/q")
	wantReason(t, err, ReasonNotFound)
	_, err = d.MakeSubdir("")
	wantReason(t, err, ReasonEmptyComponent)
}

func TestPrivateSubdir(t *testing.T) {
	root, d := newTree(t)
	sub, err := d.PrivateSubdir("state/packs")
	if err != nil {
		t.Fatal(err)
	}
	closeOnCleanup(t, sub)
	if err := sub.CreateOnce("f", []byte("private")); err != nil {
		t.Fatal(err)
	}
	if got := readFile(t, root, "state/packs/f"); got != "private" {
		t.Errorf("the file holds %q, want private", got)
	}
	_, refused := d.PrivateSubdir("/state")
	wantReason(t, refused, ReasonNotRelative)
}

func TestOpenLockFile(t *testing.T) {
	root, d := newTree(t)
	first, err := d.OpenLockFile(".aptl/lifecycle/.lock")
	if err != nil {
		t.Fatal(err)
	}
	closeOnCleanup(t, first)
	if _, writeErr := first.WriteString("owner"); writeErr != nil {
		t.Fatalf("the lock file is not open for writing: %v", writeErr)
	}
	second, err := d.OpenLockFile(".aptl/lifecycle/.lock")
	if err != nil {
		t.Fatal(err)
	}
	closeOnCleanup(t, second)
	if got, readErr := io.ReadAll(second); readErr != nil || string(got) != "owner" {
		t.Errorf("a second open reads %q, %v, want the same file without truncation", got, readErr)
	}
	symlink(t, root, ".lock", ".aptl/lifecycle/link.lock")
	symlink(t, root, "missing.lock", ".aptl/lifecycle/dangling.lock")
	for _, name := range []string{".aptl/lifecycle/link.lock", ".aptl/lifecycle/dangling.lock"} {
		_, linkErr := d.OpenLockFile(name)
		wantReason(t, linkErr, ReasonSymlink)
	}
	if got, want := names(t, root, ".aptl/lifecycle"), []string{".lock", "dangling.lock", "link.lock"}; !slices.Equal(got, want) {
		t.Errorf("the directory holds %q, want %q and no target of the dangling link", got, want)
	}
	mkdir(t, root, "dir.lock")
	_, err = d.OpenLockFile("dir.lock")
	wantReason(t, err, ReasonOpenFailed)
	_, err = d.OpenLockFile("../x.lock")
	wantReason(t, err, ReasonTraversal)
}

func TestCreateOnce(t *testing.T) {
	root, d := newTree(t)
	if err := d.CreateOnce("top", []byte("one")); err != nil {
		t.Fatal(err)
	}
	if err := d.CreateOnce("a/b/nested", []byte("two")); err != nil {
		t.Fatal(err)
	}
	if again := d.CreateOnce("top", []byte("again")); !errors.Is(again, fs.ErrExist) {
		t.Errorf("a second CreateOnce() = %v, want an error that matches fs.ErrExist", again)
	}
	if got := readFile(t, root, "top"); got != "one" {
		t.Errorf("the file holds %q after a second CreateOnce, want one", got)
	}
	if got := readFile(t, root, "a/b/nested"); got != "two" {
		t.Errorf("the nested file holds %q, want two", got)
	}
	big := bytes.Repeat([]byte("0123456789abcdef"), 1<<19)
	if err := d.CreateOnce("big", big); err != nil {
		t.Fatal(err)
	}
	if got := readFile(t, root, "big"); got != string(big) {
		t.Errorf("the large file holds %d bytes, want %d", len(got), len(big))
	}
	if got, want := names(t, root, "."), []string{"a", "big", "top"}; !slices.Equal(got, want) {
		t.Errorf("the directory holds %q, want %q and no temporary file", got, want)
	}
	wantReason(t, d.CreateOnce("a/./x", nil), ReasonDotComponent)
}

func TestReplace(t *testing.T) {
	root, d := newTree(t)
	for _, content := range []string{"first", "second"} {
		if err := d.Replace("dir/f", []byte(content), 0o600); err != nil {
			t.Fatal(err)
		}
		if got := readFile(t, root, "dir/f"); got != content {
			t.Errorf("the file holds %q, want %q", got, content)
		}
	}
	if got, want := names(t, root, "dir"), []string{"f"}; !slices.Equal(got, want) {
		t.Errorf("the directory holds %q, want %q and no temporary file", got, want)
	}
	mkdir(t, root, "dir/sub")
	wantReason(t, d.Replace("dir/sub", []byte("x"), 0o600), ReasonNotRegularFile)
	sub, err := d.Subdir("dir/sub")
	if err != nil {
		t.Fatalf("the refused directory changed: %v", err)
	}
	closeOnCleanup(t, sub)
	wantReason(t, d.Replace("dir/../f", nil, 0o600), ReasonTraversal)
}

func TestAModeWithOtherBitsIsRefusedBeforeAnyChange(t *testing.T) {
	root, d := newTree(t)
	writeFile(t, root, "f", "x")
	before, err := os.Stat(filepath.Join(root, "f"))
	if err != nil {
		t.Fatal(err)
	}
	for _, perm := range []fs.FileMode{fs.ModeSetuid | 0o600, fs.ModeSetgid | 0o600, fs.ModeSticky | 0o600} {
		if chmodErr := d.Chmod("f", perm); !errors.Is(chmodErr, fs.ErrInvalid) {
			t.Errorf("Chmod(%v) = %v, want an error that matches fs.ErrInvalid", perm, chmodErr)
		}
		if replaceErr := d.Replace("g", []byte("y"), perm); !errors.Is(replaceErr, fs.ErrInvalid) {
			t.Errorf("Replace(%v) = %v, want an error that matches fs.ErrInvalid", perm, replaceErr)
		}
	}
	after, err := os.Stat(filepath.Join(root, "f"))
	if err != nil {
		t.Fatal(err)
	}
	if after.Mode() != before.Mode() {
		t.Errorf("the mode changed from %v to %v", before.Mode(), after.Mode())
	}
	if got, want := names(t, root, "."), []string{"f"}; !slices.Equal(got, want) {
		t.Errorf("the directory holds %q, want %q", got, want)
	}
}

func TestReplaceNeverRewritesAHardLink(t *testing.T) {
	for name, replace := range map[string]func(*Dir) error{
		"Replace":        func(d *Dir) error { return d.Replace("env/node.env", []byte("NEW=1\n"), 0o600) },
		"ReplacePrivate": func(d *Dir) error { return d.ReplacePrivate("env/node.env", []byte("NEW=1\n")) },
	} {
		t.Run(name, func(t *testing.T) {
			root, d := newTree(t)
			writeFile(t, root, "outside.txt", "keep")
			mkdir(t, root, "env")
			if err := os.Link(filepath.Join(root, "outside.txt"), filepath.Join(root, "env", "node.env")); err != nil {
				t.Fatal(err)
			}
			if err := replace(d); err != nil {
				t.Fatal(err)
			}
			if got := readFile(t, root, "outside.txt"); got != "keep" {
				t.Errorf("the other name holds %q, want keep", got)
			}
			if got := readFile(t, root, "env/node.env"); got != "NEW=1\n" {
				t.Errorf("the file holds %q, want the new content", got)
			}
		})
	}
}

func TestRemove(t *testing.T) {
	root, d := newTree(t)
	writeFile(t, root, "dir/f", "x")
	writeFile(t, root, "dir/keep", "x")
	if err := d.Remove("dir/f"); err != nil {
		t.Fatal(err)
	}
	if got, want := names(t, root, "dir"), []string{"keep"}; !slices.Equal(got, want) {
		t.Errorf("the directory holds %q, want %q", got, want)
	}
	for _, name := range []string{"dir/f", "missing/f", "dir/keep/f"} {
		if err := d.Remove(name); err != nil {
			t.Errorf("Remove(%q) = %v, want nil for an absent file", name, err)
		}
	}
	mkdir(t, root, "dir/sub")
	err := d.Remove("dir/sub")
	wantReason(t, err, ReasonNotRegularFile)
	err = d.Remove("dir/")
	wantReason(t, err, ReasonEmptyComponent)
}

func TestRemoveAll(t *testing.T) {
	root, d := newTree(t)
	writeFile(t, root, "outside", "keep")
	writeFile(t, root, "tree/a/b/f", "x")
	writeFile(t, root, "tree/g", "x")
	mkdir(t, root, "tree/empty")
	symlink(t, root, filepath.Join("..", "..", "outside"), "tree/a/link")
	symlink(t, root, filepath.Join("..", "tree"), "tree/a/dirlink")
	if err := d.RemoveAll("tree"); err != nil {
		t.Fatal(err)
	}
	if got, want := names(t, root, "."), []string{"outside"}; !slices.Equal(got, want) {
		t.Errorf("the directory holds %q, want %q", got, want)
	}
	if got := readFile(t, root, "outside"); got != "keep" {
		t.Errorf("the link target holds %q, want keep", got)
	}
	for _, name := range []string{"tree", "missing/tree"} {
		if err := d.RemoveAll(name); err != nil {
			t.Errorf("RemoveAll(%q) = %v, want nil for an absent name", name, err)
		}
	}
	writeFile(t, root, "file", "x")
	if err := d.RemoveAll("file"); err != nil {
		t.Fatal(err)
	}
	if got, want := names(t, root, "."), []string{"outside"}; !slices.Equal(got, want) {
		t.Errorf("the directory holds %q, want %q", got, want)
	}
	err := d.RemoveAll(".")
	wantReason(t, err, ReasonDotComponent)
}

// linkTree makes a tree with a link at each position of a path:
//
//	real/sub/file, real/sub/dir/
//	link -> real, real/sublink -> sub
//	real/sub/filelink -> file, real/sub/dirlink -> dir
func linkTree(t *testing.T) (string, *Dir) {
	t.Helper()
	root, d := newTree(t)
	writeFile(t, root, "real/sub/file", "data")
	mkdir(t, root, "real/sub/dir")
	symlink(t, root, "real", "link")
	symlink(t, root, "sub", "real/sublink")
	symlink(t, root, "file", "real/sub/filelink")
	symlink(t, root, "dir", "real/sub/dirlink")
	return root, d
}

// linkOp is an operation with the paths that put a link at each position.
type linkOp struct {
	op    string
	paths []string
	call  func(d *Dir, name string) error
}

func linkOps() []linkOp {
	filePaths := []string{"link/sub/file", "real/sublink/file", "real/sub/filelink"}
	dirPaths := []string{"link/sub", "real/sublink", "real/sub/dirlink"}
	opened := errors.New("the operation succeeded")
	closeDir := func(sub *Dir, err error) error {
		if err != nil {
			return err
		}
		return errors.Join(opened, sub.Close())
	}
	return []linkOp{
		{"Open", filePaths, func(d *Dir, name string) error {
			file, err := d.Open(name)
			if err != nil {
				return err
			}
			return errors.Join(opened, file.Close())
		}},
		{"ReadFile", filePaths, func(d *Dir, name string) error { _, err := d.ReadFile(name); return err }},
		{"Replace", filePaths, func(d *Dir, name string) error { return d.Replace(name, []byte("new"), 0o600) }},
		{"ReplacePrivate", filePaths, func(d *Dir, name string) error { return d.ReplacePrivate(name, []byte("new")) }},
		{"Chmod", filePaths, func(d *Dir, name string) error { return d.Chmod(name, 0o600) }},
		{"RestrictToOwner", filePaths, func(d *Dir, name string) error { return d.RestrictToOwner(name) }},
		{"Remove", filePaths, func(d *Dir, name string) error { return d.Remove(name) }},
		{"RemoveAll", append(slices.Clone(filePaths), "real/sub/dirlink"), func(d *Dir, name string) error { return d.RemoveAll(name) }},
		{"CreateOnce", []string{"link/sub/new", "real/sublink/new"}, func(d *Dir, name string) error { return d.CreateOnce(name, []byte("new")) }},
		{"ReadDirNames", dirPaths, func(d *Dir, name string) error { _, err := d.ReadDirNames(name); return err }},
		{"Subdir", dirPaths, func(d *Dir, name string) error { return closeDir(d.Subdir(name)) }},
		{"MakeSubdir", append(slices.Clone(dirPaths), "link/new", "real/sublink/new"), func(d *Dir, name string) error { return closeDir(d.MakeSubdir(name)) }},
		{"PrivateSubdir", append(slices.Clone(dirPaths), "link/new"), func(d *Dir, name string) error { return closeDir(d.PrivateSubdir(name)) }},
	}
}

// checkLinkTree fails the test when the tree of linkTree changed.
func checkLinkTree(t *testing.T, root string) {
	t.Helper()
	if got := readFile(t, root, "real/sub/file"); got != "data" {
		t.Errorf("the link target holds %q, want data", got)
	}
	for _, link := range []string{"link", "real/sublink", "real/sub/filelink", "real/sub/dirlink"} {
		info, err := os.Lstat(filepath.Join(root, filepath.FromSlash(link)))
		if err != nil || info.Mode()&fs.ModeSymlink == 0 {
			t.Errorf("the link %s changed: %v", link, err)
		}
	}
	if got := names(t, root, "real/sub/dir"); len(got) != 0 {
		t.Errorf("the linked directory holds %q, want nothing", got)
	}
	if got, want := names(t, root, "real/sub"), []string{"dir", "dirlink", "file", "filelink"}; !slices.Equal(got, want) {
		t.Errorf("the directory holds %q, want %q", got, want)
	}
}

func TestEachOperationRefusesALinkAtEachComponent(t *testing.T) {
	for _, tt := range linkOps() {
		t.Run(tt.op, func(t *testing.T) {
			root, d := linkTree(t)
			for _, name := range tt.paths {
				wantReason(t, tt.call(d, name), ReasonSymlink)
			}
			checkLinkTree(t, root)
		})
	}
}

func TestCreateOnceOnALinkReportsThatTheNameExists(t *testing.T) {
	root, d := linkTree(t)
	if err := d.CreateOnce("real/sub/filelink", []byte("new")); !errors.Is(err, fs.ErrExist) {
		t.Errorf("CreateOnce() = %v, want an error that matches fs.ErrExist", err)
	}
	if got := readFile(t, root, "real/sub/file"); got != "data" {
		t.Errorf("the link target holds %q, want data", got)
	}
}

func TestOpenRefusesALinkOutOfTheTree(t *testing.T) {
	root, d := newTree(t)
	outside := t.TempDir()
	writeFile(t, outside, "f", "outside")
	symlink(t, root, outside, "esc")
	symlink(t, root, "..", "up")
	for _, name := range []string{"esc/f", "up/f"} {
		_, err := d.ReadFile(name)
		wantReason(t, err, ReasonSymlink)
		wantReason(t, d.Replace(name, []byte("x"), 0o600), ReasonSymlink)
	}
	if got := readFile(t, outside, "f"); got != "outside" {
		t.Errorf("the file out of the tree holds %q, want outside", got)
	}
}

func TestOpenRefusesADanglingLink(t *testing.T) {
	root, d := newTree(t)
	symlink(t, root, "missing", "dangling")
	_, err := d.Open("dangling")
	wantReason(t, err, ReasonSymlink)
	_, err = d.Subdir("dangling")
	wantReason(t, err, ReasonSymlink)
}
