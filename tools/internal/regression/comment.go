package regression

import (
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"regexp"
	"strconv"
	"strings"
	"unicode"
	"unicode/utf8"
)

// marker starts each line that the check reads as a regression comment.
const marker = "regression:"

var directivePattern = regexp.MustCompile(`^regression: #([1-9]\d{0,8})$`)

// testFunc is a top-level test function of a test file.
type testFunc struct {
	name string
	// line is the line of the func keyword.
	line int
	// issue is the issue of the regression comment, or 0 without one.
	issue int
	// source is the declaration without its doc comment.
	source []byte
}

// commentProblem is a regression comment that breaks the rules.
type commentProblem struct {
	line    int
	message string
}

// parseTestFile returns the test functions of a Go test file and the problems
// of its regression comments.
func parseTestFile(name string, src []byte) ([]testFunc, []commentProblem, error) {
	fset := token.NewFileSet()
	file, err := parser.ParseFile(fset, name, src, parser.ParseComments|parser.SkipObjectResolution)
	if err != nil {
		return nil, nil, fmt.Errorf("parse %s: %w", name, err)
	}
	funcs, byDoc := testFuncs(fset, file, src)
	issues := make([][]int, len(funcs))
	var problems []commentProblem
	for _, group := range file.Comments {
		index, onTest := byDoc[group]
		for _, c := range group.List {
			first := fset.Position(c.Pos()).Line
			for offset, line := range commentLines(c.Text) {
				issue, problem := readDirective(line, onTest)
				if problem != "" {
					problems = append(problems, commentProblem{line: first + offset, message: problem})
				} else if issue != 0 {
					issues[index] = append(issues[index], issue)
				}
			}
		}
	}
	return funcs, append(problems, assignIssues(funcs, issues)...), nil
}

// assignIssues sets the issue of each test function that has one regression
// comment, and returns a problem for each that has more than one.
func assignIssues(funcs []testFunc, issues [][]int) []commentProblem {
	var problems []commentProblem
	for i, found := range issues {
		switch len(found) {
		case 0:
		case 1:
			funcs[i].issue = found[0]
		default:
			problems = append(problems, commentProblem{
				line:    funcs[i].line,
				message: funcs[i].name + " has more than one regression comment",
			})
		}
	}
	return problems
}

// testFuncs returns the test functions of file and the index of each test
// function by its doc comment.
func testFuncs(fset *token.FileSet, file *ast.File, src []byte) (funcs []testFunc, byDoc map[*ast.CommentGroup]int) {
	testingName := importName(file, "testing")
	byDoc = map[*ast.CommentGroup]int{}
	for _, decl := range file.Decls {
		fn, ok := decl.(*ast.FuncDecl)
		if !ok || !isTest(fn, testingName) {
			continue
		}
		if fn.Doc != nil {
			byDoc[fn.Doc] = len(funcs)
		}
		start, end := fset.Position(fn.Pos()).Offset, fset.Position(fn.End()).Offset
		funcs = append(funcs, testFunc{
			name:   fn.Name.Name,
			line:   fset.Position(fn.Pos()).Line,
			source: src[start:end],
		})
	}
	return funcs, byDoc
}

// readDirective returns the issue of a regression comment line, or a problem.
// It returns neither for a line that is not a regression comment.
func readDirective(line string, onTest bool) (issue int, problem string) {
	if !strings.HasPrefix(line, marker) {
		return 0, ""
	}
	match := directivePattern.FindStringSubmatch(line)
	if match == nil {
		return 0, fmt.Sprintf("malformed regression comment %q; write \"regression: #<issue>\"", line)
	}
	if !onTest {
		return 0, "the regression comment is not in the doc comment of a test function"
	}
	issue, err := strconv.Atoi(match[1])
	if err != nil {
		return 0, fmt.Sprintf("malformed issue number in %q", line)
	}
	return issue, ""
}

// commentLines returns the lines of a comment without the comment markers and
// without surrounding space.
func commentLines(text string) []string {
	if body, ok := strings.CutPrefix(text, "//"); ok {
		return []string{strings.TrimSpace(body)}
	}
	body := strings.TrimSuffix(strings.TrimPrefix(text, "/*"), "*/")
	lines := strings.Split(body, "\n")
	for i, line := range lines {
		lines[i] = strings.TrimSpace(line)
	}
	return lines
}

// importName returns the name under which file imports path, or "" when file
// does not import it.
func importName(file *ast.File, path string) string {
	for _, spec := range file.Imports {
		if spec.Path.Value != strconv.Quote(path) {
			continue
		}
		if spec.Name != nil {
			return spec.Name.Name
		}
		return path
	}
	return ""
}

// isTest reports whether fn is a test function. Its name is Test followed by a
// part that does not start with a lower-case letter, and its one parameter is
// a pointer to [testing.T]. testingName is the name under which the file
// imports the testing package.
func isTest(fn *ast.FuncDecl, testingName string) bool {
	name, ok := strings.CutPrefix(fn.Name.Name, "Test")
	if !ok || fn.Recv != nil || fn.Type.TypeParams != nil || fn.Type.Results != nil || testingName == "" {
		return false
	}
	if r, _ := utf8.DecodeRuneInString(name); unicode.IsLower(r) {
		return false
	}
	params := fn.Type.Params.List
	if len(params) != 1 || len(params[0].Names) > 1 {
		return false
	}
	star, ok := params[0].Type.(*ast.StarExpr)
	if !ok {
		return false
	}
	sel, ok := star.X.(*ast.SelectorExpr)
	if !ok {
		return false
	}
	pkg, ok := sel.X.(*ast.Ident)
	return ok && pkg.Name == testingName && sel.Sel.Name == "T"
}
