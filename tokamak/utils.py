import subprocess
import sys
import re
from gemeinsprache.utils import *
from functools import partial
from collections import deque


def logger(prefix, prefix_color=cyan, default_color=green):
    def log(msg, prefix=prefix, color=default_color):
        try:
            h, w = os.get_terminal_size()
        except OSError:
            h, w = 120, 80
        prefix = (prefix, "  ::  ")
        prefix_len = sum([len(part) for part in prefix])
        prefix = f"{prefix_color(prefix[0])}{grey(prefix[1])}"
        available_len = w - prefix_len
        formatted = []
        words = deque(msg.split(" "))
        while words:
            _msg = ""
            while len(_msg) < available_len:
                try:
                    _msg += f"{words.popleft()} "
                except IndexError:
                    break
            _pref = prefix if len(formatted) == 0 else " " * prefix_len
            formatted.append(_pref + color(_msg))

        formatted = '\n'.join(formatted)
        print(formatted)
    return partial(log, prefix=prefix)

def pp(obj):
    if not isinstance(obj, dict):
        if hasattr(obj, '__dict__'):
            obj = obj.__dict__
        else:
            print(f"Not a mapping: {obj}")
            return
    left_col = max(len(repr(k)) for k in obj.keys())
    right_col = 80 - left_col
    left_pad = " " * left_col
    i = 0
    right = []

    curr = []
    curr_len = 0
    for k, v in obj.items():
        i += 1
        curr = [
            f"{grey(str(i) + '.'):>4} {blue(k)} {' ' * (left_col - len(k))} :: "
        ]

        curr_len = 0
        for wd in re.split(r'\s+', repr(v)):
            curr_len += len(wd) + 1
            if curr_len > right_col:
                right.append(' '.join(curr))
                curr = [left_pad]
                curr_len = 0
            curr.append(wd)
        right.append(green(' '.join(curr)))
    right = '\n'.join(right)
    print(right)

    # print(f"{grey(str(i) + '.'):>4} {blue(k)} {' ' * (left_col - len(k))} :: {green(right)}")


def kill(pid):
    cmd = f"kill -9 {pid}"
    out = ""
    try:
        out = subprocess.check_call(cmd, shell=True).decode('utf-8')
    except subprocess.CalledProcessError as e:
        out = (
            "common::run_command() : [ERROR]: output = %s, error code = %s\n"
            % (e.output, e.returncode))
    finally:
        sys.stderr.write(out)
    return f"Exit code: {out}"


def pidofport(port, killall=False):
    cmd = f"fuser {port}/tcp"
    out = ""
    try:
        out = subprocess.check_output(cmd, shell=True).decode('utf-8')
    except subprocess.CalledProcessError as e:
        out = (
                "common::run_command() : [ERROR]: output = %s, error code = %s\n"
                % (e.output, e.returncode))
    finally:
        sys.stdout.write(out)
    pids = map(lambda x: int(x), re.findall(r'(\d+)', out)[1:])
    if killall:
        for pid in pids:
            kill(pid)

def conditional_breakpoint(assertion):
    result = assertion()
    if not result:
        log = logger('[ breakpoint ] ', default_color=red)
        pp({k:v for k,v in vars().items() if not k.startswith("_")})
        log(f"Breakpoint hit: {assertion} returned False.")
        breakpoint()