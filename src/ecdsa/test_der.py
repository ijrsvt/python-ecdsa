# compatibility with Python 2.6, for that we need unittest2 package,
# which is not available on 3.3 or 3.4
import warnings
from binascii import hexlify

try:
    import unittest2 as unittest
except ImportError:
    import unittest
from six import b
import hypothesis.strategies as st
from hypothesis import given, example
import pytest
from ._compat import str_idx_as_int
from .curves import NIST256p, NIST224p
from .der import (
    remove_integer,
    UnexpectedDER,
    read_length,
    encode_bitstring,
    remove_bitstring,
    remove_object,
    encode_oid,
    remove_constructed,
    remove_octet_string,
    remove_sequence,
)


class TestRemoveInteger(unittest.TestCase):
    # DER requires the integers to be 0-padded only if they would be
    # interpreted as negative, check if those errors are detected
    def test_non_minimal_encoding(self):
        with self.assertRaises(UnexpectedDER):
            remove_integer(b("\x02\x02\x00\x01"))

    def test_negative_with_high_bit_set(self):
        with self.assertRaises(UnexpectedDER):
            remove_integer(b("\x02\x01\x80"))

    def test_minimal_with_high_bit_set(self):
        val, rem = remove_integer(b("\x02\x02\x00\x80"))

        self.assertEqual(val, 0x80)
        self.assertFalse(rem)

    def test_two_zero_bytes_with_high_bit_set(self):
        with self.assertRaises(UnexpectedDER):
            remove_integer(b("\x02\x03\x00\x00\xff"))

    def test_zero_length_integer(self):
        with self.assertRaises(UnexpectedDER):
            remove_integer(b("\x02\x00"))

    def test_empty_string(self):
        with self.assertRaises(UnexpectedDER):
            remove_integer(b(""))

    def test_encoding_of_zero(self):
        val, rem = remove_integer(b("\x02\x01\x00"))

        self.assertEqual(val, 0)
        self.assertFalse(rem)

    def test_encoding_of_127(self):
        val, rem = remove_integer(b("\x02\x01\x7f"))

        self.assertEqual(val, 127)
        self.assertFalse(rem)

    def test_encoding_of_128(self):
        val, rem = remove_integer(b("\x02\x02\x00\x80"))

        self.assertEqual(val, 128)
        self.assertFalse(rem)

    def test_wrong_tag(self):
        with self.assertRaises(UnexpectedDER) as e:
            remove_integer(b"\x01\x02\x00\x80")

        self.assertIn("wanted type 'integer'", str(e.exception))

    def test_wrong_length(self):
        with self.assertRaises(UnexpectedDER) as e:
            remove_integer(b"\x02\x03\x00\x80")

        self.assertIn("Length longer", str(e.exception))


class TestReadLength(unittest.TestCase):
    # DER requires the lengths between 0 and 127 to be encoded using the short
    # form and lengths above that encoded with minimal number of bytes
    # necessary
    def test_zero_length(self):
        self.assertEqual((0, 1), read_length(b("\x00")))

    def test_two_byte_zero_length(self):
        with self.assertRaises(UnexpectedDER):
            read_length(b("\x81\x00"))

    def test_two_byte_small_length(self):
        with self.assertRaises(UnexpectedDER):
            read_length(b("\x81\x7f"))

    def test_long_form_with_zero_length(self):
        with self.assertRaises(UnexpectedDER):
            read_length(b("\x80"))

    def test_smallest_two_byte_length(self):
        self.assertEqual((128, 2), read_length(b("\x81\x80")))

    def test_zero_padded_length(self):
        with self.assertRaises(UnexpectedDER):
            read_length(b("\x82\x00\x80"))

    def test_two_three_byte_length(self):
        self.assertEqual((256, 3), read_length(b"\x82\x01\x00"))

    def test_empty_string(self):
        with self.assertRaises(UnexpectedDER):
            read_length(b(""))

    def test_length_overflow(self):
        with self.assertRaises(UnexpectedDER):
            read_length(b("\x83\x01\x00"))


