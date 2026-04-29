package main

import (
	"crypto/sha256"
	"fmt"
	"testing"

	"github.com/libp2p/go-libp2p/core/peer"
)

// TestPeerIDGeneration tests that peer ID generation is consistent across implementations.
func TestPeerIDGeneration(t *testing.T) {
	var peerIDs []string
	for nodeID := range 10_000 {
		privKey := nodePrivKey(nodeID)
		id, err := peer.IDFromPrivateKey(privKey)
		if err != nil {
			t.Fatal(err)
		}
		peerIDs = append(peerIDs, fmt.Sprintf(">%d:%s\n", nodeID, id.String()))
	}

	hash := sha256.New()
	for _, peerID := range peerIDs {
		hash.Write([]byte(peerID))
	}
	hashStr := fmt.Sprintf("%x", hash.Sum(nil))
	expectedHash := "9da32ad6bf8dd4b3ad55bffea81a5288b97b3cba4da93a93f718a681f2f8aa4b"
	if hashStr != expectedHash {
		t.Errorf("Did not generate peer ids correctly. Saw %s expected %s", hashStr, expectedHash)
	}
	fmt.Printf("SHA256 hash of all peer ids: %s\n", hashStr)
}
