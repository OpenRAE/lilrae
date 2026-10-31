module github.com/OpenRAE/lilrae

// CI installs the release that the go directive names, and govulncheck
// checks the standard library of that release, so it names the patch release.
go 1.27.3

// Node.js trees hold third-party Go files. Package patterns such as ./...
// skip them.
ignore node_modules
