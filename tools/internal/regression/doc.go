// Package regression implements the regression test check of ADR-065.
//
// A regression test carries the line "regression: #<issue>" in the doc
// comment of its test function. For the issue of a pull request, the check
// replays each regression test that the change adds or changes. The test must
// fail on the base revision, with the test files and test data of the head
// revision, and it must pass on the head revision. A build failure, a skip, a
// test that does not run, and a test that does not finish do not satisfy the
// check.
package regression
