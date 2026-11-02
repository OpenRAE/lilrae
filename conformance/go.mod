module github.com/OpenRAE/lilrae/conformance

// The conformance suite is a module of its own: it holds test files only,
// and its tests need an installed lilrae binary. Thus go test ./... and the
// mutation gate in the product module do not run it.
go 1.27.3

require (
	github.com/itchyny/gojq v0.12.19
	github.com/rogpeppe/go-internal v1.16.0
	github.com/santhosh-tekuri/jsonschema/v6 v6.0.3
	github.com/yuin/goldmark v1.8.7
)

require (
	github.com/itchyny/timefmt-go v0.1.8 // indirect
	golang.org/x/sys v0.49.0 // indirect
	golang.org/x/text v0.43.0 // indirect
	golang.org/x/tools v0.52.0 // indirect
)
