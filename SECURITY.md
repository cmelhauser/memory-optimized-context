# Security policy

## Supported versions

The latest release. A fix arrives as a new patch release; older versions are not patched.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting: the **Report a vulnerability** button under this repository's
**Security** tab. It reaches the owner without making the report public. Please do not open a public issue for one.

Include the version, what you did, and what happened. Do not attach a memory store, a transcript or an export: they hold
someone's conversations. A minimal reproduction with invented text is enough.

## What counts

The tool reads files that other parties write (transcripts, cloned repositories, exports) and sends them to a language
model, then writes what comes back into files that every Claude Code session imports. These are in scope:

- a way to make the tool read a file outside the folder it was pointed at (see `inside()` in `bin/memory`);
- a model answer, or a document, that changes what a later session is told to do beyond the one line it may add;
- a way to make the MCP server answer a request from a host other than loopback or `--allowed-host`;
- two writers corrupting `memory.db` or `compiled/`, or a lost or invented lesson;
- anything in the image or the workflows that exposes a secret or lets an unreviewed change publish a release.

Out of scope: a Reflector that is wrong about what a conversation meant, a lesson you disagree with, and anything that
needs write access to your own `~/memory`, which already holds your data.
