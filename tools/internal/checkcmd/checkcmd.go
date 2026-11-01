// Package checkcmd holds the exit statuses, the flag parsing, and the output
// handling that the check commands share.
package checkcmd

import (
	"errors"
	"flag"
	"io"
)

// The exit statuses of a check command.
const (
	// Pass reports that the check found no violation.
	Pass = 0
	// Fail reports that the check found a violation.
	Fail = 1
	// Error reports that the check could not run.
	Error = 2
)

// Parse parses args with flags, which reports its own errors. It reports
// whether the command must stop, and then the exit status: Pass after -help,
// and Error after a flag error.
func Parse(flags *flag.FlagSet, args []string) (code int, stop bool) {
	err := flags.Parse(args)
	if err == nil {
		return Pass, false
	}
	if errors.Is(err, flag.ErrHelp) {
		return Pass, true
	}
	return Error, true
}

// Write writes text to w and returns code, or Error when the write fails.
func Write(w io.Writer, text string, code int) int {
	if _, err := io.WriteString(w, text); err != nil {
		return Error
	}
	return code
}
