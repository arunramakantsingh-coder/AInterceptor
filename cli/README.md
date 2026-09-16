# AInterceptor CLI

CLI-M0 establishes the AInterceptor command-line control plane.

## Start

From the repository root:

    .\scripts\ainterceptor.ps1

The root `ainterceptor.cmd` provides a Windows command launcher.

## Global context

Commands: help, providers, status, use <provider>, sessions, diagnostics, version, clear, exit, quit.

## Provider context

Commands: help, status, session, chat, diagnostics, doctor, back, exit.

CLI-M0 does not duplicate provider transport logic. `chat` remains intentionally unwired until the runtime integration milestone.
