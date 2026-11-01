// Package gates_test runs each gate of tools/ci/go-gates.sh, with the pinned
// tools and the repository configuration, on a fixture that fails and on a
// fixture that passes.
package gates_test

import (
	"encoding/json/v2"
	"os"
	"os/exec"
	"path/filepath"
	"testing"

	"github.com/rogpeppe/go-internal/testscript"
)

// goEnv returns the Go settings that the scripts inherit. A script runs with
// an empty home directory, so the go command needs its cache paths.
func goEnv(t *testing.T) map[string]string {
	t.Helper()
	out, err := exec.CommandContext(t.Context(), "go", "env", "-json",
		"GOCACHE", "GOMODCACHE", "GOPATH", "GOPROXY", "GOSUMDB", "GONOSUMDB", "GOPRIVATE", "GOTOOLCHAIN", "GOFLAGS").Output()
	if err != nil {
		t.Fatalf("go env: %v", err)
	}
	env := map[string]string{}
	if err = json.Unmarshal(out, &env); err != nil {
		t.Fatalf("decode go env: %v", err)
	}
	cache, err := os.UserCacheDir()
	if err != nil {
		t.Fatalf("locate the user cache: %v", err)
	}
	env["GOLANGCI_LINT_CACHE"] = filepath.Join(cache, "golangci-lint")
	env["GOWORK"] = "off"
	env["GIT_CONFIG_NOSYSTEM"] = "1"
	return env
}

func TestGates(t *testing.T) {
	t.Parallel()
	repo, err := filepath.Abs(filepath.Join("..", ".."))
	if err != nil {
		t.Fatal(err)
	}
	env := goEnv(t)
	testscript.Run(t, testscript.Params{
		Dir: "testdata",
		Setup: func(e *testscript.Env) error {
			e.Setenv("REPO", repo)
			e.Setenv("GATES", filepath.Join(repo, "tools", "ci", "go-gates.sh"))
			for name, value := range env {
				e.Setenv(name, value)
			}
			return nil
		},
	})
}