class TestEncodeBitstring(unittest.TestCase):
    # DER requires BIT STRINGS to include a number of padding bits in the
    # encoded byte string, that padding must be between 0 and 7

    def test_old_call_convention(self):
        """This is the old way to use the function."""
        warnings.simplefilter("always")
        with pytest.warns(DeprecationWarning) as warns:
            der = encode_bitstring(b"\x00\xff")

        self.assertEqual(len(warns), 1)
        self.assertIn(
            "unused= needs to be specified", warns[0].message.args[0]
        )

        self.assertEqual(der, b"\x03\x02\x00\xff")

    def test_new_call_convention(self):
        """This is how it should be called now."""
        warnings.simplefilter("always")
        with pytest.warns(None) as warns:
            der = encode_bitstring(b"\xff", 0)

        # verify that new call convention doesn't raise Warnings
        self.assertEqual(len(warns), 0)

        self.assertEqual(der, b"\x03\x02\x00\xff")

    def test_implicit_unused_bits(self):
        """
        Writing bit string with already included the number of unused bits.
        """
        warnings.simplefilter("always")
        with pytest.warns(None) as warns:
            der = encode_bitstring(b"\x00\xff", None)

        # verify that new call convention doesn't raise Warnings
        self.assertEqual(len(warns), 0)

        self.assertEqual(der, b"\x03\x02\x00\xff")

    def test_explicit_unused_bits(self):
        der = encode_bitstring(b"\xff\xf0", 4)

        self.assertEqual(der, b"\x03\x03\x04\xff\xf0")

    def test_empty_string(self):
        self.assertEqual(encode_bitstring(b"", 0), b"\x03\x01\x00")

    def test_invalid_unused_count(self):
        with self.assertRaises(ValueError):
            encode_bitstring(b"\xff\x00", 8)

    def test_invalid_unused_with_empty_string(self):
        with self.assertRaises(ValueError):
            encode_bitstring(b"", 1)

    def test_non_zero_padding_bits(self):
        with self.assertRaises(ValueError):
            encode_bitstring(b"\xff", 2)


class TestRemoveBitstring(unittest.TestCase):
    def test_old_call_convention(self):
        """This is the old way to call the function."""
        warnings.simplefilter("always")
        with pytest.warns(DeprecationWarning) as warns:
            bits, rest = remove_bitstring(b"\x03\x02\x00\xff")

        self.assertEqual(len(warns), 1)
        self.assertIn(
            "expect_unused= needs to be specified", warns[0].message.args[0]
        )

        self.assertEqual(bits, b"\x00\xff")
        self.assertEqual(rest, b"")

    def test_new_call_convention(self):
        warnings.simplefilter("always")
        with pytest.warns(None) as warns:
            bits, rest = remove_bitstring(b"\x03\x02\x00\xff", 0)

        self.assertEqual(len(warns), 0)

        self.assertEqual(bits, b"\xff")
        self.assertEqual(rest, b"")

    def test_implicit_unexpected_unused(self):
        warnings.simplefilter("always")
        with pytest.warns(None) as warns:
            bits, rest = remove_bitstring(b"\x03\x02\x00\xff", None)

        self.assertEqual(len(warns), 0)

        self.assertEqual(bits, (b"\xff", 0))
        self.assertEqual(rest, b"")

    def test_with_padding(self):
        ret, rest = remove_bitstring(b"\x03\x02\x04\xf0", None)

        self.assertEqual(ret, (b"\xf0", 4))
        self.assertEqual(rest, b"")

    def test_not_a_bitstring(self):
        with self.assertRaises(UnexpectedDER):
            remove_bitstring(b"\x02\x02\x00\xff", None)

    def test_empty_encoding(self):
        with self.assertRaises(UnexpectedDER):
            remove_bitstring(b"\x03\x00", None)

    def test_empty_string(self):
        with self.assertRaises(UnexpectedDER):
            remove_bitstring(b"", None)

    def test_no_length(self):
        with self.assertRaises(UnexpectedDER):
            remove_bitstring(b"\x03", None)

    def test_unexpected_number_of_unused_bits(self):
        with self.assertRaises(UnexpectedDER):
            remove_bitstring(b"\x03\x02\x00\xff", 1)

    def test_invalid_encoding_of_unused_bits(self):
        with self.assertRaises(UnexpectedDER):
            remove_bitstring(b"\x03\x03\x08\xff\x00", None)

    def test_invalid_encoding_of_empty_string(self):
        with self.assertRaises(UnexpectedDER):
            remove_bitstring(b"\x03\x01\x01", None)

    def test_invalid_padding_bits(self):
        with self.assertRaises(UnexpectedDER):
            remove_bitstring(b"\x03\x02\x01\xff", None)


