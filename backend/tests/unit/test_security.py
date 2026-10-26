from app.security import (
    DUMMY_PASSWORD_HASH,
    hash_password,
    hash_session_token,
    new_csrf_token,
    new_session_token,
    password_needs_rehash,
    tokens_equal,
    verify_password,
)


def test_password_roundtrip():
    password_hash = hash_password("correct horse")

    assert password_hash.startswith("$argon2id$")
    assert verify_password(password_hash, "correct horse")
    assert not verify_password(password_hash, "wrong horse")
    assert not password_needs_rehash(password_hash)


def test_same_password_gives_different_hashes():
    assert hash_password("secret") != hash_password("secret")


def test_verify_garbage_hash_is_false_not_error():
    assert not verify_password("not-a-hash", "secret")


def test_dummy_hash_matches_nothing():
    assert not verify_password(DUMMY_PASSWORD_HASH, "")
    assert not verify_password(DUMMY_PASSWORD_HASH, "password")


def test_session_token_hash_fits_column():
    token = new_session_token()
    token_hash = hash_session_token(token)

    assert len(token_hash) == 64
    assert token_hash == hash_session_token(token)
    assert token_hash != hash_session_token(new_session_token())


def test_csrf_token_fits_column():
    assert len(new_csrf_token()) <= 64


def test_tokens_equal():
    assert tokens_equal("abc", "abc")
    assert not tokens_equal("abc", "abd")
    assert not tokens_equal("abc", "abcd")
