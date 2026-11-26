import pytest

from qkd.privacy_amplification import amplify_agreed_bits


def test_amplification_matches_explicit_toeplitz_matrix():
    bits = (1, 1, 0)
    # Toeplitz rows are (1, 0, 1) and (1, 1, 0).
    assert amplify_agreed_bits(bits, bits, 2, (1, 0, 1, 1)) == (1, 0)


def test_amplification_rejects_disagreement():
    with pytest.raises(ValueError, match="must agree"):
        amplify_agreed_bits((0, 1), (1, 1), 1, (0, 1))


@pytest.mark.parametrize("seed", [(1,), (1, 2)])
def test_amplification_rejects_invalid_seed(seed):
    with pytest.raises(ValueError, match="public_seed"):
        amplify_agreed_bits((1, 0), (1, 0), 1, seed)


def test_amplification_can_return_zero_bits():
    assert amplify_agreed_bits((1,), (1,), 0, ()) == ()
