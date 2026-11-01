//go:build !windows

package architecture

import (
	"fmt"
	"os"

	"github.com/google/renameio/v2"
)

// replaceFile replaces the file name in root atomically (ADR-065), and keeps
// the permissions of the existing file.
func replaceFile(root *os.Root, name string, data []byte) error {
	if err := renameio.WriteFile(name, data, 0o600, renameio.WithRoot(root)); err != nil {
		return fmt.Errorf("replace %s: %w", name, err)
	}
	return nil
}
