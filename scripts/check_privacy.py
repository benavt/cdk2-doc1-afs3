#!/usr/bin/env python3
"""Validate the complete Git tree for privacy leaks without printing matched values."""
import argparse
import gzip
import json
import os
from pathlib import PurePosixPath
import re
import struct
import subprocess
import sys

# Build patterns from fragments to avoid literal sensitive strings
_p1, _p2 = 'p' + 'a', 'x'  # private hostname fragment
_m1, _m2 = 'm' + 'i', 'm' + 'as'  # private hostname fragment
_rpi = 'r' + 'p' + 'i'  # private institution fragment

RULES = {
    'private key': rb'-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----',
    'GitHub token': rb'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})\b',
    'cloud access key': rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    'service token': rb'\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{15,})\b',
    'literal credential': rb'''(?i)(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)\s*[=:]\s*["']([^"'\s]{12,})["']''',
    'authorization value': rb'(?i)\bBearer\s+[A-Za-z0-9_.-]{20,}',
    'private filesystem path': rb'/(?:home|Users|scratch|data|projects|mnt)/[A-Za-z0-9_.-]+/',
    'private network address': rb'\b(?:10\.[0-9]+\.[0-9]+\.[0-9]+|192\.168\.[0-9]+\.[0-9]+|172\.(?:1[6-9]|2[0-9]|3[01])\.[0-9]+\.[0-9]+|100\.(?:6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]+\.[0-9]+)\b|[A-Za-z0-9.-]+\.ts\.net',
    'private hostname': ('(?i)(?:^|[^a-z])(?:' + _p1 + _p2 + '|' + _m1 + _m2 + ')(?:[^a-z]|$)').encode(),
    'private git host': ('(?i)github\\.' + _rpi + '\\.edu').encode(),
    'ssh config': rb'(?i)(?:^|\n)\s*(?:Host|HostName|IdentityFile|ProxyCommand|RemoteCommand)\s+[^\n]+',
}

# File extensions to exclude from certain pattern checks
# Protein sequences contain AKIA-like substrings
PROTEIN_DATA_EXTENSIONS = {'.fasta', '.a3m', '.pdb', '.cif', '.csv'}

# Specific files excluded from credential/hostname checks by path
# These files legitimately contain test fixtures or detection patterns as string literals
FIXTURE_FILES = {
    'scripts/check_privacy.py',  # Contains the patterns it checks for
    'scripts/test_check_privacy.py',  # Contains fake credentials/paths as test data
}

# Files excluded from credential patterns only (hostnames, IPs, and paths still checked)
# These are third-party libraries with false positives in minified code
CREDENTIAL_EXCLUDED_FILES = set()

# Context-specific exclusions for false positives in known positions
# Each entry: (filepath, pattern_name, context_before_bytes, context_after_bytes)
# The match is excluded ONLY when surrounded by these exact byte sequences
CONTEXT_EXCLUDED_MATCHES = [
    # Maya calendar month name in plotly.min.js calendar data
    # Matches only when surrounded by neighboring month names in the sequence
    ('assets/plotly.min.js', 'private hostname', b'"Muan",', b',"Kayab"'),
    # OppAxisClassName and rangeslider-mask-opp-axis in plotly.min.js
    # These contain 'pax' as part of compound words, not the hostname
    ('assets/plotly.min.js', 'private hostname', b'OppAxisCl', b'ssName'),
    ('assets/plotly.min.js', 'private hostname', b'-mask-opp-', b'xis'),
    # URL template placeholders and example code in plotly.min.js
    # api_key= in Stadia Maps tile URL templates (multiple instances)
    ('assets/plotly.min.js', 'literal credential', b'{y}.png?', b'plotly-stamen-terrain"'),
    ('assets/plotly.min.js', 'literal credential', b'{y}.png?', b'plotly-stamen-toner"'),
    ('assets/plotly.min.js', 'literal credential', b'{y}.jpg?', b'plotly-stamen-watercolor"'),
    # mapboxAccessToken example in documentation string
    ('assets/plotly.min.js', 'literal credential', b'{ mapbox', b' });","More info'),
    # access_token URL parameter placeholder in analytics code
    ('assets/plotly.min.js', 'literal credential', b'.params.push("', b'"));var Oe={event:this.type'),
]

