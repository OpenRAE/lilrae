package architecture

import (
	"fmt"
	"io"
	"strconv"
	"strings"
	"unicode/utf8"
)

// maxShown bounds the findings that Write prints.
const maxShown = 500

// maxText bounds a diagnostic text from an untrusted source.
const maxText = 2000

// Finding is a violation of the model or of a design record.
type Finding struct {
	// Rule is the rule of the checker.
	Rule string
	// Location is a repository path, with a line when one applies.
	Location string
	// Message describes the violation. It holds no source text.
	Message string
	// FixIt is the fix-it message of the model for the rule.
	FixIt string
}

// String returns the finding on two lines. The location, the message, and the
// fix-it message pass through Clean, so a finding cannot add a line of its own.
func (f Finding) String() string {
	return fmt.Sprintf("[%s] %s: %s\n    fix: %s", f.Rule, Clean(f.Location), Clean(f.Message), Clean(f.FixIt))
}

// Report is the result of a check.
type Report struct {
	// Findings lists the violations. The check passed when it is empty.
	Findings []Finding
}

// Write prints at most maxShown findings and a count of the others.
func Write(w io.Writer, findings []Finding) error {
	var out strings.Builder
	for i, f := range findings {
		if i == maxShown {
			fmt.Fprintf(&out, "archcheck: %d more findings are not shown\n", len(findings)-maxShown)
			break
		}
		out.WriteString(f.String())
		out.WriteString("\n")
	}
	if _, err := io.WriteString(w, out.String()); err != nil {
		return fmt.Errorf("write the findings: %w", err)
	}
	return nil
}

// quote returns s as a Go string literal, which escapes each character that is
// not printable and each invalid byte. Use it for import paths and other names
// from input files.
func quote(s string) string {
	return strconv.Quote(s)
}

// quoteEach returns each entry as a Go string literal.
func quoteEach(entries []string) []string {
	quoted := make([]string, len(entries))
	for i, entry := range entries {
		quoted[i] = quote(entry)
	}
	return quoted
}

// Clean returns at most maxText bytes of s, with each character that is not
// printable and each invalid byte escaped. Use it for each text that can come
// from input files, Git, or a decoder, so the text cannot add a line or hide a
// part of the output.
func Clean(s string) string {
	if len(s) > maxText {
		s = s[:maxText] + "..."
	}
	if utf8.ValidString(s) && !strings.ContainsFunc(s, func(r rune) bool { return !strconv.IsPrint(r) }) {
		return s
	}
	quoted := strconv.Quote(s)
	return quoted[1 : len(quoted)-1]
}
