package mutation

import (
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestGremlinsEnvAddsToTheExistingSettings(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		env  []string
		want []string
	}{
		{
			name: "empty",
			env:  []string{"PATH=/bin"},
			want: []string{"PATH=/bin", "GOWORK=off", "GOFLAGS=-count=1",
				"GIT_CONFIG_KEY_0=diff.relative", "GIT_CONFIG_VALUE_0=true", "GIT_CONFIG_COUNT=1"},
		},
		{
			name: "existing",
			env:  []string{"GOFLAGS=-mod=readonly", "GIT_CONFIG_COUNT=2"},
			want: []string{"GOFLAGS=-mod=readonly", "GIT_CONFIG_COUNT=2", "GOWORK=off", "GOFLAGS=-mod=readonly -count=1",
				"GIT_CONFIG_KEY_2=diff.relative", "GIT_CONFIG_VALUE_2=true", "GIT_CONFIG_COUNT=3"},
		},
		{
			name: "negative count",
			env:  []string{"GIT_CONFIG_COUNT=-1"},
			want: []string{"GIT_CONFIG_COUNT=-1", "GOWORK=off", "GOFLAGS=-count=1",
				"GIT_CONFIG_KEY_0=diff.relative", "GIT_CONFIG_VALUE_0=true", "GIT_CONFIG_COUNT=1"},
		},
		{
			name: "invalid count",
			env:  []string{"GIT_CONFIG_COUNT=x"},
			want: []string{"GIT_CONFIG_COUNT=x", "GOWORK=off", "GOFLAGS=-count=1",
				"GIT_CONFIG_KEY_0=diff.relative", "GIT_CONFIG_VALUE_0=true", "GIT_CONFIG_COUNT=1"},
		},
	}
	for _, tc := range tests {
		if diff := cmp.Diff(tc.want, gremlinsEnv(tc.env)); diff != "" {
			t.Errorf("gremlinsEnv(%q) mismatch (-want +got):\n%s", tc.env, diff)
		}
	}
}