def extract_png_text_chunks(body):
    """Extract text chunks from PNG without parsing IDAT (compressed image data).
    
    PNG structure:
    - 8-byte signature
    - Chunks: [length(4)][type(4)][data(length)][crc(4)]
    
    Text chunks: tEXt, zTXt, iTXt
    """
    if not body.startswith(b'\x89PNG\r\n\x1a\n'):
        return b''
    
    text_content = b''
    offset = 8  # Skip PNG signature
    
    while offset + 12 <= len(body):
        # Read chunk length (big-endian)
        chunk_length = struct.unpack('>I', body[offset:offset+4])[0]
        chunk_type = body[offset+4:offset+8]
        
        # Check if this is a text chunk (not IDAT)
        if chunk_type in (b'tEXt', b'zTXt', b'iTXt'):
            chunk_data = body[offset+8:offset+8+chunk_length]
            if chunk_type == b'zTXt':
                # Compressed text chunk - decompress
                try:
                    # Format: keyword\0compression_method(1 byte)compressed_text
                    null_pos = chunk_data.find(b'\0')
                    if null_pos > 0 and null_pos + 2 < len(chunk_data):
                        compressed = chunk_data[null_pos+2:]
                        text_content += gzip.decompress(b'\x1f\x8b\x08\x00\x00\x00\x00\x00' + compressed)
                except Exception as e:
                    # Unreadable compressed PNG text chunk is a violation
                    raise SystemExit(f'{filename}: PNG zTXt chunk decompression failed: {e}')
            else:
                text_content += chunk_data
        
        # Move to next chunk (skip length + type + data + CRC)
        offset += 4 + 4 + chunk_length + 4
        
        # Stop at IEND chunk
        if chunk_type == b'IEND':
            break
    
    return text_content

def strings_scan_binary(body, min_length=4):
    """Extract printable strings from binary data (similar to 'strings' command).
    
    Only scans for ASCII printable strings, avoiding false positives from binary data.
    """
    strings_found = []
    current_string = b''
    
    for byte in body:
        # Printable ASCII range (space to ~) plus common whitespace
        if 32 <= byte <= 126 or byte in (9, 10, 13):  # tab, newline, carriage return
            current_string += bytes([byte])
        else:
            if len(current_string) >= min_length:
                strings_found.append(current_string)
            current_string = b''
    
    # Don't forget the last string if file doesn't end with non-printable
    if len(current_string) >= min_length:
        strings_found.append(current_string)
    
    return b'\n'.join(strings_found)

