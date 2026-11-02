// Package mutation implements the mutation test gate of ADR-065.
//
// The gate runs Gremlins in each Go module that has changed production files,
// with --diff at the base revision, or in each module for a full run. It reads
// the JSON report of Gremlins and applies the thresholds itself, because the
// threshold flags of Gremlins v0.6.0 have no effect.
//
// Efficacy is killed mutants divided by killed and lived mutants. Mutant
// coverage is killed and lived mutants divided by killed, lived, and uncovered
// mutants. Mutants that do not compile and mutants that time out count in
// neither value.
package mutation
