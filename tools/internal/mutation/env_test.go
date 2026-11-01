package mutation

import (
	"os"
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestGremlinsEnvAddsToTheExistingSettings(t *testing.T) {
	t.Parallel()
	isolated := []string{"GOWORK=off", "GOFLAGS=-count=1", "GIT_CONFIG_GLOBAL=" + os.DevNull, "GIT_CONFIG_NOSYSTEM=1"}
	first := []string{"GIT_CONFIG_KEY_0=diff.relative", "GIT_CONFIG_VALUE_0=true",
		"GIT_CONFIG_KEY_1=diff.context", "GIT_CONFIG_VALUE_1=0", "GIT_CONFIG_COUNT=2"}
	tests := []struct {
		name string
		env  []string
		want []string
	}{
		{
			name: "empty",
			env:  []string{"PATH=/bin"},
			want: append(append([]string{"PATH=/bin"}, isolated...), first...),
		},
		{
			name: "existing",
			env:  []string{"GOFLAGS=-mod=readonly", "GIT_CONFIG_COUNT=2"},
			want: []string{"GOFLAGS=-mod=readonly", "GIT_CONFIG_COUNT=2", "GOWORK=off", "GOFLAGS=-mod=readonly -count=1",
				"GIT_CONFIG_GLOBAL=" + os.DevNull, "GIT_CONFIG_NOSYSTEM=1",
				"GIT_CONFIG_KEY_2=diff.relative", "GIT_CONFIG_VALUE_2=true",
				"GIT_CONFIG_KEY_3=diff.context", "GIT_CONFIG_VALUE_3=0", "GIT_CONFIG_COUNT=4"},
		},
		{
			name: "negative count",
			env:  []string{"GIT_CONFIG_COUNT=-1"},
			want: append(append([]string{"GIT_CONFIG_COUNT=-1"}, isolated...), first...),
		},
		{
			name: "invalid count",
			env:  []string{"GIT_CONFIG_COUNT=x"},
			want: append(append([]string{"GIT_CONFIG_COUNT=x"}, isolated...), first...),
		},
	}
	for _, tc := range tests {
		if diff := cmp.Diff(tc.want, gremlinsEnv(tc.env)); diff != "" {
			t.Errorf("%s: gremlinsEnv(%q) mismatch (-want +got):\n%s", tc.name, tc.env, diff)
		}
	}
}
