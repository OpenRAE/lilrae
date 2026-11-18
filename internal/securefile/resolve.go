package securefile

// Resolve returns the absolute form of path with each link resolved, as
// pathlib.Path.resolve of Python does. A part of path that does not exist
// stays as written. On Linux and macOS each part resolves from left to
// right, a link resolves through the parts of its target, and ".." goes to
// the parent of the resolved part. On Windows the path is first normalized,
// and Resolve reads the final path of the longest leading part that exists,
// so it also resolves a junction.
//
// Resolve gives a path to locate a directory. The caller opens that path
// with OpenDir or with a method of Dir, which apply the link rules.
func Resolve(path string) (string, error) {
	return resolve(path)
}