class TestStrIdxAsInt(unittest.TestCase):
    def test_str(self):
        self.assertEqual(115, str_idx_as_int("str", 0))

    def test_bytes(self):
        self.assertEqual(115, str_idx_as_int(b"str", 0))

    def test_bytearray(self):
        self.assertEqual(115, str_idx_as_int(bytearray(b"str"), 0))


class TestEncodeOid(unittest.TestCase):
    def test_pub_key_oid(self):
        oid_ecPublicKey = encode_oid(1, 2, 840, 10045, 2, 1)
        self.assertEqual(hexlify(oid_ecPublicKey), b("06072a8648ce3d0201"))

    def test_nist224p_oid(self):
        self.assertEqual(hexlify(NIST224p.encoded_oid), b("06052b81040021"))

    def test_nist256p_oid(self):
        self.assertEqual(
            hexlify(NIST256p.encoded_oid), b"06082a8648ce3d030107"
        )

    def test_large_second_subid(self):
        # from X.690, section 8.19.5
        oid = encode_oid(2, 999, 3)
        self.assertEqual(oid, b"\x06\x03\x88\x37\x03")

    def test_with_two_subids(self):
        oid = encode_oid(2, 999)
        self.assertEqual(oid, b"\x06\x02\x88\x37")

    def test_zero_zero(self):
        oid = encode_oid(0, 0)
        self.assertEqual(oid, b"\x06\x01\x00")

    def test_with_wrong_types(self):
        with self.assertRaises((TypeError, AssertionError)):
            encode_oid(0, None)

    def test_with_small_first_large_second(self):
        with self.assertRaises(AssertionError):
            encode_oid(1, 40)

    def test_small_first_max_second(self):
        oid = encode_oid(1, 39)
        self.assertEqual(oid, b"\x06\x01\x4f")

    def test_with_invalid_first(self):
        with self.assertRaises(AssertionError):
            encode_oid(3, 39)


