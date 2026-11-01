package checkcmd_test

import (
	"bytes"
	"errors"
	"flag"
	"testing"

	"github.com/OpenRAE/lilrae/tools/internal/checkcmd"
)

func TestParse(t *testing.T) {
	t.Parallel()
	tests := []struct {
		args     []string
		wantCode int
		wantStop bool
		wantOut  bool
	}{
		{args: []string{"-n", "3", "rest"}, wantCode: checkcmd.Pass},
		{args: []string{"-help"}, wantCode: checkcmd.Pass, wantStop: true, wantOut: true},
		{args: []string{"-unknown"}, wantCode: checkcmd.Error, wantStop: true, wantOut: true},
	}
	for _, tc := range tests {
		var out bytes.Buffer
		flags := flag.NewFlagSet("check", flag.ContinueOnError)
		flags.SetOutput(&out)
		n := flags.Int("n", 0, "a number")

		code, stop := checkcmd.Parse(flags, tc.args)

		if code != tc.wantCode || stop != tc.wantStop {
			t.Errorf("Parse(%q) = %d, %t; want %d, %t", tc.args, code, stop, tc.wantCode, tc.wantStop)
		}
		if (out.Len() > 0) != tc.wantOut {
			t.Errorf("Parse(%q) wrote %q; want output %t", tc.args, out.String(), tc.wantOut)
		}
		if !stop && (*n != 3 || flags.NArg() != 1) {
			t.Errorf("Parse(%q) parsed n = %d and %d arguments; want 3 and 1", tc.args, *n, flags.NArg())
		}
	}
}

// failingWriter fails each write.
type failingWriter struct{}

func (failingWriter) Write([]byte) (int, error) {
	return 0, errors.New("write failed")
}

func TestWrite(t *testing.T) {
	t.Parallel()
	var out bytes.Buffer
	if got := checkcmd.Write(&out, "text\n", checkcmd.Fail); got != checkcmd.Fail || out.String() != "text\n" {
		t.Errorf("Write() = %d and wrote %q; want %d and %q", got, out.String(), checkcmd.Fail, "text\n")
	}
	if got := checkcmd.Write(failingWriter{}, "text\n", checkcmd.Pass); got != checkcmd.Error {
		t.Errorf("Write(failing writer) = %d, want %d", got, checkcmd.Error)
	}
}
