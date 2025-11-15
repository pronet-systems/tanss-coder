"""
TANSS Encoding/Decoding Module
"""

import base64


class TANSSCrypto:
    """
    Handles encoding and decoding of document content
    """

    def __init__(self, encoding_errors='strict'):
        """
        Initialize the encoder with the passphrase and character mapping.

        Args:
            encoding_errors: How to handle encoding errors ('strict', 'ignore', 'replace', 'xmlcharrefreplace')
                           - 'strict': Raise UnicodeEncodeError (default, matches PHP behavior)
                           - 'ignore': Skip characters that can't be encoded
                           - 'replace': Replace with '?'
                           - 'xmlcharrefreplace': Replace with XML character references
        """
        self.passphrase = "3c2e002ab7b41f49ddc877a727787f03"
        self.encoding_errors = encoding_errors

        # Character substitution mapping
        self.enc_map = {
            "=": "V", "z": "m", "5": "G", "H": "a", "1": "x",
            "N": "C", "q": "p", "r": "8", "/": "+", "J": "i",
            "2": "w", "9": "T", "s": "h", "l": "Z", "V": "=",
            "m": "z", "G": "5", "a": "H", "x": "1", "C": "N",
            "p": "q", "8": "r", "+": "/", "i": "J", "w": "2",
            "T": "9", "h": "s", "Z": "l"
        }

    def _switch_encode(self, data: str) -> str:
        """
        Perform character substitution based on the mapping.

        Args:
            data: Input string to transform

        Returns:
            Transformed string
        """
        result = []
        for char in data:
            result.append(self.enc_map.get(char, char))
        return ''.join(result)

    def _pass_encode(self, data: str, encode_type: int) -> str:
        """
        Encode/decode string using passphrase-based character shifting.

        Args:
            data: Input string to transform
            encode_type: 0 for encoding, 1 for decoding

        Returns:
            Transformed string
        """
        result = []
        pp_len = len(self.passphrase)
        pp_i = 0

        for char in data:
            if encode_type == 0:
                # Encoding: add passphrase character value
                new_char = chr(ord(char) + ord(self.passphrase[pp_i]))
            else:
                # Decoding: subtract passphrase character value
                new_char = chr(ord(char) - ord(self.passphrase[pp_i]))

            result.append(new_char)
            pp_i += 1
            if pp_i == pp_len:
                pp_i = 0

        return ''.join(result)

    def _base_encode(self, data: str, encode_type: int) -> str:
        """
        Perform base64 encoding or decoding.

        Args:
            data: Input string to transform
            encode_type: 0 for encoding, 1 for decoding

        Returns:
            Transformed string
        """
        if encode_type == 0:
            # Encoding - use latin-1 to match PHP implementation
            return base64.b64encode(data.encode('latin-1', errors=self.encoding_errors)).decode('ascii')
        else:
            # Decoding - use latin-1 to match PHP implementation
            return base64.b64decode(data.encode('ascii')).decode('latin-1')

    def encode(self, data: str) -> str:
        """
        Encode a string using the RHD algorithm.

        Args:
            data: Plain text string to encode

        Returns:
            Encoded string
        """
        # Step 1: Base64 encode
        result = self._base_encode(data, 0)

        # Step 2: Character substitution
        result = self._switch_encode(result)

        # Step 3: Passphrase encoding
        result = self._pass_encode(result, 0)

        # Step 4: Base64 encode again
        result = self._base_encode(result, 0)

        # Step 5: Final character substitution
        result = self._switch_encode(result)

        return result

    def decode(self, data: str) -> str:
        """
        Decode a string using the RHD algorithm.

        Args:
            data: Encoded string to decode

        Returns:
            Decoded plain text string
        """
        # Step 1: Character substitution (reverse)
        result = self._switch_encode(data)

        # Step 2: Base64 decode
        result = self._base_encode(result, 1)

        # Step 3: Passphrase decoding
        result = self._pass_encode(result, 1)

        # Step 4: Character substitution (reverse)
        result = self._switch_encode(result)

        # Step 5: Base64 decode
        result = self._base_encode(result, 1)

        return result
