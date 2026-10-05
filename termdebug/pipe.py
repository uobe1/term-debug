#!/usr/bin/env python3
"""pipe-pane sink: wraps pane output chunks into asciicast v2 o-events.

Spawned by the tmux server (one per pane, lifetime = pane lifetime):
    tmux pipe-pane -o -t %N "python3 pipe.py <session_dir>/raw.log"
Reads the v2 header line for the start timestamp, then appends one
[elapsed, "o", text] JSON line per input chunk, flushed immediately
(crash-safe). An incremental UTF-8 decoder keeps multi-byte characters
intact across chunk boundaries.
"""
import codecs
import json
import os
import sys
import time


def write_all(fd: int, data: bytes) -> None:
    while data:
        n = os.write(fd, data)
        data = data[n:]


def main() -> None:
    out_path = sys.argv[1]
    with open(out_path, "rb") as fh:
        header = json.loads(fh.readline())
    t0 = header.get("timestamp", time.time())
    dec = codecs.getincrementaldecoder("utf-8")("replace")
    fd = os.open(out_path, os.O_WRONLY | os.O_APPEND)
    while True:
        chunk = os.read(0, 65536)
        if not chunk:
            break
        text = dec.decode(chunk)
        if not text:
            continue
        line = json.dumps([round(time.time() - t0, 6), "o", text],
                          ensure_ascii=False) + "\n"
        write_all(fd, line.encode("utf-8"))
    tail = dec.decode(b"", True)
    if tail:
        line = json.dumps([round(time.time() - t0, 6), "o", tail],
                          ensure_ascii=False) + "\n"
        write_all(fd, line.encode("utf-8"))
    os.close(fd)


if __name__ == "__main__":
    main()
