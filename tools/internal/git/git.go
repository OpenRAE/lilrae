// Package git runs the Git commands that the developer tools need.
//
// Each function runs git with a fixed argument list in a working tree. Paths
// in arguments and results are relative to the root of that working tree and
// use forward slashes.
package git

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os/exec"
	"strings"
)

// Run runs git with args in dir and returns its standard output.
func Run(ctx context.Context, dir string, args ...string) ([]byte, error) {
	// G204 is a false positive: the program is fixed, no shell runs, and the
	// callers pass full commit names, --end-of-options, or -- before a path,
	// so an argument cannot become an option.
	cmd := exec.CommandContext(ctx, "git", args...) //nolint:gosec // G204: fixed program, argv without a shell.
	cmd.Dir = dir
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("git %s: %w: %s", strings.Join(args, " "), err, strings.TrimSpace(stderr.String()))
	}
	return stdout.Bytes(), nil
}

// TopLevel returns the root of the working tree that contains dir.
func TopLevel(ctx context.Context, dir string) (string, error) {
	out, err := Run(ctx, dir, "rev-parse", "--show-toplevel")
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(out)), nil
}

// ResolveCommit returns the full object name of the commit that rev names.
func ResolveCommit(ctx context.Context, dir, rev string) (string, error) {
	out, err := Run(ctx, dir, "rev-parse", "--verify", "--quiet", "--end-of-options", rev+"^{commit}")
	if err != nil {
		return "", fmt.Errorf("resolve %q to a commit: %w", rev, err)
	}
	return strings.TrimSpace(string(out)), nil
}

// Change is a file that differs between two revisions.
type Change struct {
	// Path is the path of the file.
	Path string
	// Deleted reports that the newer revision does not have the file.
	Deleted bool
}

// ChangedFiles returns the files that differ between base and head, limited to
// pathspec. A renamed file counts as a deleted file and a new file.
func ChangedFiles(ctx context.Context, dir, base, head, pathspec string) ([]Change, error) {
	out, err := Run(ctx, dir, "diff", "--name-status", "--no-renames", "-z", base, head, "--", pathspec)
	if err != nil {
		return nil, err
	}
	fields := splitNUL(out)
	if len(fields)%2 != 0 {
		return nil, fmt.Errorf("git diff: unexpected output %q", out)
	}
	var changes []Change
	for i := 0; i < len(fields); i += 2 {
		status, path := fields[i], fields[i+1]
		switch status {
		case "A", "M", "T":
			changes = append(changes, Change{Path: path})
		case "D":
			changes = append(changes, Change{Path: path, Deleted: true})
		default:
			return nil, fmt.Errorf("git diff: unexpected status %q for %s", status, path)
		}
	}
	return changes, nil
}

// Entry is a file of a tree.
type Entry struct {
	// Path is the path of the file.
	Path string
	// Mode is the Git file mode, for example 100644, 100755, or 120000.
	Mode string
}

// Files returns the files of the tree of rev below dirPath, at any depth.
func Files(ctx context.Context, dir, rev, dirPath string) ([]Entry, error) {
	out, err := Run(ctx, dir, "ls-tree", "-r", "-z", "--full-tree", rev, "--", dirPath+"/")
	if err != nil {
		return nil, err
	}
	var entries []Entry
	for _, record := range splitNUL(out) {
		meta, path, ok := strings.Cut(record, "\t")
		fields := strings.Fields(meta)
		if !ok || len(fields) != 3 {
			return nil, fmt.Errorf("git ls-tree: unexpected record %q", record)
		}
		if fields[1] == "blob" {
			entries = append(entries, Entry{Path: path, Mode: fields[0]})
		}
	}
	return entries, nil
}

// ErrNotExist reports that a file does not exist at a revision.
var ErrNotExist = errors.New("file does not exist at the revision")

// Show returns the content of the file at path in rev. It returns an error
// that wraps ErrNotExist when rev has no file at path.
func Show(ctx context.Context, dir, rev, path string) ([]byte, error) {
	out, err := Run(ctx, dir, "ls-tree", "-z", "--full-tree", rev, "--", path)
	if err != nil {
		return nil, err
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("%s at %s: %w", path, rev, ErrNotExist)
	}
	return Run(ctx, dir, "cat-file", "blob", rev+":"+path)
}

func splitNUL(out []byte) []string {
	var parts []string
	for part := range strings.SplitSeq(string(out), "\x00") {
		if part != "" {
			parts = append(parts, part)
		}
	}
	return parts
}
