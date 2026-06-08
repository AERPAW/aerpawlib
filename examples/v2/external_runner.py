"""
external_runner will run and interact with some external processes.

Run with:
    aerpawlib --api-version v2 --script examples/v2/external_runner.py \
        --vehicle generic --conn udpin://127.0.0.1:14550
"""

import re

from aerpawlib.v2 import BasicRunner, ExternalProcess, entrypoint


class MyScript(BasicRunner):
    """Demonstrate how to run and interact with external processes."""

    @entrypoint
    async def do_stuff(self):
        # spit out ls output
        print("[example] Listing files with 'ls':")
        ls = ExternalProcess("ls")
        await ls.start()
        while line := await ls.read_line():
            print(line)

        # spit out ps output and wait for some kind of python to show up (this script)
        print("[example] Checking process list with 'ps aux':")
        ps = ExternalProcess("ps", params=["aux"])
        await ps.start()
        buff = await ps.wait_until_output(r"aerpaw")
        if buff:
            print(buff[-1])

        # talk interactively with cat
        print("[example] Talking interactively with 'cat':")
        cat = ExternalProcess("cat")
        await cat.start()
        await cat.send_input("dronegobrr\n")
        catized = await cat.read_line()
        print(f"cat echoed: {catized}")

        # ping loopback 5 times
        times = 5
        print(f"[example] Pinging 127.0.0.1 {times} times:")
        ping = ExternalProcess("ping", params=["127.0.0.1", "-c", str(times)])
        await ping.start()
        ping_re = re.compile(r".+icmp_seq=(?P<seq>\d+).+time=(?P<time>\d+(?:\.\d+)?) ms")
        while buff := await ping.wait_until_output(r"icmp_seq="):
            ping_re_match = ping_re.match(buff[-1])
            if ping_re_match:
                print(f"latency: {ping_re_match.group('time')} ms")
                if ping_re_match.group("seq") == str(times):
                    break
