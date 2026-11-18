//go:build linux || darwin

package securefile

import (
	"path/filepath"
	"strings"
	"testing"
)

// raw joins parts with the separator and keeps each ".." part, which
// filepath.Join would remove before Resolve reads it.
func raw(parts ...string) string {
	return strings.Join(parts, string(filepath.Separator))
}

func TestResolveResolvesEachLink(t *testing.T) {
	root := realTempDir(t)
	mkdir(t, root, "real/sub")
	symlink(t, root, filepath.Join(root, "real"), "link")
	symlink(t, root, "real/sub", "relative")
	wantResolve(t, filepath.Join(root, "link", "sub"), filepath.Join(root, "real", "sub"))
	wantResolve(t, filepath.Join(root, "relative"), filepath.Join(root, "real", "sub"))
	wantResolve(t, filepath.Join(root, "link", "missing"), filepath.Join(root, "real", "missing"))
}

func TestResolveGoesToTheParentOfTheResolvedPart(t *testing.T) {
	root := realTempDir(t)
	mkdir(t, root, "real/sub")
	mkdir(t, root, "other")
	symlink(t, root, filepath.Join(root, "real", "sub"), "other/link")
	// Python goes to the parent of the target, not to "other".
	wantResolve(t, raw(root, "other", "link", ".."), filepath.Join(root, "real"))
}

func TestResolveResolvesALinkAfterAMissingPart(t *testing.T) {
	root := realTempDir(t)
	mkdir(t, root, "real")
	symlink(t, root, filepath.Join(root, "real"), "link")
	wantResolve(t, raw(root, "missing", "..", "link"), filepath.Join(root, "real"))
}

func TestResolveFollowsALinkWithAMissingTarget(t *testing.T) {
	root := realTempDir(t)
	mkdir(t, root, "a")
	mkdir(t, root, "b")
	symlink(t, root, filepath.Join(root, "b", "missing"), "a/alias")
	symlink(t, root, "../b/missing", "a/relative")
	symlink(t, root, filepath.Join(root, "a", "relative"), "a/chain")
	want := filepath.Join(root, "b", "missing")
	wantResolve(t, filepath.Join(root, "a", "alias"), want)
	wantResolve(t, filepath.Join(root, "a", "alias", "x"), filepath.Join(want, "x"))
	wantResolve(t, filepath.Join(root, "a", "relative"), want)
	wantResolve(t, raw(root, "a", "relative", "x", ".."), want)
	wantResolve(t, filepath.Join(root, "a", "chain"), want)
}

func TestResolveKeepsALinkLoopAsWritten(t *testing.T) {
	root := realTempDir(t)
	symlink(t, root, "loop", "loop")
	wantResolve(t, filepath.Join(root, "loop"), filepath.Join(root, "loop"))
	wantResolve(t, filepath.Join(root, "loop", "x"), filepath.Join(root, "loop", "x"))
}

func TestResolveReusesAResolvedLink(t *testing.T) {
	root := realTempDir(t)
	mkdir(t, root, "real")
	symlink(t, root, filepath.Join(root, "real"), "link")
	wantResolve(t, raw(root, "link", "..", "link"), filepath.Join(root, "real"))
}

func TestResolveStopsAtTheRoot(t *testing.T) {
	wantResolve(t, raw("", "..", "..", "x"), filepath.Join(string(filepath.Separator), "x"))
}
