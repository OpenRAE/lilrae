module github.com/OpenRAE/lilrae

// CI installs the release that the go directive names, and govulncheck
// checks the standard library of that release, so it names the patch release.
go 1.27.3

// Node.js trees hold third-party Go files. Package patterns such as ./...
// skip them.
ignore node_modules

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
