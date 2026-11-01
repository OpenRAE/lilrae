//go:build windows

package architecture

import (
	"errors"
	"os"
)

// replaceFile reports that the file cannot be replaced. Windows cannot replace
// a file atomically, so renameio exports no function there (ADR-065).
func replaceFile(*os.Root, string, []byte) error {
	return errors.New("diagram -write needs an atomic file replacement, which Windows does not have")
}
