"""Authenticated transfer of synthetic healthcare payloads."""

from dataclasses import dataclass
from secrets import token_bytes

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass(frozen=True)
class EncryptedRecord:
    key_id: str
    nonce: bytes
    ciphertext: bytes


def key_from_bits(bits: tuple[int, ...]) -> bytes:
    if len(bits) != 256 or any(type(bit) is not int or bit not in (0, 1) for bit in bits):
        raise ValueError("AES-256 requires 256 integer bits")
    return int("".join(map(str, bits)), 2).to_bytes(32, "big")


def encrypt_record(payload: bytes, key: bytes, key_id: str) -> EncryptedRecord:
    if len(key) != 32:
        raise ValueError("AES-256 requires a 32-byte key")
    nonce = token_bytes(12)
    ciphertext = AESGCM(key).encrypt(nonce, payload, key_id.encode("utf-8"))
    return EncryptedRecord(key_id, nonce, ciphertext)


def decrypt_record(record: EncryptedRecord, key: bytes) -> bytes:
    if len(key) != 32:
        raise ValueError("AES-256 requires a 32-byte key")
    return AESGCM(key).decrypt(record.nonce, record.ciphertext, record.key_id.encode("utf-8"))
