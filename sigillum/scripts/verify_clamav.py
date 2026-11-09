"""Live ClamAV integration check for CI and deployment smoke tests.

Waits for the scanner's signature database to recognise the standard harmless
EICAR test string, then verifies a clean fixture returns CLEAN. The EICAR
string is a test signature, not executable malware.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sigillum.infrastructure.malware import ClamAVScanner

EICAR_TEST_STRING = (
    b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
)
CLEAN_FIXTURE = b"Sigillum clean ClamAV integration fixture. No executable content."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3310)
    parser.add_argument("--timeout", type=int, default=600, help="Maximum seconds to wait for signatures")
    args = parser.parse_args()
    deadline = time.monotonic() + max(30, args.timeout)
    scanner = ClamAVScanner(host=args.host, port=args.port, timeout_seconds=8)

    print(f"Waiting for ClamAV at {args.host}:{args.port} and for EICAR signatures...")
    last_status = "NOT_ATTEMPTED"
    while time.monotonic() < deadline:
        result = scanner.scan(EICAR_TEST_STRING)
        last_status = result.status
        if result.status == "INFECTED":
            print(f"EICAR test signature detected: {result.signature or 'signature reported'}")
            break
        if result.status == "CLEAN":
            print("ClamAV is responding, but its signature database has not recognised EICAR yet.")
        else:
            print(f"ClamAV not ready: {result.status} ({result.message or 'no detail'})")
        time.sleep(5)
    else:
        print(f"ClamAV did not recognise the EICAR test string before timeout; last status={last_status}.", file=sys.stderr)
        return 1

    clean_result = scanner.scan(CLEAN_FIXTURE)
    if clean_result.status != "CLEAN":
        print(
            f"Expected CLEAN for the harmless fixture, received {clean_result.status}: {clean_result.message or 'no detail'}",
            file=sys.stderr,
        )
        return 1
    print("ClamAV live integration check passed: infected test signature is detected and clean fixture remains CLEAN.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
