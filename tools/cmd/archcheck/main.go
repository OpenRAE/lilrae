// Command archcheck checks a repository and its design notes against the
// architecture model of ADR-065 (architecture/model.yaml).
//
// Usage:
//
//	archcheck check [-repo DIR]
//	archcheck design [-repo DIR] -base REV FILE
//	archcheck pr [-repo DIR] -base REV [-issue N] [-promotion]
//	archcheck diagram [-repo DIR] [-doc FILE] [-write]
//
// check checks the whole repository. design checks the design record of a
// design note before the code exists. pr checks the whole repository and then
// the change from REV to HEAD against the design record of issue N. diagram
// checks, or with -write replaces, the generated diagram of the model. A
// relative FILE or -doc path is relative to the top of the working tree. The
// exit status is 0 when the check passes, 1 when it finds a violation, and 2
// when it cannot run.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"syscall"

	"github.com/OpenRAE/lilrae/tools/internal/architecture"
	"github.com/OpenRAE/lilrae/tools/internal/checkcmd"
)

const usage = "usage: archcheck check|design|pr|diagram [flags]\n"

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	code := run(ctx, os.Args[1:], os.Stdout, os.Stderr)
	stop()
	os.Exit(code)
}

func run(ctx context.Context, args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		return checkcmd.Write(stderr, usage, checkcmd.Error)
	}
	name := args[0]
	flags := flag.NewFlagSet("archcheck "+name, flag.ContinueOnError)
	flags.SetOutput(stderr)
	cmd, ok := newCommand(ctx, name, flags)
	if !ok {
		return checkcmd.Write(stderr, usage, checkcmd.Error)
	}
	if code, stop := checkcmd.Parse(flags, args[1:]); stop {
		return code
	}
	if flags.NArg() != cmd.args {
		return checkcmd.Write(stderr, fmt.Sprintf("archcheck: %s takes %d argument(s) after the flags\n", name, cmd.args), checkcmd.Error)
	}
	report, err := cmd.run(flags.Args())
	if err != nil {
		return checkcmd.Write(stderr, "archcheck: "+architecture.Clean(err.Error())+"\n", checkcmd.Error)
	}
	if len(report.Findings) == 0 {
		return checkcmd.Write(stdout, "archcheck: "+name+" passed\n", checkcmd.Pass)
	}
	if err := architecture.Write(stdout, report.Findings); err != nil {
		return checkcmd.Error
	}
	return checkcmd.Write(stdout, fmt.Sprintf("archcheck: %d finding(s)\n", len(report.Findings)), checkcmd.Fail)
}

// command is a subcommand.
type command struct {
	// args is the number of arguments after the flags.
	args int
	// run runs the check after the flags are parsed.
	run func(args []string) (architecture.Report, error)
}

// newCommand defines the flags of the subcommand name and returns it. It
// reports false for an unknown name.
func newCommand(ctx context.Context, name string, flags *flag.FlagSet) (command, bool) {
	repo := flags.String("repo", ".", "a directory in the working tree")
	switch name {
	case "check":
		return command{run: func([]string) (architecture.Report, error) { return architecture.Check(ctx, *repo) }}, true
	case "design":
		base := flags.String("base", "", "the base revision of the change (required)")
		return command{args: 1, run: func(args []string) (architecture.Report, error) {
			if *base == "" {
				return architecture.Report{}, errors.New("design needs -base")
			}
			return architecture.CheckDesign(ctx, *repo, *base, args[0])
		}}, true
	case "pr":
		var cfg architecture.PRConfig
		flags.StringVar(&cfg.Base, "base", "", "the base revision of the change (required)")
		flags.IntVar(&cfg.Issue, "issue", 0, "the issue of the branch, or 0 for none")
		flags.BoolVar(&cfg.Promotion, "promotion", false, "the head is a protected branch of this repository")
		return command{run: func([]string) (architecture.Report, error) {
			cfg.Repo = *repo
			if cfg.Base == "" || cfg.Issue < 0 {
				return architecture.Report{}, errors.New("pr needs -base and an issue that is not negative")
			}
			return architecture.CheckPullRequest(ctx, cfg)
		}}, true
	case "diagram":
		doc := flags.String("doc", "docs/architecture/go-architecture.md", "the document with the generated diagram")
		writeDoc := flags.Bool("write", false, "replace the generated diagram")
		return command{run: func([]string) (architecture.Report, error) {
			return architecture.Diagram(ctx, *repo, *doc, *writeDoc)
		}}, true
	}
	return command{}, false
}
