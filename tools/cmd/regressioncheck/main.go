// Command regressioncheck runs the regression test check of ADR-065 on the
// change from a base revision to HEAD.
//
// Usage:
//
//	regressioncheck -base REV [-repo DIR] [-issue N] [-bug]
//
// The working tree must hold the head revision. -issue is the issue number of
// the branch, or 0 when the branch names no issue. -bug states that the issue
// has the bug label. The exit status is 0 when the check passes, 1 when it
// finds a violation, and 2 when it cannot run.
package main

import (
	"context"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"strings"
	"syscall"

	"github.com/OpenRAE/lilrae/tools/internal/checkcmd"
	"github.com/OpenRAE/lilrae/tools/internal/regression"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	code := run(ctx, os.Args[1:], os.Stdout, os.Stderr)
	stop()
	os.Exit(code)
}

func run(ctx context.Context, args []string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("regressioncheck", flag.ContinueOnError)
	flags.SetOutput(stderr)
	var cfg regression.Config
	flags.StringVar(&cfg.Repo, "repo", ".", "a directory in the working tree of the head revision")
	flags.StringVar(&cfg.Base, "base", "", "the base revision of the change (required)")
	flags.IntVar(&cfg.Issue, "issue", 0, "the issue number of the branch, or 0 for none")
	flags.BoolVar(&cfg.Bug, "bug", false, "the issue has the bug label")
	if code, stop := checkcmd.Parse(flags, args); stop {
		return code
	}
	if cfg.Base == "" || cfg.Issue < 0 || flags.NArg() != 0 {
		return checkcmd.Write(stderr, "regressioncheck: -base is required, -issue is not negative, and no argument follows the flags\n", checkcmd.Error)
	}
	report, err := regression.Check(ctx, cfg)
	if err != nil {
		return checkcmd.Write(stderr, fmt.Sprintf("regressioncheck: %v\n", err), checkcmd.Error)
	}
	var out strings.Builder
	fmt.Fprintf(&out, "regressioncheck: base %s, head %s\n", report.Base, report.Head)
	if cfg.Issue == 0 {
		out.WriteString("regressioncheck: the branch names no issue, so no test is replayed\n")
	} else {
		fmt.Fprintf(&out, "regressioncheck: issue #%d, bug label %t, %d test(s) replayed\n", cfg.Issue, cfg.Bug, len(report.Selected))
		for _, t := range report.Selected {
			fmt.Fprintf(&out, "  %s: %s\n", t.File, t.Name)
		}
	}
	for _, f := range report.Findings {
		fmt.Fprintln(&out, f)
	}
	if len(report.Findings) == 0 {
		return checkcmd.Write(stdout, out.String(), checkcmd.Pass)
	}
	fmt.Fprintf(&out, "regressioncheck: %d finding(s)\n", len(report.Findings))
	return checkcmd.Write(stdout, out.String(), checkcmd.Fail)
}