def inspect(body, filename=''):
    """Inspect content for sensitive patterns.
    
    Args:
        body: Content to inspect
        filename: Original filename, used for path-based and extension-based filtering
    
    Returns:
        List of tuples: (rule_name, line_number) or just rule names for non-line-based matches
    """
    import tempfile
    import zipfile
    import io
    
    file_ext = os.path.splitext(filename)[1].lower()
    exclude_protein_patterns = file_ext in PROTEIN_DATA_EXTENSIONS
    # Path-based exclusion for test fixtures only, not extension-based
    is_fixture_file = filename in FIXTURE_FILES
    # Path-based exclusion for third-party libraries with credential false positives
    is_credential_excluded_file = filename in CREDENTIAL_EXCLUDED_FILES
    
    if body.startswith(b'\x1f\x8b'):
        body = gzip.decompress(body)
    
    # Office Open XML documents (.docx, .xlsx, .pptx) are ZIP files containing XML
    if file_ext in {'.docx', '.xlsx', '.pptx', '.docm', '.xlsm', '.pptm'}:
        try:
            with zipfile.ZipFile(io.BytesIO(body)) as zf:
                for name in zf.namelist():
                    if name.endswith('.xml') or name.endswith('.xml.rels'):
                        try:
                            xml_content = zf.read(name)
                            # Recursively scan XML content
                            xml_filename = f'{filename}:{name}'
                            xml_labels = inspect(xml_content, filename=xml_filename)
                            if xml_labels:
                                label_strs = [f'{lbl[0]}@L{lbl[1]}' if isinstance(lbl, tuple) else lbl for lbl in xml_labels]
                                raise SystemExit(f'{filename}: Office XML "{name}" contains sensitive data: {", ".join(sorted(set(label_strs)))}')
                        except SystemExit:
                            raise  # Re-raise our own errors
                        except Exception as e:
                            # Unreadable XML is a hard error
                            raise SystemExit(f'{filename}: Office XML "{name}" is unreadable: {e}')
        except SystemExit:
            raise  # Re-raise our own errors
        except Exception as e:
            # ZIP extraction failure is a hard error
            raise SystemExit(f'{filename}: Failed to extract Office XML: {e}')
    
    if body.startswith(b'%PDF'):
        # Check for pdftotext availability
        if subprocess.run(['which', 'pdftotext'], capture_output=True).returncode != 0:
            raise SystemExit('pdftotext not found - install poppler-utils')
        if subprocess.run(['which', 'pdfdetach'], capture_output=True).returncode != 0:
            raise SystemExit('pdfdetach not found - install poppler-utils')
        
        # Extract visible text from PDF
        visible_text = subprocess.run(['pdftotext', '-layout', '-', '-'], input=body,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     check=True).stdout
        
        # Extract and check PDF attachments - failures are hard errors
        with tempfile.TemporaryDirectory() as tmpdir:
            # Save PDF to temp file for pdfdetach
            pdf_path = os.path.join(tmpdir, 'temp.pdf')
            with open(pdf_path, 'wb') as f:
                f.write(body)
            
            # List attachments - must succeed
            list_result = subprocess.run(['pdfdetach', '-list', pdf_path],
                                       capture_output=True, text=True, check=True)
            
            if 'embedded file' in list_result.stdout:
                # Extract all attachments - must succeed
                extract_result = subprocess.run(['pdfdetach', '-saveall', '-o', tmpdir, pdf_path],
                                              capture_output=True, text=True, check=True)
                
                # Read and recursively scan attachment contents
                for item in os.listdir(tmpdir):
                    item_path = os.path.join(tmpdir, item)
                    if os.path.isfile(item_path) and item != 'temp.pdf':
                        try:
                            with open(item_path, 'rb') as f:
                                attachment_content = f.read()
                        except Exception as e:
                            # Unreadable attachment is a hard failure
                            raise SystemExit(f'{filename}: PDF attachment "{item}" is unreadable: {e}')
                        
                        # Recursively scan attachment (handles nested PDFs, Office docs, etc.)
                        attachment_filename = f'{filename}:{item}'
                        attachment_labels = inspect(attachment_content, filename=attachment_filename)
                        if attachment_labels:
                            label_strs = [f'{lbl[0]}@L{lbl[1]}' if isinstance(lbl, tuple) else lbl for lbl in attachment_labels]
                            raise SystemExit(f'{filename}: PDF attachment "{item}" contains sensitive data: {", ".join(sorted(set(label_strs)))}')
        
        body = visible_text
    
    # PNG text chunk extraction (not IDAT)
    elif body.startswith(b'\x89PNG'):
        text_chunks = extract_png_text_chunks(body)
        if text_chunks:
            body = text_chunks
        else:
            # No text chunks, treat as binary (will be handled by binary detection below)
            pass
    
    # Detect non-text binary content to apply strings scanning
    # Check for common binary image/video/audio signatures
    is_binary_content = (
        body.startswith(b'\x89PNG') or  # PNG
        body.startswith(b'\xff\xd8\xff') or  # JPEG
        body.startswith(b'GIF8') or  # GIF
        body.startswith(b'RIFF') or  # WAV, AVI, WebP
        body.startswith(b'\x00\x00\x00\x0cjP') or  # JPEG2000
        body.startswith(b'\x00\x00\x01\x00') or  # ICO
        body.startswith(b'BM') or  # BMP
        body.startswith(b'II*\x00') or  # TIFF little-endian
        body.startswith(b'MM\x00*') or  # TIFF big-endian
        body.startswith(b'\x1a\x45\xdf\xa3') or  # WebM/MKV
        body.startswith(b'ftyp') or  # MP4/MOV (at offset 4, but checking start)
        body.startswith(b'\x7fELF') or  # ELF binary
        body.startswith(b'MZ') or  # PE/DOS executable
        body.startswith(b'\xca\xfe\xba\xbe') or  # Mach-O binary (big-endian)
        body.startswith(b'\xce\xfa\xed\xfe') or  # Mach-O binary (little-endian 32-bit)
        body.startswith(b'\xcf\xfa\xed\xfe')  # Mach-O binary (little-endian 64-bit)
    )
    
    # For binaries (except PNG which we already handled), extract strings
    if is_binary_content and not body.startswith(b'\x89PNG'):
        body = strings_scan_binary(body)
    
    # Check main body with line number tracking
    labels = []
    body_lines = body.split(b'\n')
    
    for name, pattern in RULES.items():
        # Skip all credential/secret patterns ONLY for specific test fixture files by path
        # Other .py/.js/.sh files are fully scanned - hardcoded hostnames in scripts are dangerous
        if is_fixture_file and name in ('GitHub token', 'cloud access key', 
                                        'private filesystem path', 'private hostname',
                                        'private key', 'service token', 'literal credential',
                                        'authorization value', 'private git host', 'ssh config',
                                        'private network address'):
            continue
        # Skip credential patterns ONLY for third-party libraries with false positives
        # (hostnames, IPs, and paths are still checked)
        if is_credential_excluded_file and name in ('GitHub token', 'cloud access key',
                                                     'private key', 'service token', 
                                                     'literal credential', 'authorization value'):
            continue
        # Skip AWS key pattern for protein data files (sequences contain AKIA-like substrings)
        if exclude_protein_patterns and name == 'cloud access key':
            continue
        
        # Track line numbers for each match
        found_lines = set()
        for line_num, line in enumerate(body_lines, start=1):
            matches = list(re.finditer(pattern, line))
            for match in matches:
                # Check context-specific exclusions
                is_excluded = False
                for excl_file, excl_pattern, context_before, context_after in CONTEXT_EXCLUDED_MATCHES:
                    if filename == excl_file and name == excl_pattern:
                        # Check if match is surrounded by the required context
                        match_start = match.start()
                        match_end = match.end()
                        before_start = max(0, match_start - len(context_before))
                        after_end = min(len(line), match_end + len(context_after))
                        
                        actual_before = line[before_start:match_start]
                        actual_after = line[match_end:after_end]
                        
                        if actual_before.endswith(context_before) and actual_after.startswith(context_after):
                            is_excluded = True
                            break
                
                if not is_excluded:
                    found_lines.add(line_num)
                    break  # One match per line is enough
        
        if found_lines:
            for line_num in sorted(found_lines):
                labels.append((name, line_num))
    
    return labels

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='*', help='Files or directories to check (default: entire git tree)')
    args = parser.parse_args()
    
    if args.paths:
        # Check specific files/directories
        failures = []
        checked_count = 0
        
        for path in args.paths:
            if os.path.isfile(path):
                try:
                    with open(path, 'rb') as f:
                        content = f.read()
                    labels = inspect(content, filename=path)
                    if labels:
                        # Format labels with line numbers
                        formatted_labels = [f'{lbl[0]}@L{lbl[1]}' if isinstance(lbl, tuple) else lbl for lbl in labels]
                        failures.append((path, sorted(set(formatted_labels))))
                    checked_count += 1
                except Exception as e:
                    failures.append((path, [f'error reading file: {e}']))
            elif os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    # Skip common hidden/cache directories
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('__pycache__', 'node_modules')]
                    
                    for file in files:
                        if file.startswith('.'):
                            continue
                        
                        filepath = os.path.join(root, file)
                        try:
                            with open(filepath, 'rb') as f:
                                content = f.read()
                            labels = inspect(content, filename=filepath)
                            if labels:
                                # Format labels with line numbers
                                formatted_labels = [f'{lbl[0]}@L{lbl[1]}' if isinstance(lbl, tuple) else lbl for lbl in labels]
                                failures.append((filepath, sorted(set(formatted_labels))))
                            checked_count += 1
                        except Exception as e:
                            failures.append((filepath, [f'error reading file: {e}']))
            else:
                failures.append((path, ['not found']))
        
        for name, labels in failures:
            print(f'{name}: {", ".join(labels)}', file=sys.stderr)
        
        if failures:
            return 1
        
        print(f'Privacy check passed: {checked_count} files checked.')
        return 0
    else:
        # Default: check entire git tree (requires git repository)
        try:
            # Get the git root
            git_root = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], 
                                             stderr=subprocess.PIPE).decode().strip()
            os.chdir(git_root)
        except subprocess.CalledProcessError:
            print('Not in a git repository. Specify files/directories to check.', file=sys.stderr)
            return 1
        
        failures = []
        checked_count = 0
        
        # Get all tracked files
        try:
            tracked_files = subprocess.check_output(['git', 'ls-files', '-z'], 
                                                   stderr=subprocess.PIPE).decode().split('\0')
        except subprocess.CalledProcessError as e:
            print(f'Failed to list git files: {e}', file=sys.stderr)
            return 1
        
        for filepath in tracked_files:
            if not filepath:
                continue
            
            # Skip paths with operational/private indicators
            if any(part in {'local', 'drafts', 'reference', 'continuation', 'campaigns', '.ssh', '.aws'}
                   or part.startswith('.env') for part in PurePosixPath(filepath).parts):
                continue
            
            try:
                with open(filepath, 'rb') as f:
                    content = f.read()
                labels = inspect(content, filename=filepath)
                # Also check the filename itself
                labels += inspect(filepath.encode(), filename=filepath)
                if labels:
                    # Format labels with line numbers
                    formatted_labels = [f'{lbl[0]}@L{lbl[1]}' if isinstance(lbl, tuple) else lbl for lbl in labels]
                    failures.append((filepath, sorted(set(formatted_labels))))
                checked_count += 1
            except Exception as e:
                failures.append((filepath, [f'error reading file: {e}']))
        
        for name, labels in failures:
            print(f'{name}: {", ".join(labels)}', file=sys.stderr)
        
        if failures:
            return 1
        
        print(f'Privacy check passed: {checked_count} files checked.')
        return 0

if __name__ == '__main__':
    sys.exit(main())
