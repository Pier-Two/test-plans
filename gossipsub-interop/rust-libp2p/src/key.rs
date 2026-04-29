use crate::script_instruction::NodeID;
use byteorder::{BigEndian, ByteOrder};
use libp2p::identity;

/// Generate a private key for a node ID
pub fn node_priv_key(id: NodeID) -> identity::Keypair {
    // Create a deterministic seed based on the node ID
    let mut seed = [0u8; 32];
    BigEndian::write_u64(&mut seed[24..32], (id as u64) + 1);

    // Create a keypair from the seed
    let secret =
        identity::secp256k1::SecretKey::try_from_bytes(seed).expect("Failed to create keypair");
    identity::Keypair::from(identity::secp256k1::Keypair::from(secret))
}

#[test]
fn test_node_priv_key() {
    let mut peer_ids = Vec::new();
    for node_id in 0..10_000 {
        let key = node_priv_key(node_id);
        let local_peer_id = libp2p::PeerId::from(key.public());
        peer_ids.push(format!(">{}:{}\n", node_id, local_peer_id));
    }
    use sha2::{Digest, Sha256};
    let mut hasher = Sha256::new();
    for key in &peer_ids {
        hasher.update(key.as_bytes());
    }
    let hash = hasher.finalize();

    let hash_str = format!("{:02x}", hash);
    let expected_hash = "9da32ad6bf8dd4b3ad55bffea81a5288b97b3cba4da93a93f718a681f2f8aa4b";
    assert_eq!(
        hash_str, expected_hash,
        "Implementation did not generate peer ids correctly"
    );

    println!("SHA256 hash of all peer ids: {:02x}", hash);
}
