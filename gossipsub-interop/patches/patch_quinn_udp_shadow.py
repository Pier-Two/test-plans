#!/usr/bin/env python3
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch_quinn_udp_shadow.py <quinn-udp-module-dir>", file=sys.stderr)
        return 2

    module_dir = Path(sys.argv[1])
    target = module_dir / "src" / "unix.rs"
    text = target.read_text()
    marker = 'std::env::var_os("QUINN_UDP_SHADOW_RECVMSG")'
    if marker in text:
        return 0

    needle = """    let max_msg_count = bufs.len().min(BATCH_SIZE);
    for i in 0..max_msg_count {
        prepare_recv(
            &mut bufs[i],
            &mut names[i],
            &mut ctrls[i],
            &mut hdrs[i].msg_hdr,
        );
    }
    let msg_count = loop {
"""
    replacement = """    let max_msg_count = bufs.len().min(BATCH_SIZE);
    if max_msg_count == 0 {
        return Ok(0);
    }
    if std::env::var_os("QUINN_UDP_SHADOW_RECVMSG").is_some() {
        let mut hdr = unsafe { mem::zeroed::<libc::msghdr>() };
        prepare_recv(&mut bufs[0], &mut names[0], &mut ctrls[0], &mut hdr);
        let n = loop {
            let n = unsafe { libc::recvmsg(io.as_raw_fd(), &mut hdr, 0) };

            if hdr.msg_flags & libc::MSG_TRUNC != 0 {
                continue;
            }

            if n >= 0 {
                break n;
            }

            let e = io::Error::last_os_error();
            match e.kind() {
                io::ErrorKind::Interrupted => continue,
                _ => return Err(e),
            }
        };
        meta[0] = decode_recv(&names[0], &hdr, n as usize);
        return Ok(1);
    }
    for i in 0..max_msg_count {
        prepare_recv(
            &mut bufs[i],
            &mut names[i],
            &mut ctrls[i],
            &mut hdrs[i].msg_hdr,
        );
    }
    let msg_count = loop {
"""
    if needle not in text:
        print(f"quinn-udp patch anchor not found in {target}", file=sys.stderr)
        return 1

    target.chmod(0o644)
    target.write_text(text.replace(needle, replacement))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
