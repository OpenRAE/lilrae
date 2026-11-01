//go:build integration

package conformance_test

import (
	"os"
	"path/filepath"
	"testing"
)

// scenarioVar names the scenario file that the lab cases start.
const scenarioVar = "LILRAE_CONFORMANCE_SCENARIO"

// TestLab runs the lab cases. They need a Docker daemon that only the lab
// owns, and the scenario that LILRAE_CONFORMANCE_SCENARIO names by an
// absolute path.
func TestLab(t *testing.T) {
	scenario := os.Getenv(scenarioVar)
	if !filepath.IsAbs(scenario) {
		t.Fatalf("%s must name the scenario of the lab cases by an absolute path; it is %q", scenarioVar, scenario)
	}
	runCases(t, filepath.Join("testdata", "lab"), map[string]string{scenarioVar: scenario})
}
