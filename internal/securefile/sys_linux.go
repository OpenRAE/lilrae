package securefile

import "golang.org/x/sys/unix"

// searchFlag opens a directory to search it, which needs execute permission
// only (O_PATH).
const searchFlag = unix.O_PATH

// statMode returns the mode of a file status.
func statMode(st *unix.Stat_t) uint32 {
	return st.Mode
}
