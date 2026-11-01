// Package clock reads the host clock and writes the UTC text forms that
// records store.
package clock

import "time"

// System reads the clock of the host. Its zero value is ready to use, and it
// satisfies an interface with a Now method that returns a [time.Time].
type System struct{}

// Now returns the current instant in UTC.
func (System) Now() time.Time {
	return time.Now().UTC()
}

// ISO returns t in UTC as Python's datetime.isoformat writes it, the
// continuity-now form: the seconds, a six-digit microsecond fraction when the
// microseconds are not zero, and the offset +00:00. It drops the part below
// a microsecond, as a Python datetime does.
func ISO(t time.Time) string {
	return format(t, "-07:00")
}

// ISOZ returns the text of ISO with Z for the offset, the utc-now form.
func ISOZ(t time.Time) string {
	return format(t, "Z07:00")
}

func format(t time.Time, offset string) string {
	t = t.UTC().Truncate(time.Microsecond)
	layout := "2006-01-02T15:04:05"
	if t.Nanosecond() != 0 {
		layout += ".000000"
	}
	return t.Format(layout + offset)
}
