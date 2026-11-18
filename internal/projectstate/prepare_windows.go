//go:build windows

package projectstate

import (
	"fmt"
	"os"
)

// prepareLockFile writes one NUL byte to an empty lock file, as the Python
// release does before it locks byte 0. Otherwise a Python process writes the
// byte while Go holds the lock, that write fails, and Python reports the
// lock as unavailable, not busy.
func prepareLockFile(file *os.File) error {
	info, err := file.Stat()
	if err == nil && info.Size() == 0 {
		_, err = file.Write([]byte{0})
	}
	if err != nil {
		return fmt.Errorf("projectstate: prepare %s: %w", LockFile, err)
	}
	return nil
}
