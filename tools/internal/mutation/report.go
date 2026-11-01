package mutation

import (
	"encoding/json/v2"
	"fmt"
	"path"
)

// The statuses of a mutant in a Gremlins report.
const (
	statusKilled     = "KILLED"
	statusLived      = "LIVED"
	statusNotCovered = "NOT COVERED"
	statusTimedOut   = "TIMED OUT"
	statusNotViable  = "NOT VIABLE"
	statusSkipped    = "SKIPPED"
	statusRunnable   = "RUNNABLE"
)

// Mutant is a mutant that Gremlins tested.
type Mutant struct {
	// File is the repository path of the mutated file.
	File   string
	Line   int
	Column int
	// Type is the Gremlins mutator, for example CONDITIONALS_BOUNDARY.
	Type string
	// Status is the Gremlins status, for example LIVED.
	Status string
}

// Counts are the numbers of tested mutants by status.
type Counts struct {
	Killed, Lived, NotCovered, TimedOut, NotViable int
}

func (c Counts) add(other Counts) Counts {
	return Counts{
		Killed:     c.Killed + other.Killed,
		Lived:      c.Lived + other.Lived,
		NotCovered: c.NotCovered + other.NotCovered,
		TimedOut:   c.TimedOut + other.TimedOut,
		NotViable:  c.NotViable + other.NotViable,
	}
}

// Efficacy returns killed mutants divided by killed and lived mutants, in
// percent. It reports false when no mutant was killed or lived.
func (c Counts) Efficacy() (float64, bool) {
	if c.Killed+c.Lived == 0 {
		return 0, false
	}
	return 100 * float64(c.Killed) / float64(c.Killed+c.Lived), true
}

// MutantCoverage returns killed and lived mutants divided by killed, lived,
// and uncovered mutants, in percent. It reports false when there are none.
func (c Counts) MutantCoverage() (float64, bool) {
	if c.Killed+c.Lived+c.NotCovered == 0 {
		return 0, false
	}
	return 100 * float64(c.Killed+c.Lived) / float64(c.Killed+c.Lived+c.NotCovered), true
}

// gremlinsReport holds the fields of a Gremlins JSON report that the gate
// reads. Gremlins owns the format, so other members are ignored.
type gremlinsReport struct {
	Files []struct {
		FileName  string `json:"file_name"`
		Mutations []struct {
			Type   string `json:"type"`
			Status string `json:"status"`
			Line   int    `json:"line"`
			Column int    `json:"column"`
		} `json:"mutations"`
	} `json:"files"`
}

// readReport decodes the Gremlins report of module and returns its counts and
// the mutants that lived or are not covered. Skipped mutants are outside the
// changed lines and do not count.
func readReport(data []byte, module string) (Counts, []Mutant, error) {
	var report gremlinsReport
	if err := json.Unmarshal(data, &report); err != nil {
		return Counts{}, nil, fmt.Errorf("decode the Gremlins report of %s: %w", module, err)
	}
	var counts Counts
	var open []Mutant
	for _, file := range report.Files {
		if file.FileName == "" {
			return Counts{}, nil, fmt.Errorf("the Gremlins report of %s has a file without a name", module)
		}
		for _, m := range file.Mutations {
			if m.Line < 1 || m.Type == "" {
				return Counts{}, nil, fmt.Errorf("the Gremlins report of %s has a mutant without a line or a type in %s", module, file.FileName)
			}
			mutant := Mutant{File: path.Join(module, file.FileName), Line: m.Line, Column: m.Column, Type: m.Type, Status: m.Status}
			switch m.Status {
			case statusKilled:
				counts.Killed++
			case statusLived:
				counts.Lived++
				open = append(open, mutant)
			case statusNotCovered:
				counts.NotCovered++
				open = append(open, mutant)
			case statusTimedOut:
				counts.TimedOut++
			case statusNotViable:
				counts.NotViable++
			case statusSkipped:
			case statusRunnable:
				return Counts{}, nil, fmt.Errorf("the Gremlins report of %s is a dry run", module)
			default:
				return Counts{}, nil, fmt.Errorf("the Gremlins report of %s has the unknown status %q", module, m.Status)
			}
		}
	}
	return counts, open, nil
}
