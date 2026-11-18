//go:build !windows

package projectstate

import "os"

// prepareLockFile does nothing on Linux and macOS, where flock locks the
// whole file.
func prepareLockFile(*os.File) error { return nil }
