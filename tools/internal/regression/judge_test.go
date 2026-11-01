package regression

import (
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestJudgeQuotesTheBuildOutputOnlyWhenThereIsSome(t *testing.T) {
	t.Parallel()
	test := Test{File: "calc/calc_test.go", Name: "TestValue"}
	tests := []struct {
		run  testRun
		want string
	}{
		{
			run:  testRun{buildFailed: true},
			want: "TestValue: the test does not build on the head revision",
		},
		{
			run:  testRun{buildFailed: true, buildOutput: []string{"# calc", "undefined: x"}},
			want: "TestValue: the test does not build on the head revision: # calc; undefined: x",
		},
	}
	for _, tc := range tests {
		got := judge(test, "head", passed, tc.run)
		want := []Finding{{Location: test.File, Message: tc.want}}
		if diff := cmp.Diff(want, got); diff != "" {
			t.Errorf("judge(%+v) mismatch (-want +got):\n%s", tc.run, diff)
		}
	}
}
