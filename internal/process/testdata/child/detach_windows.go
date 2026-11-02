package main

import "os/exec"

func detach(_ *exec.Cmd) {}

func selfSignal() {}
