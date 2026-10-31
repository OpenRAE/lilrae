package mutation

import (
	"encoding/json/v2"
	"fmt"
)

// Thresholds are the lowest accepted percentages of the gate.
type Thresholds struct {
	// Efficacy is the lowest accepted efficacy, in percent.
	Efficacy float64 `json:"efficacy"`
	// MutantCoverage is the lowest accepted mutant coverage, in percent.
	MutantCoverage float64 `json:"mutant_coverage"`
}

// ParseThresholds decodes a thresholds file. Each threshold must be present,
// greater than 0, and at most 100. Unknown members are rejected.
func ParseThresholds(data []byte) (Thresholds, error) {
	var file struct {
		Efficacy       *float64 `json:"efficacy"`
		MutantCoverage *float64 `json:"mutant_coverage"`
	}
	if err := json.Unmarshal(data, &file, json.RejectUnknownMembers(true)); err != nil {
		return Thresholds{}, fmt.Errorf("decode the mutation thresholds: %w", err)
	}
	fields := []struct {
		name  string
		value *float64
	}{{"efficacy", file.Efficacy}, {"mutant_coverage", file.MutantCoverage}}
	for _, field := range fields {
		if field.value == nil || *field.value <= 0 || *field.value > 100 {
			return Thresholds{}, fmt.Errorf("mutation threshold %q must be greater than 0 and at most 100", field.name)
		}
	}
	return Thresholds{Efficacy: *file.Efficacy, MutantCoverage: *file.MutantCoverage}, nil
}

// lowered returns the names of the thresholds of t that are lower than those
// of old.
func (t Thresholds) lowered(old Thresholds) []string {
	var names []string
	if t.Efficacy < old.Efficacy {
		names = append(names, fmt.Sprintf("efficacy %g < %g", t.Efficacy, old.Efficacy))
	}
	if t.MutantCoverage < old.MutantCoverage {
		names = append(names, fmt.Sprintf("mutant_coverage %g < %g", t.MutantCoverage, old.MutantCoverage))
	}
	return names
}
