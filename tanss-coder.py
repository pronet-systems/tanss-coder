#!/usr/bin/env python3
"""
TANSS Document Encryption/Decryption Tool

This tool encrypts or decrypts documents in the TANSS MySQL database.
It can process all unencrypted documents (encrypt) or all encrypted documents (decrypt).
"""

import argparse
import configparser
import logging
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import pymysql
from pymysql.cursors import DictCursor

from tanss_crypto import TANSSCrypto


class Coder:
    """Main class for handling TANSS document encryption/decryption."""

    def __init__(self, config_file: str = "config.ini", encoding_errors: str = "strict"):
        """
        Initialize the TanssCrypto tool.

        Args:
            config_file: Path to the configuration file
            encoding_errors: How to handle encoding errors ('strict', 'ignore', 'replace')
        """
        self.config_file = config_file
        self.config = self._load_config()
        self.encoder = TANSSCrypto(encoding_errors=encoding_errors)
        self.connection = None
        self.logger = self._setup_logging()

    def _load_config(self) -> configparser.ConfigParser:
        """
        Load configuration from INI file.

        Returns:
            ConfigParser object with loaded configuration

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If required configuration is missing
        """
        config = configparser.ConfigParser()

        if not Path(self.config_file).exists():
            raise FileNotFoundError(
                f"Configuration file '{self.config_file}' not found. "
                f"Please create it with MySQL connection details."
            )

        config.read(self.config_file)

        # Validate required sections and keys
        required_keys = ['host', 'database', 'user', 'password']
        if 'mysql' not in config:
            raise ValueError("Configuration file must contain [mysql] section")

        for key in required_keys:
            if key not in config['mysql']:
                raise ValueError(f"Configuration file missing required key: {key}")

        return config

    def _setup_logging(self) -> logging.Logger:
        """
        Setup logging configuration.

        Returns:
            Configured logger instance
        """
        # Create logs directory if it doesn't exist
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)

        # Create logger
        logger = logging.getLogger('TanssCrypto')
        logger.setLevel(logging.DEBUG)

        # File handler with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        fh = logging.FileHandler(f'logs/tanss_crypto_{timestamp}.log')
        fh.setLevel(logging.DEBUG)

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)

        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)

        logger.addHandler(fh)
        logger.addHandler(ch)

        return logger

    def connect(self):
        """Establish connection to MySQL database."""
        try:
            self.connection = pymysql.connect(
                host=self.config['mysql']['host'],
                user=self.config['mysql']['user'],
                password=self.config['mysql']['password'],
                database=self.config['mysql']['database'],
                port=self.config['mysql'].getint('port', 3306),
                charset='utf8mb4',
                cursorclass=DictCursor
            )
            self.logger.info("Successfully connected to MySQL database")
        except pymysql.Error as e:
            self.logger.error(f"Failed to connect to database: {e}")
            raise

    def disconnect(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            self.logger.info("Database connection closed")

    def backup_database(self, backup_dir: str = "backups") -> Optional[str]:
        """
        Create a full backup of the database using mysqldump.

        Args:
            backup_dir: Directory to store backups

        Returns:
            Path to backup file if successful, None otherwise
        """
        backup_path = Path(backup_dir)
        backup_path.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = backup_path / f"tanss_backup_{timestamp}.sql"

        self.logger.info(f"Creating database backup: {backup_file}")

        try:
            cmd = [
                'mysqldump',
                '-h', self.config['mysql']['host'],
                '-u', self.config['mysql']['user'],
                f"-p{self.config['mysql']['password']}",
                '-P', str(self.config['mysql'].getint('port', 3306)),
                '--single-transaction',
                '--routines',
                '--triggers',
                self.config['mysql']['database']
            ]

            with open(backup_file, 'w') as f:
                result = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.PIPE,
                    text=True
                )

            if result.returncode == 0:
                self.logger.info(f"Backup created successfully: {backup_file}")
                return str(backup_file)
            else:
                self.logger.error(f"Backup failed: {result.stderr}")
                return None

        except Exception as e:
            self.logger.error(f"Error creating backup: {e}")
            return None

    def get_documents(self, encrypted: bool) -> list:
        """
        Retrieve documents from database based on encryption status.

        Args:
            encrypted: True to get encrypted documents, False for unencrypted

        Returns:
            List of document dictionaries
        """
        kodiert_value = 1 if encrypted else 0

        query = """
            SELECT ID, name, inhalt, kodiert
            FROM dokumente
            WHERE kodiert = %s AND inhalt IS NOT NULL AND inhalt != ''
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, (kodiert_value,))
                documents = cursor.fetchall()
                self.logger.info(
                    f"Found {len(documents)} {'encrypted' if encrypted else 'unencrypted'} documents"
                )
                return documents
        except pymysql.Error as e:
            self.logger.error(f"Error fetching documents: {e}")
            raise

    def update_document(self, doc_id: int, content: str, kodiert: int) -> bool:
        """
        Update document content and encryption status.

        Args:
            doc_id: Document ID
            content: New content
            kodiert: Encryption status (0 or 1)

        Returns:
            True if successful, False otherwise
        """
        query = """
            UPDATE dokumente
            SET inhalt = %s, kodiert = %s
            WHERE ID = %s
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, (content, kodiert, doc_id))
                self.connection.commit()
                return True
        except pymysql.Error as e:
            self.logger.error(f"Error updating document {doc_id}: {e}")
            self.connection.rollback()
            return False

    def encrypt_documents(self, dry_run: bool = False, validate: bool = False) -> dict:
        """
        Encrypt all unencrypted documents.

        Args:
            dry_run: If True, don't actually update the database
            validate: If True, validate encoding/decoding for each document

        Returns:
            Dictionary with statistics
        """
        self.logger.info("Starting document encryption process")

        documents = self.get_documents(encrypted=False)
        stats = {
            'total': len(documents),
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'validated': 0
        }

        for doc in documents:
            doc_id = doc['ID']
            doc_name = doc['name']
            content = doc['inhalt']

            try:
                # Encrypt the content
                encrypted_content = self.encoder.encode(content)

                # Validate if requested
                if validate:
                    decoded_content = self.encoder.decode(encrypted_content)
                    if decoded_content != content:
                        # Check if this is due to encoding error handling
                        if self.encoder.encoding_errors != 'strict':
                            self.logger.warning(
                                f"[VALIDATE FAILED] Document {doc_id} ({doc_name}): "
                                f"Content modified due to --encoding-errors={self.encoder.encoding_errors}. "
                                f"Some characters were {self.encoder.encoding_errors}d."
                            )
                        else:
                            self.logger.error(
                                f"[VALIDATE FAILED] Document {doc_id} ({doc_name}): "
                                f"Decoded content doesn't match original"
                            )
                        stats['failed'] += 1
                        continue
                    else:
                        self.logger.info(
                            f"[VALIDATE OK] Document {doc_id}: {doc_name} "
                            f"({len(content)} bytes -> {len(encrypted_content)} bytes)"
                        )
                        stats['validated'] += 1

                if dry_run or validate:
                    if not validate:
                        self.logger.info(
                            f"[DRY RUN] Would encrypt document {doc_id}: {doc_name}"
                        )
                    stats['skipped'] += 1
                else:
                    # Update database
                    if self.update_document(doc_id, encrypted_content, 1):
                        self.logger.info(f"Encrypted document {doc_id}: {doc_name}")
                        stats['success'] += 1
                    else:
                        self.logger.error(f"Failed to update document {doc_id}: {doc_name}")
                        stats['failed'] += 1

            except Exception as e:
                self.logger.error(f"Error encrypting document {doc_id} ({doc_name}): {e}")
                stats['failed'] += 1

        return stats

    def decrypt_documents(self, dry_run: bool = False, validate: bool = False) -> dict:
        """
        Decrypt all encrypted documents.

        Args:
            dry_run: If True, don't actually update the database
            validate: If True, validate decoding/encoding for each document

        Returns:
            Dictionary with statistics
        """
        self.logger.info("Starting document decryption process")

        documents = self.get_documents(encrypted=True)
        stats = {
            'total': len(documents),
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'validated': 0
        }

        for doc in documents:
            doc_id = doc['ID']
            doc_name = doc['name']
            content = doc['inhalt']

            try:
                # Decrypt the content
                decrypted_content = self.encoder.decode(content)

                # Validate if requested
                if validate:
                    re_encrypted_content = self.encoder.encode(decrypted_content)
                    if re_encrypted_content != content:
                        self.logger.error(
                            f"[VALIDATE FAILED] Document {doc_id} ({doc_name}): "
                            f"Re-encrypted content doesn't match original"
                        )
                        stats['failed'] += 1
                        continue
                    else:
                        self.logger.info(
                            f"[VALIDATE OK] Document {doc_id}: {doc_name} "
                            f"({len(content)} bytes -> {len(decrypted_content)} bytes)"
                        )
                        stats['validated'] += 1

                if dry_run or validate:
                    if not validate:
                        self.logger.info(
                            f"[DRY RUN] Would decrypt document {doc_id}: {doc_name}"
                        )
                    stats['skipped'] += 1
                else:
                    # Update database
                    if self.update_document(doc_id, decrypted_content, 0):
                        self.logger.info(f"Decrypted document {doc_id}: {doc_name}")
                        stats['success'] += 1
                    else:
                        self.logger.error(f"Failed to update document {doc_id}: {doc_name}")
                        stats['failed'] += 1

            except Exception as e:
                self.logger.error(f"Error decrypting document {doc_id} ({doc_name}): {e}")
                stats['failed'] += 1

        return stats

    def test_encoding(self) -> bool:
        """
        Test encoding/decoding functionality with actual database documents.

        Retrieves one encrypted and one unencrypted document and tests
        that encoding/decoding works correctly.

        Returns:
            True if all tests pass, False otherwise
        """
        self.logger.info("=" * 60)
        self.logger.info("TESTING ENCODING/DECODING")
        self.logger.info("=" * 60)

        all_tests_passed = True

        # Test 1: Get an unencrypted document and test encoding/decoding
        self.logger.info("\n[TEST 1] Testing with unencrypted document...")
        try:
            query = """
                SELECT ID, name, inhalt, kodiert
                FROM dokumente
                WHERE kodiert = 0 AND inhalt IS NOT NULL AND inhalt != ''
                LIMIT 1
            """
            with self.connection.cursor() as cursor:
                cursor.execute(query)
                doc = cursor.fetchone()

            if doc:
                original_content = doc['inhalt']
                doc_id = doc['ID']
                doc_name = doc['name']

                self.logger.info(f"Testing with document {doc_id}: {doc_name}")
                self.logger.info(f"Original content length: {len(original_content)} bytes")

                # Encode
                encoded = self.encoder.encode(original_content)
                self.logger.info(f"Encoded content length: {len(encoded)} bytes")

                # Decode
                decoded = self.encoder.decode(encoded)
                self.logger.info(f"Decoded content length: {len(decoded)} bytes")

                # Verify
                if decoded == original_content:
                    self.logger.info("✓ TEST 1 PASSED: Encoding/decoding cycle successful")
                else:
                    self.logger.error("✗ TEST 1 FAILED: Decoded content doesn't match original")
                    self.logger.error(f"Expected length: {len(original_content)}, Got: {len(decoded)}")
                    all_tests_passed = False
            else:
                self.logger.warning("No unencrypted documents found for testing")

        except Exception as e:
            self.logger.error(f"✗ TEST 1 FAILED with exception: {e}")
            all_tests_passed = False

        # Test 2: Get an encrypted document and test decoding/encoding
        self.logger.info("\n[TEST 2] Testing with encrypted document...")
        try:
            query = """
                SELECT ID, name, inhalt, kodiert
                FROM dokumente
                WHERE kodiert = 1 AND inhalt IS NOT NULL AND inhalt != ''
                LIMIT 1
            """
            with self.connection.cursor() as cursor:
                cursor.execute(query)
                doc = cursor.fetchone()

            if doc:
                encrypted_content = doc['inhalt']
                doc_id = doc['ID']
                doc_name = doc['name']

                self.logger.info(f"Testing with document {doc_id}: {doc_name}")
                self.logger.info(f"Encrypted content length: {len(encrypted_content)} bytes")

                # Decode
                decrypted = self.encoder.decode(encrypted_content)
                self.logger.info(f"Decrypted content length: {len(decrypted)} bytes")

                # Re-encode
                re_encrypted = self.encoder.encode(decrypted)
                self.logger.info(f"Re-encrypted content length: {len(re_encrypted)} bytes")

                # Verify
                if re_encrypted == encrypted_content:
                    self.logger.info("✓ TEST 2 PASSED: Decoding/encoding cycle successful")
                else:
                    self.logger.error("✗ TEST 2 FAILED: Re-encrypted content doesn't match original")
                    self.logger.error(f"Expected length: {len(encrypted_content)}, Got: {len(re_encrypted)}")
                    all_tests_passed = False
            else:
                self.logger.warning("No encrypted documents found for testing")

        except Exception as e:
            self.logger.error(f"✗ TEST 2 FAILED with exception: {e}")
            all_tests_passed = False

        # Test 3: Test with sample text
        self.logger.info("\n[TEST 3] Testing with sample text...")
        try:
            test_strings = [
                "Hello, World!",
                "This is a test document with special characters: äöü ß",
                "1234567890",
                "Multi\nLine\nText\nWith\nNewlines",
                "",  # Empty string
                "Latin-1 special chars: ¡¢£¤¥¦§¨©ª«¬®¯°±²³´µ¶·¸¹º»¼½¾¿"
            ]

            test3_passed = True
            for i, test_str in enumerate(test_strings):
                encoded = self.encoder.encode(test_str)
                decoded = self.encoder.decode(encoded)

                if decoded == test_str:
                    self.logger.info(f"  ✓ Test string {i+1} passed")
                else:
                    self.logger.error(f"  ✗ Test string {i+1} failed")
                    self.logger.error(f"    Expected: {repr(test_str)}")
                    self.logger.error(f"    Got: {repr(decoded)}")
                    test3_passed = False

            if test3_passed:
                self.logger.info("✓ TEST 3 PASSED: All sample strings encoded/decoded correctly")
            else:
                self.logger.error("✗ TEST 3 FAILED: Some sample strings failed")
                all_tests_passed = False

        except Exception as e:
            self.logger.error(f"✗ TEST 3 FAILED with exception: {e}")
            all_tests_passed = False

        # Final result
        self.logger.info("\n" + "=" * 60)
        if all_tests_passed:
            self.logger.info("ALL TESTS PASSED ✓")
        else:
            self.logger.error("SOME TESTS FAILED ✗")
        self.logger.info("=" * 60)

        return all_tests_passed


