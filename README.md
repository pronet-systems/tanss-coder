# TANSS Document Encryption/Decryption Tool

A Python tool for encrypting and decrypting all documents in the TANSS MySQL database. This can be helpful when connecting TANSS to a RAG like [Onyx](https://github.com/onyx-dot-app/onyx).

## Features

- **Encrypt** all unencrypted documents (kodiert = 0)
- **Decrypt** all encrypted documents (kodiert = 1)
- **Test mode** to verify encoding/decoding functionality
- **Validation mode** to test encoding/decoding on all documents without updating the database
- **Automatic database backup** before processing (can be skipped)
- **Dry-run mode** to preview changes without modifying the database
- **Character encoding options** for handling special characters
- **Comprehensive logging** of all operations
- **Configuration file** for database connection settings

## Requirements

- Python 3.6 or higher
- MySQL server with TANSS database
- Required Python packages:
  - `pymysql`
- System utilities:
  - `mysqldump` (for database backups)

## Quick Start

```bash
# 1. Install dependencies
pip install pymysql

# 2. Create and configure config.ini
cp config.ini.example config.ini
# Edit config.ini with your database credentials

# 3. Test the connection and encoding
python3 tanss-coder.py test

# 4. Validate all documents can be encrypted
python3 tanss-coder.py encrypt --validate

# 5. Encrypt all unencrypted documents
python3 tanss-coder.py encrypt
```

## Installation

1. Clone or download this repository

2. Install required Python packages:
```bash
pip install -r requirements.txt
# Or manually:
pip install pymysql
```

3. Create a configuration file:
```bash
cp config.ini.example config.ini
```

4. Edit `config.ini` with your MySQL connection details:
```ini
[mysql]
host = localhost
port = 3306
database = tanss
user = your_username
password = your_password
```

5. Ensure the database user has appropriate permissions:
```sql
GRANT SELECT, UPDATE ON tanss.dokumente TO 'your_user'@'your_host';
FLUSH PRIVILEGES;
```

## Usage

### Basic Syntax

```bash
python3 tanss-coder.py [action] [options]
```

### Actions

- `encrypt` - Encrypt all unencrypted documents
- `decrypt` - Decrypt all encrypted documents
- `test` - Test encoding/decoding functionality

### Options

- `-c, --config CONFIG` - Path to configuration file (default: config.ini)
- `--skip-backup` - Skip database backup before processing
- `--dry-run` - Preview changes without modifying the database
- `--validate` - Validate encoding/decoding for each document without updating the database
- `--encoding-errors {strict,ignore,replace}` - How to handle characters that cannot be encoded in latin-1 (default: strict)
- `-h, --help` - Show help message

### Examples

#### Test encoding/decoding functionality
```bash
python3 tanss-coder.py test
```

#### Validate all unencrypted documents can be encoded
```bash
python3 tanss-coder.py encrypt --validate
```

#### Validate all encrypted documents can be decoded
```bash
python3 tanss-coder.py decrypt --validate
```

#### Encrypt all unencrypted documents
```bash
python3 tanss-coder.py encrypt
```

#### Decrypt all encrypted documents
```bash
python3 tanss-coder.py decrypt
```

#### Dry-run to preview changes
```bash
python3 tanss-coder.py encrypt --dry-run
```

#### Skip database backup
```bash
python3 tanss-coder.py encrypt --skip-backup
```

#### Use custom configuration file
```bash
python3 tanss-coder.py encrypt -c /path/to/config.ini
```

#### Handle documents with special characters (replaces unsupported characters with '?')
```bash
python3 tanss-coder.py encrypt --encoding-errors replace
```

## How It Works

### Encryption Process

When encrypting documents:
1. Tool connects to MySQL database
2. Creates a database backup (unless --skip-backup is used)
3. Retrieves all documents where `kodiert = 0` (unencrypted)
4. For each document:
   - Encrypts the `inhalt` field using RHD encoding
   - Updates the document with encrypted content
   - Sets `kodiert = 1`
5. Provides summary of successful/failed operations

### Decryption Process

When decrypting documents:
1. Tool connects to MySQL database
2. Creates a database backup (unless --skip-backup is used)
3. Retrieves all documents where `kodiert = 1` (encrypted)
4. For each document:
   - Decrypts the `inhalt` field using RHD decoding
   - Updates the document with decrypted content
   - Sets `kodiert = 0`
5. Provides summary of successful/failed operations

### Test Mode

Test mode performs three types of tests:
1. **Test 1**: Retrieves an unencrypted document, encodes it, then decodes it to verify the result matches the original
2. **Test 2**: Retrieves an encrypted document, decodes it, then re-encodes it to verify the result matches the original
3. **Test 3**: Tests encoding/decoding with various sample strings

This mode does not modify the database and skips the backup process.

### Validation Mode

Validation mode (`--validate`) tests encoding/decoding on ALL documents without making any changes to the database:

**For encryption validation:**
- Reads all unencrypted documents
- Encodes each document
- Immediately decodes it and verifies it matches the original
- Reports which documents can be successfully encrypted
- Does NOT update the database
- Skips backup process

**For decryption validation:**
- Reads all encrypted documents
- Decodes each document
- Immediately re-encodes it and verifies it matches the original encrypted version
- Reports which documents can be successfully decrypted
- Does NOT update the database
- Skips backup process

This is useful for identifying potential issues before performing actual encryption/decryption operations.

## RHD Encoding Algorithm

The tool uses the RHD encoding algorithm, which performs the following steps:

**Encoding:**
1. Base64 encode
2. Character substitution
3. Passphrase-based character shifting
4. Base64 encode again
5. Final character substitution

**Decoding:**
1. Character substitution (reverse)
2. Base64 decode
3. Passphrase-based character shifting (reverse)
4. Character substitution (reverse)
5. Base64 decode

### Character Encoding

The tool uses **latin-1** (ISO-8859-1) character encoding to match the original PHP implementation. This encoding supports characters 0-255, which includes:
- Standard ASCII characters (0-127)
- Western European characters (128-255): àáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ

**Unsupported characters** include:
- Full Unicode characters outside latin-1 range (e.g., emoji, CJK characters, some special punctuation)
- Examples: €, –, —, ', ", •, …

### Handling Unsupported Characters

Use the `--encoding-errors` flag to control how unsupported characters are handled:

| Mode | Behavior | Data Loss | Use Case |
|------|----------|-----------|----------|
| `strict` | Raises error if document contains unsupported characters | **No** | Default and recommended - prevents data corruption |
| `replace` | Replaces unsupported characters with `?` | **Yes** | When minor data loss is acceptable |
| `ignore` | Removes unsupported characters entirely | **Yes** | When characters can be safely removed |

**Example:**
```bash
# Recommended: Use strict mode to identify problematic documents
python3 tanss-coder.py encrypt --validate

# If needed: Allow replacement of unsupported characters
python3 tanss-coder.py encrypt --encoding-errors replace
```

**⚠️ Warning:** Using `replace` or `ignore` modes will modify document content. Use `--validate` first to see which documents will be affected.

## Database Schema

The tool operates on the `dokumente` table with the following relevant fields:

- `ID` (int) - Primary key
- `name` (varchar) - Document name
- `inhalt` (mediumtext) - Document content
- `kodiert` (tinyint) - Encryption flag (0 = unencrypted, 1 = encrypted)

## Logging

All operations are logged to:
- Console output (INFO level and above)
- Log files in `logs/` directory (DEBUG level and above)

Log files are named: `tanss_crypto_YYYYMMDD_HHMMSS.log`

## Backups

Database backups are created in the `backups/` directory by default.

Backup files are named: `tanss_backup_YYYYMMDD_HHMMSS.sql`

**Important:** Always verify backups before running encryption/decryption operations!

## Error Handling

The tool includes comprehensive error handling:
- Database connection failures
- Encoding/decoding errors
- Update failures
- Transaction rollback on errors

All errors are logged with details for troubleshooting.

## Security Considerations

1. **Configuration file**: The `config.ini` file contains database credentials. Ensure it has appropriate permissions:
   ```bash
   chmod 600 config.ini
   ```

2. **Backups**: Backup files may contain sensitive data. Store them securely.

3. **Logs**: Log files may contain document names and other metadata. Review log retention policies.

## File Structure

```
tanss-tools/
├── tanss-coder.py        # Main script
├── encoder.py            # RHD encoding/decoding class
├── config.ini            # Database configuration (create from example)
├── config.ini.example    # Configuration template
├── requirements.txt      # Python dependencies
├── README.md            # This file
├── .gitignore           # Git ignore rules
├── logs/                # Log files (created automatically)
└── backups/             # Database backups (created automatically)
```

## Troubleshooting

### "Configuration file not found"
Create `config.ini` from `config.ini.example` and fill in your database details.

### "Failed to connect to database"
- Verify MySQL server is running
- Check database credentials in config.ini
- Ensure database user has appropriate permissions
- Verify firewall settings if connecting to remote server

### "Backup failed"
- Ensure `mysqldump` is installed and in PATH
- Verify database user has necessary permissions
- Check available disk space
- Use `--skip-backup` if backups are not needed

### Encoding/decoding errors
- Run `python3 tanss-coder.py test` to verify the algorithm
- Use `python3 tanss-coder.py encrypt --validate` to identify problematic documents
- Check character encoding issues - the tool uses latin-1, not UTF-8
- Review log files for detailed error messages

### "latin-1 codec can't encode character" error
This error occurs when a document contains characters outside the latin-1 range (0-255).

**Solution 1 (Recommended):** Identify and fix problematic documents
```bash
# Find which documents have encoding issues
python3 tanss-coder.py encrypt --validate

# Check the log file for details
cat logs/tanss_crypto_*.log | grep "Error encrypting"
```

**Solution 2:** Use `--encoding-errors` flag to handle unsupported characters
```bash
# Replace unsupported characters with '?'
python3 tanss-coder.py encrypt --encoding-errors replace

# Or remove unsupported characters
python3 tanss-coder.py encrypt --encoding-errors ignore
```

**⚠️ Warning:** Solution 2 will modify document content. Always use `--validate` first and create a backup.

## License

This tool is provided as-is for use with TANSS database systems.

## Support

For issues or questions, please check the log files first for detailed error messages.
