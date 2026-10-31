// Command mutationcheck runs the mutation test gate of ADR-065.
//
// Usage:
//
//	mutationcheck -gremlins PATH -thresholds FILE [-repo DIR] [-base REV] MODULE...
//
// Each MODULE is the directory of a Go module with packages, relative to the
// repository root. With -base, Gremlins mutates the changed production lines
// from REV to HEAD in each module that has changed production files. Without
// -base, it mutates each whole module. The exit status is 0 when the gate
// passes, 1 when it finds a violation, and 2 when it cannot run.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"strings"
	"syscall"

	"github.com/OpenRAE/lilrae/tools/internal/mutation"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	code := run(ctx, os.Args[1:], os.Stdout, os.Stderr)
	stop()
	os.Exit(code)
}

func run(ctx context.Context, args []string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("mutationcheck", flag.ContinueOnError)
	flags.SetOutput(stderr)
	cfg := mutation.Config{Log: stderr}
	flags.StringVar(&cfg.Repo, "repo", ".", "a directory in the working tree of the head revision")
	flags.StringVar(&cfg.Base, "base", "", "the base revision of the change; empty for a full run")
	flags.StringVar(&cfg.Gremlins, "gremlins", "", "the path of the gremlins program (required)")
	flags.StringVar(&cfg.Thresholds, "thresholds", "", "the path of the thresholds file (required)")
	flags.IntVar(&cfg.Workers, "workers", 0, "the number of mutants that Gremlins tests at the same time; 0 for one per CPU")
	flags.IntVar(&cfg.TimeoutCoefficient, "timeout-coefficient", 0, "the multiple of the first test run time that a mutant may take; 0 for the Gremlins default")
	if err := flags.Parse(args); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return 0
		}
		return 2
	}
	cfg.Modules = flags.Args()
	if cfg.Gremlins == "" || cfg.Thresholds == "" {
		return write(stderr, "mutationcheck: -gremlins and -thresholds are required\n", 2)
	}
	report, err := mutation.Check(ctx, cfg)
	if err != nil {
		return write(stderr, fmt.Sprintf("mutationcheck: %v\n", err), 2)
	}
	text := summary(report)
	if len(report.Findings) == 0 {
		return write(stdout, text, 0)
	}
	return write(stdout, text+fmt.Sprintf("mutationcheck: %d finding(s)\n", len(report.Findings)), 1)
}

// summary returns the scope, the counts, the measures, and the findings of a
// report.
func summary(report mutation.Report) string {
	var out strings.Builder
	writeScope(&out, report)
	c := report.Counts
	fmt.Fprintf(&out, "mutationcheck: killed %d, lived %d, not covered %d, timed out %d, not viable %d\n",
		c.Killed, c.Lived, c.NotCovered, c.TimedOut, c.NotViable)
	if efficacy, ok := c.Efficacy(); ok {
		fmt.Fprintf(&out, "mutationcheck: efficacy %.2f%% (threshold %g%%)\n", efficacy, report.Thresholds.Efficacy)
	}
	if coverage, ok := c.MutantCoverage(); ok {
		fmt.Fprintf(&out, "mutationcheck: mutant coverage %.2f%% (threshold %g%%)\n", coverage, report.Thresholds.MutantCoverage)
	} else if c.TimedOut == 0 && len(report.Changed) > 0 {
		out.WriteString("mutationcheck: the changed lines hold no mutant\n")
	}
	for _, f := range report.Findings {
		fmt.Fprintln(&out, f)
	}
	return out.String()
}

// writeScope writes what the run mutated.
func writeScope(out *strings.Builder, report mutation.Report) {
	if report.Base == "" {
		fmt.Fprintf(out, "mutationcheck: full run of %d module(s)\n", len(report.Mutated))
		return
	}
	if len(report.Changed) == 0 {
		fmt.Fprintf(out, "mutationcheck: base %s: no Go production file changed, so no relevant input changed\n", report.Base)
		return
	}
	fmt.Fprintf(out, "mutationcheck: base %s: %d changed production file(s) in %d module(s)\n", report.Base, len(report.Changed), len(report.Mutated))
	for _, file := range report.Changed {
		fmt.Fprintf(out, "  %s\n", file)
	}
}

// write writes text to w and returns code, or 2 when the write fails.
func write(w io.Writer, text string, code int) int {
	if _, err := io.WriteString(w, text); err != nil {
		return 2
	}
	return code
}
