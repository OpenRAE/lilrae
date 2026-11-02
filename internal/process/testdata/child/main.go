// Command child provides finite, harmless processes for runner tests.
package main

import (
	"bytes"
	"fmt"
	"io"
	"os"
	"os/exec"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"
)

func main() {
	mode, args := os.Args[1], os.Args[2:]
	switch mode {
	case "echo":
		_, err := io.Copy(os.Stdout, os.Stdin)
		check(err)
	case "touch":
		check(os.WriteFile(args[0], []byte("launched"), 0600))
	case "signal":
		selfSignal()
	case "args":
		_, err := io.WriteString(os.Stdout, strings.Join(args, "\n")+"\n")
		check(err)
	case "output":
		_, err := io.WriteString(os.Stdout, args[0])
		check(err)
		_, err = io.WriteString(os.Stderr, args[1])
		check(err)
	case "exit":
		code, err := strconv.Atoi(args[0])
		check(err)
		os.Exit(code)
	case "sleep":
		time.Sleep(time.Minute)
	case "duplex":
		_, err := os.Stdout.Write(bytes.Repeat([]byte("x"), 1<<20))
		check(err)
		got, err := io.ReadAll(os.Stdin)
		check(err)
		if !bytes.Equal(got, bytes.Repeat([]byte("x"), 1<<20)) {
			os.Exit(5)
		}
	case "environment":
		dir, err := os.Getwd()
		check(err)
		_, err = fmt.Fprintf(os.Stdout, "%s\n%s\n%s\n", dir, os.Getenv("CANARY"), os.Getenv("LILRAE_PROCESS_AMBIENT"))
		check(err)
	case "flood":
		end := time.Now().Add(time.Minute)
		block := bytes.Repeat([]byte("x"), 4096)
		for time.Now().Before(end) {
			_, err := os.Stdout.Write(block)
			check(err)
		}
	case "spawn":
		spawn(args)
	case "stubborn", "graceful", "detached":
		helper(mode, args)
	default:
		os.Exit(3)
	}
}

func spawn(args []string) {
	exe, err := os.Executable()
	check(err)
	cmd := exec.Command(exe, args[0], args[2])
	cmd.Stdout, cmd.Stderr = os.Stdout, os.Stderr
	if args[0] == "detached" {
		detach(cmd)
	}
	check(cmd.Start())
	end := time.Now().Add(10 * time.Second)
	for {
		if _, err := os.Stat(args[2]); err == nil {
			break
		}
		if time.Now().After(end) {
			os.Exit(6)
		}
		time.Sleep(time.Millisecond)
	}
	switch args[1] {
	case "exit":
		_, err := io.WriteString(os.Stdout, "result")
		check(err)
	case "nonzero":
		os.Exit(7)
	case "overflow":
		_, err := os.Stdout.Write(bytes.Repeat([]byte("x"), 4096))
		check(err)
		time.Sleep(time.Minute)
	case "hang":
		time.Sleep(time.Minute)
	}
}

func helper(mode string, args []string) {
	stop := make(chan os.Signal, 2)
	if mode == "graceful" {
		signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	} else {
		signal.Ignore(os.Interrupt, syscall.SIGTERM)
	}
	check(os.WriteFile(args[0], []byte(strconv.Itoa(os.Getpid())), 0600))
	select {
	case <-stop:
		time.Sleep(120 * time.Millisecond)
		check(os.WriteFile(args[0]+".finished", []byte("finished"), 0600))
	case <-time.After(time.Minute):
	}
}

func check(err error) {
	if err != nil {
		os.Exit(4)
	}
}