class TestRemoveObject(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oid_ecPublicKey = encode_oid(1, 2, 840, 10045, 2, 1)

    def test_pub_key_oid(self):
        oid, rest = remove_object(self.oid_ecPublicKey)
        self.assertEqual(rest, b"")
        self.assertEqual(oid, (1, 2, 840, 10045, 2, 1))

    def test_with_extra_bytes(self):
        oid, rest = remove_object(self.oid_ecPublicKey + b"more")
        self.assertEqual(rest, b"more")
        self.assertEqual(oid, (1, 2, 840, 10045, 2, 1))

    def test_with_large_second_subid(self):
        # from X.690, section 8.19.5
        oid, rest = remove_object(b"\x06\x03\x88\x37\x03")
        self.assertEqual(rest, b"")
        self.assertEqual(oid, (2, 999, 3))

    def test_with_padded_first_subid(self):
        with self.assertRaises(UnexpectedDER):
            remove_object(b"\x06\x02\x80\x00")

    def test_with_padded_second_subid(self):
        with self.assertRaises(UnexpectedDER):
            remove_object(b"\x06\x04\x88\x37\x80\x01")

    def test_with_missing_last_byte_of_multi_byte(self):
        with self.assertRaises(UnexpectedDER):
            remove_object(b"\x06\x03\x88\x37\x83")

    def test_with_two_subids(self):
        oid, rest = remove_object(b"\x06\x02\x88\x37")
        self.assertEqual(rest, b"")
        self.assertEqual(oid, (2, 999))

    def test_zero_zero(self):
        oid, rest = remove_object(b"\x06\x01\x00")
        self.assertEqual(rest, b"")
        self.assertEqual(oid, (0, 0))

    def test_empty_string(self):
        with self.assertRaises(UnexpectedDER):
            remove_object(b"")

    def test_missing_length(self):
        with self.assertRaises(UnexpectedDER):
            remove_object(b"\x06")

    def test_empty_oid(self):
        with self.assertRaises(UnexpectedDER):
            remove_object(b"\x06\x00")

    def test_empty_oid_overflow(self):
        with self.assertRaises(UnexpectedDER):
            remove_object(b"\x06\x01")

    def test_with_wrong_type(self):
        with self.assertRaises(UnexpectedDER):
            remove_object(b"\x04\x02\x88\x37")

    def test_with_too_long_length(self):
        with self.assertRaises(UnexpectedDER):
            remove_object(b"\x06\x03\x88\x37")


class TestRemoveConstructed(unittest.TestCase):
    def test_simple(self):
        data = b"\xa1\x02\xff\xaa"

        tag, body, rest = remove_constructed(data)

        self.assertEqual(tag, 0x01)
        self.assertEqual(body, b"\xff\xaa")
        self.assertEqual(rest, b"")

    def test_with_malformed_tag(self):
        data = b"\x01\x02\xff\xaa"

        with self.assertRaises(UnexpectedDER) as e:
            remove_constructed(data)

        self.assertIn("constructed tag", str(e.exception))


class TestRemoveOctetString(unittest.TestCase):
    def test_simple(self):
        data = b"\x04\x03\xaa\xbb\xcc"
        body, rest = remove_octet_string(data)
        self.assertEqual(body, b"\xaa\xbb\xcc")
        self.assertEqual(rest, b"")

    def test_with_malformed_tag(self):
        data = b"\x03\x03\xaa\xbb\xcc"
        with self.assertRaises(UnexpectedDER) as e:
            remove_octet_string(data)

        self.assertIn("octetstring", str(e.exception))


class TestRemoveSequence(unittest.TestCase):
    def test_simple(self):
        data = b"\x30\x02\xff\xaa"
        body, rest = remove_sequence(data)
        self.assertEqual(body, b"\xff\xaa")
        self.assertEqual(rest, b"")

    def test_with_empty_string(self):
        with self.assertRaises(UnexpectedDER) as e:
            remove_sequence(b"")

        self.assertIn("Empty string", str(e.exception))

    def test_with_wrong_tag(self):
        data = b"\x20\x02\xff\xaa"

        with self.assertRaises(UnexpectedDER) as e:
            remove_sequence(data)

        self.assertIn("wanted type 'sequence'", str(e.exception))

    def test_with_wrong_length(self):
        data = b"\x30\x03\xff\xaa"

        with self.assertRaises(UnexpectedDER) as e:
            remove_sequence(data)

        self.assertIn("Length longer", str(e.exception))


@st.composite
def st_oid(draw, max_value=2 ** 512, max_size=50):
    """
    Hypothesis strategy that returns valid OBJECT IDENTIFIERs as tuples

    :param max_value: maximum value of any single sub-identifier
    :param max_size: maximum length of the generated OID
    """
    first = draw(st.integers(min_value=0, max_value=2))
    if first < 2:
        second = draw(st.integers(min_value=0, max_value=39))
    else:
        second = draw(st.integers(min_value=0, max_value=max_value))
    rest = draw(
        st.lists(
            st.integers(min_value=0, max_value=max_value), max_size=max_size
        )
    )
    return (first, second) + tuple(rest)


@given(st_oid())
def test_oids(ids):
    encoded_oid = encode_oid(*ids)
    decoded_oid, rest = remove_object(encoded_oid)
    assert rest == b""
    assert decoded_oid == ids
