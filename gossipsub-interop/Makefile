# Default target
all: binaries

C_LEAN_LIBP2P_ROOT ?= ../../..
C_LEAN_LIBP2P_BUILD ?= $(C_LEAN_LIBP2P_ROOT)/build-gossipsub-interop
C_LEAN_LIBP2P_GOSSIPSUB_BIN ?= $(C_LEAN_LIBP2P_BUILD)/bin/c_lean_libp2p_gossipsub_interop

binaries: patch-go-shadow patch-rust-shadow
	cd go-libp2p && go build -buildvcs=false -linkshared -o gossipsub-bin
	cd rust-libp2p && cargo build

patch-go-shadow:
	cd go-libp2p && go mod download github.com/quic-go/quic-go
	python3 patches/patch_quic_go_shadow.py "$$(cd go-libp2p && go env GOMODCACHE)/github.com/quic-go/quic-go@v0.50.1"

patch-rust-shadow:
	cd rust-libp2p && cargo fetch
	python3 patches/patch_quinn_udp_shadow.py "$$(find "$${CARGO_HOME:-$$HOME/.cargo}"/registry/src -path '*/quinn-udp-0.5.14' -type d | head -n 1)"

c-lean-libp2p:
	cmake -S "$(C_LEAN_LIBP2P_ROOT)" -B "$(C_LEAN_LIBP2P_BUILD)" \
		-DCMAKE_BUILD_TYPE=Release \
		-DDISABLE_CPU_JITTER_ENTROPY=ON \
		-DOPENSSL_NO_ASM=ON \
		-DSECP256K1_ASM=OFF \
		-DBUILD_TESTING=OFF \
		-DLIBP2P_BUILD_GOSSIPSUB_INTEROP_BINARY=ON
	cmake --build "$(C_LEAN_LIBP2P_BUILD)" --target c_lean_libp2p_gossipsub_interop --parallel
	test -x "$(C_LEAN_LIBP2P_GOSSIPSUB_BIN)"

# Clean all generated shadow simulation files
clean:
	rm -rf shadow-outputs || true
	rm plots/* || true

test:
	# Testing partial messages
	@echo "Testing partial messages"
	@uv run run.py --node_count 32 --composition "rust-and-go" --scenario "partial-messages" && uv run checks/partial_messages.py latest --count 1

	@echo "Testing partial messages chain"
	@uv run run.py --node_count 8 --composition "rust-and-go" --scenario "partial-messages-chain" && uv run checks/partial_messages.py latest --count 16

	@echo "Testing fanout"
	uv run run.py --node_count 8 --composition "rust-and-go" --scenario "partial-messages-fanout" && uv run checks/partial_messages.py latest/
	uv run run.py --node_count 8 --seed 1 --composition "rust-and-go" --scenario "partial-messages-fanout" && uv run checks/partial_messages.py latest/
	uv run run.py --node_count 8 --seed 2 --composition "rust-and-go" --scenario "partial-messages-fanout" && uv run checks/partial_messages.py latest/
	uv run run.py --node_count 8 --seed 3 --composition "rust-and-go" --scenario "partial-messages-fanout" && uv run checks/partial_messages.py latest/

test-go:
	# Testing partial messages
	@echo "Testing partial messages"
	@uv run run.py --node_count 8 --composition "all-go" --scenario "partial-messages" && uv run checks/partial_messages.py latest --count 1

	@echo "Testing partial messages chain"
	@uv run run.py --node_count 8 --composition "all-go" --scenario "partial-messages-chain" && uv run checks/partial_messages.py latest --count 16

	@echo "Testing fanout"
	@uv run run.py --node_count 2 --composition "all-go" --scenario "partial-messages-fanout" && uv run checks/partial_messages.py latest/


test-rust-only:
	# Testing partial messages
	@echo "Testing partial messages"
	@uv run run.py --node_count 8 --composition "all-rust" --scenario "partial-messages" && uv run checks/partial_messages.py latest --count 1

	@echo "Testing partial messages chain"
	@uv run run.py --node_count 8 --composition "all-rust" --scenario "partial-messages-chain" && uv run checks/partial_messages.py latest --count 16

	@echo "Testing fanout"
	@uv run run.py --node_count 2 --composition "all-rust" --scenario "partial-messages-fanout" && uv run checks/partial_messages.py latest/



.PHONY: binaries all clean test patch-go-shadow patch-rust-shadow
