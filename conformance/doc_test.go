// Package conformance_test runs the black-box contract cases of ADR-065
// against an installed lilrae binary.
//
// LILRAE_CONFORMANCE_BINARY names the binary by an absolute path. The cases in
// testdata/cases need no lab. The cases in testdata/lab need a Docker daemon;
// their test has the integration build tag. docs/reference/schemas holds the
// published JSON Schemas that the cases check, and
// docs/reference/conformance-inventory.md maps each contract to its case.
package conformance_test
