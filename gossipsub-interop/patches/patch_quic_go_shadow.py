#!/usr/bin/env python3
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch_quic_go_shadow.py <quic-go-module-dir>", file=sys.stderr)
        return 2

    module_dir = Path(sys.argv[1])
    target = module_dir / "sys_conn.go"
    text = target.read_text()
    marker = 'os.Getenv("QUIC_GO_SHADOW_BASIC_CONN")'
    if marker in text:
        return 0

    needle = """\tc, ok := pc.(OOBCapablePacketConn)
\tif !ok {
\t\tutils.DefaultLogger.Infof("PacketConn is not a net.UDPConn. Disabling optimizations possible on UDP connections.")
\t\treturn &basicConn{PacketConn: pc, supportsDF: supportsDF}, nil
\t}
\treturn newConn(c, supportsDF)
"""
    replacement = """\tc, ok := pc.(OOBCapablePacketConn)
\tif !ok {
\t\tutils.DefaultLogger.Infof("PacketConn is not a net.UDPConn. Disabling optimizations possible on UDP connections.")
\t\treturn &basicConn{PacketConn: pc, supportsDF: supportsDF}, nil
\t}
\tif disable, _ := strconv.ParseBool(os.Getenv("QUIC_GO_SHADOW_BASIC_CONN")); disable {
\t\tutils.DefaultLogger.Infof("QUIC_GO_SHADOW_BASIC_CONN set. Disabling UDP OOB batching for Shadow.")
\t\treturn &basicConn{PacketConn: pc, supportsDF: supportsDF}, nil
\t}
\treturn newConn(c, supportsDF)
"""
    if needle not in text:
        print(f"quic-go patch anchor not found in {target}", file=sys.stderr)
        return 1

    target.chmod(0o644)
    target.write_text(text.replace(needle, replacement))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
