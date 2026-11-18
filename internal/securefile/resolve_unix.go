//go:build linux || darwin

package securefile

import (
	"io/fs"
	"os"
	"slices"
	"strings"
)

const separator = "/"

// part is one entry of the stack of unresolved parts. An entry with a link
// marks that the target of that link is resolved when the entry is popped.
type part struct {
	name string
	link string
}

// linkState is the resolved target of a link, or a link whose target is
// still in resolution.
type linkState struct {
	target string
	done   bool
}

// resolver holds the state of one resolution.
type resolver struct {
	path string
	rest []part
	seen map[string]linkState
}

// resolve applies posixpath.realpath of Python 3.14 with strict=False. It
// resolves each part under the result so far, it follows a link through the
// parts of its target, so a missing part of a target stays as written, and
// ".." goes to the parent of the result so far. A part that cannot be read,
// or a link loop, stays as written.
func resolve(path string) (string, error) {
	r := resolver{path: separator, seen: map[string]linkState{}}
	if !strings.HasPrefix(path, separator) {
		wd, err := os.Getwd()
		if err != nil {
			return "", failure("resolve", path, err)
		}
		r.path = wd
	}
	r.push(path)
	for len(r.rest) > 0 {
		next := r.rest[len(r.rest)-1]
		r.rest = r.rest[:len(r.rest)-1]
		if next.link != "" {
			r.seen[next.link] = linkState{target: r.path, done: true}
			continue
		}
		r.step(next.name)
	}
	return r.path, nil
}

// push adds the parts of path to the stack, so that the first part pops first.
func (r *resolver) push(path string) {
	parts := strings.Split(path, separator)
	slices.Reverse(parts)
	for _, name := range parts {
		r.rest = append(r.rest, part{name: name})
	}
}

// step resolves one part name under the result so far.
func (r *resolver) step(name string) {
	switch name {
	case "", ".":
		return
	case "..":
		r.path = r.path[:strings.LastIndex(r.path, separator)]
		if r.path == "" {
			r.path = separator
		}
		return
	}
	next := strings.TrimSuffix(r.path, separator) + separator + name
	info, err := os.Lstat(next)
	if err != nil || info.Mode()&fs.ModeSymlink == 0 {
		r.path = next
		return
	}
	if state, ok := r.seen[next]; ok {
		// A link that is still in resolution is a loop, and it stays as
		// written.
		r.path = next
		if state.done {
			r.path = state.target
		}
		return
	}
	target, err := os.Readlink(next)
	if err != nil {
		r.path = next
		return
	}
	if strings.HasPrefix(target, separator) {
		r.path = separator
	}
	r.seen[next] = linkState{}
	r.rest = append(r.rest, part{link: next})
	r.push(target)
}