def main():
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(
        description='Encrypt or decrypt documents in TANSS database'
    )

    parser.add_argument(
        'action',
        choices=['encrypt', 'decrypt', 'test'],
        help='Action to perform: encrypt unencrypted documents, decrypt encrypted documents, or test encoding/decoding'
    )

    parser.add_argument(
        '-c', '--config',
        default='config.ini',
        help='Path to configuration file (default: config.ini)'
    )

    parser.add_argument(
        '--skip-backup',
        action='store_true',
        help='Skip database backup before processing'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform a dry run without actually updating the database'
    )

    parser.add_argument(
        '--validate',
        action='store_true',
        help='Validate encoding/decoding for each document without updating the database'
    )

    parser.add_argument(
        '--encoding-errors',
        choices=['strict', 'ignore', 'replace'],
        default='strict',
        help='How to handle characters that cannot be encoded in latin-1 (default: strict)'
    )

    args = parser.parse_args()

    try:
        # Initialize the tool
        crypto = Coder(config_file=args.config, encoding_errors=args.encoding_errors)

        # Warn if using non-strict encoding
        if args.encoding_errors != 'strict':
            crypto.logger.warning(
                f"Using encoding-errors={args.encoding_errors}. "
                f"Characters that cannot be encoded in latin-1 will be {args.encoding_errors}d."
            )

        # Create backup unless skipped or testing
        if args.action != 'test' and not args.skip_backup:
            crypto.logger.info("Creating database backup...")
            backup_file = crypto.backup_database()
            if not backup_file:
                crypto.logger.warning("Backup failed, but continuing anyway...")
        elif args.action == 'test':
            crypto.logger.info("Test mode: Skipping database backup")
        else:
            crypto.logger.info("Skipping database backup (--skip-backup flag set)")

        # Connect to database
        crypto.connect()

        # Perform the requested action
        if args.action == 'test':
            # Test mode - no stats summary needed
            test_passed = crypto.test_encoding()
            crypto.disconnect()

            if test_passed:
                sys.exit(0)
            else:
                sys.exit(1)
        elif args.action == 'encrypt':
            stats = crypto.encrypt_documents(dry_run=args.dry_run, validate=args.validate)
            action_word = "encrypted"
        else:
            stats = crypto.decrypt_documents(dry_run=args.dry_run, validate=args.validate)
            action_word = "decrypted"

        # Disconnect
        crypto.disconnect()

        # Print summary
        crypto.logger.info("=" * 60)
        crypto.logger.info("SUMMARY")
        crypto.logger.info("=" * 60)
        crypto.logger.info(f"Total documents found: {stats['total']}")
        if args.validate:
            crypto.logger.info(f"Successfully validated: {stats['validated']}")
        else:
            crypto.logger.info(f"Successfully {action_word}: {stats['success']}")
        crypto.logger.info(f"Failed: {stats['failed']}")
        if not args.validate:
            crypto.logger.info(f"Skipped (dry run): {stats['skipped']}")
        crypto.logger.info("=" * 60)

        # Exit with appropriate code
        if stats['failed'] > 0:
            sys.exit(1)
        else:
            sys.exit(0)

    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
