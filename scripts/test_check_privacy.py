#!/usr/bin/env python3
"""Tests for check_privacy.py privacy checker."""
import tempfile
import os
import subprocess
import sys
from pathlib import Path

def create_test_pdf_with_dirty_attachment():
    """Create a PDF with clean visible text but dirty attachment.
    
    This tests the exact bug: attachments were not being scanned.
    """
    try:
        import pikepdf
        from reportlab.pdfgen import canvas as pdf_canvas
        from reportlab.lib.pagesizes import letter
    except ImportError as e:
        # In CI, missing dependencies are a hard failure
        if os.environ.get('CI') == 'true':
            raise SystemExit(f"Required test dependency missing in CI: {e}")
        print("  ⚠ SKIP: pikepdf or reportlab not installed")
        return None
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a clean PDF using reportlab
        pdf_path = os.path.join(tmpdir, 'test.pdf')
        c = pdf_canvas.Canvas(pdf_path, pagesize=letter)
        c.drawString(100, 750, "Clean visible text - no sensitive information here")
        c.save()
        
        # Now add the dirty attachment using pikepdf
        pdf_with_attachment_path = os.path.join(tmpdir, 'test_with_attachment.pdf')
        with pikepdf.open(pdf_path) as pdf:
            # Create a dirty attachment with private path
            dirty_content = b'This file contains /home/fakeuser/private/code/project/sensitive.txt'
            attachment = pikepdf.Stream(pdf, dirty_content)
            
            # Add the attachment
            if '/Names' not in pdf.Root:
                pdf.Root.Names = pikepdf.Dictionary()
            
            filespec = pikepdf.Dictionary(
                Type=pikepdf.Name.Filespec,
                F='dirty_file.txt',
                EF=pikepdf.Dictionary(F=attachment)
            )
            
            pdf.Root.Names.EmbeddedFiles = pikepdf.Dictionary(
                Names=pikepdf.Array([pikepdf.String('dirty_file.txt'), filespec])
            )
            
            pdf.save(pdf_with_attachment_path)
        
        with open(pdf_with_attachment_path, 'rb') as f:
            return f.read()


def create_test_content_with_hostname(hostname):
    """Create test content with a hostname."""
    return f'Server: {hostname}\nConnection established'.encode()


def test_pdf_with_dirty_attachment():
    """Test that PDF with dirty attachment but clean visible text is rejected."""
    print("Test: PDF with dirty attachment (clean visible text)")
    
    pdf_content = create_test_pdf_with_dirty_attachment()
    if pdf_content is None:
        return None  # Skip test
    
    from check_privacy import inspect
    
    # With recursive scanning, this should now raise SystemExit
    try:
        labels = inspect(pdf_content, filename='test.pdf')
        print("  ✗ FAIL: Did not detect private path in PDF attachment (no exception raised)")
        return False
    except SystemExit as e:
        if 'PDF attachment' in str(e) and 'private filesystem path' in str(e):
            print("  ✓ PASS: Detected private path in PDF attachment (hard failure)")
            return True
        else:
            print(f"  ✗ FAIL: Wrong error: {e}")
            return False


def test_hostname_detection_case_insensitive():
    """Test that hostnames are detected case-insensitively."""
    print("Test: Case-insensitive hostname detection")
    
    from check_privacy import inspect
    
    # Build hostnames from fragments to avoid literal sensitive strings
    h1_lower = 'p' + 'a' + 'x'
    h1_upper = 'P' + 'A' + 'X'
    h1_mixed = 'P' + 'a' + 'x'
    h2_lower = 'm' + 'i' + 'm' + 'as'
    h2_upper = 'M' + 'I' + 'M' + 'AS'
    h2_mixed = 'M' + 'i' + 'm' + 'as'
    h2_embedded = 'M' + 'i' + 'm' + 'as' + '_Folding_Skills'
    
    test_cases = [
        (h1_lower, 'lowercase'),
        (h1_upper, 'uppercase'),
        (h1_mixed, 'mixed case'),
        (h2_lower, 'lowercase'),
        (h2_upper, 'uppercase'),
        (h2_mixed, 'mixed case'),
        (h2_embedded, 'embedded in identifier'),
    ]
    
    all_passed = True
    for hostname, description in test_cases:
        content = create_test_content_with_hostname(hostname)
        labels = inspect(content, filename='test.txt')
        
        # Extract just the rule names (ignore line numbers)
        rule_names = [lbl[0] if isinstance(lbl, tuple) else lbl for lbl in labels]
        
        if 'private hostname' in rule_names:
            print(f"  ✓ PASS: Detected '{hostname}' ({description})")
        else:
            print(f"  ✗ FAIL: Did not detect '{hostname}' ({description})")
            all_passed = False
    
    return all_passed


def test_protein_sequence_exclusion():
    """Test that protein sequences don't trigger false positives."""
    print("Test: Protein sequence exclusion from AWS key pattern")
    
    from check_privacy import inspect
    
    # Protein sequence with AKIA-like substring (common in real sequences)
    protein_content = b'>seq1\nMAKIAEADKVTVTVAVPEDATHADILDLALPAAAQLTASDKPVEPIAVAFH\n'
    
    # Should not match in CSV files
    labels = inspect(protein_content, filename='sequences.csv')
    
    # Extract just the rule names (ignore line numbers)
    rule_names = [lbl[0] if isinstance(lbl, tuple) else lbl for lbl in labels]
    
    if 'cloud access key' in rule_names:
        print("  ✗ FAIL: False positive on protein sequence in CSV")
        return False
    else:
        print("  ✓ PASS: No false positive on protein sequence in CSV")
    
    # Should still match in non-protein files
    aws_key_content = b'AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE'
    labels = inspect(aws_key_content, filename='config.txt')
    
    # Extract just the rule names (ignore line numbers)
    rule_names = [lbl[0] if isinstance(lbl, tuple) else lbl for lbl in labels]
    
    if 'cloud access key' in rule_names:
        print("  ✓ PASS: Real AWS key detected in non-protein file")
        return True
    else:
        print("  ✗ FAIL: Real AWS key not detected")
        return False


def test_tailscale_and_private_networks():
    """Test that Tailscale and RFC1918 networks are detected."""
    print("Test: Tailscale and private network detection")
    
    from check_privacy import inspect
    
    test_cases = [
        (b'Connect to server.ts.net:8080', 'Tailscale hostname'),
        (b'IP: 100.64.1.1', 'Tailscale IP (100.64/10)'),
        (b'Internal server: 192.168.1.100', 'RFC1918 (192.168)'),
        (b'Database at 10.0.0.50', 'RFC1918 (10.0)'),
        (b'App server: 172.16.0.10', 'RFC1918 (172.16)'),
    ]
    
    all_passed = True
    for content, description in test_cases:
        labels = inspect(content, filename='config.txt')
        
        # Extract just the rule names (ignore line numbers)
        rule_names = [lbl[0] if isinstance(lbl, tuple) else lbl for lbl in labels]
        
        if 'private network address' in rule_names:
            print(f"  ✓ PASS: Detected {description}")
        else:
            print(f"  ✗ FAIL: Did not detect {description}")
            all_passed = False
    
    return all_passed


def test_python_script_with_hardcoded_hostname():
    """Test that .py files with hardcoded hostnames are rejected.
    
    This proves the narrowing works: the broad extension-based exclusion
    would have let this pass, but path-based exclusion only covers test fixtures.
    """
    print("Test: Python script with hardcoded hostname is rejected")
    
    from check_privacy import inspect
    
    # Build hostname from fragments to avoid literal sensitive strings
    test_host = 'test-' + 'p' + 'a' + 'x'
    
    # A helper script with a hardcoded SSH invocation to a private host
    script_content = f"""#!/usr/bin/env python3
import subprocess

def deploy_to_server():
    # Deploy files to the private server {test_host}
    subprocess.run(['ssh', 'user@{test_host}', 'mkdir -p /opt/deploy'])
    return True
""".encode()
    
    # This is scripts/deploy_helper.py - NOT in FIXTURE_FILES, so must be scanned
    labels = inspect(script_content, filename='scripts/deploy_helper.py')
    
    # Extract just the rule names (ignore line numbers)
    rule_names = [lbl[0] if isinstance(lbl, tuple) else lbl for lbl in labels]
    
    if 'private hostname' in rule_names:
        print("  ✓ PASS: Detected hardcoded hostname in .py script")
        return True
    else:
        print("  ✗ FAIL: Did not detect hardcoded hostname in .py script")
        return False


def test_png_text_chunks():
    """Test that PNG text chunks are scanned (not IDAT)."""
    print("Test: PNG text chunk scanning")
    
    from check_privacy import inspect
    import struct
    import zlib
    
    # Create a minimal PNG with a text chunk containing sensitive data
    # PNG signature
    png_data = b'\x89PNG\r\n\x1a\n'
    
    # IHDR chunk (minimal 1x1 image)
    ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff
    png_data += struct.pack('>I', len(ihdr_data)) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)
    
    # tEXt chunk with private path
    text_content = b'Author\x00/home/secretuser/project/image.png'
    text_crc = zlib.crc32(b'tEXt' + text_content) & 0xffffffff
    png_data += struct.pack('>I', len(text_content)) + b'tEXt' + text_content + struct.pack('>I', text_crc)
    
    # IDAT chunk (minimal image data - should not be scanned)
    idat_data = zlib.compress(b'\x00\xff\xff\xff')
    idat_crc = zlib.crc32(b'IDAT' + idat_data) & 0xffffffff
    png_data += struct.pack('>I', len(idat_data)) + b'IDAT' + idat_data + struct.pack('>I', idat_crc)
    
    # IEND chunk
    iend_crc = zlib.crc32(b'IEND') & 0xffffffff
    png_data += struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
    
    labels = inspect(png_data, filename='image.png')
    
    # Extract just the rule names (ignore line numbers)
    rule_names = [lbl[0] if isinstance(lbl, tuple) else lbl for lbl in labels]
    
    if 'private filesystem path' in rule_names:
        print("  ✓ PASS: Detected private path in PNG text chunk")
        return True
    else:
        print("  ✗ FAIL: Did not detect private path in PNG text chunk")
        return False


def test_binary_strings_scan():
    """Test that binary files are scanned with strings extraction."""
    print("Test: Binary strings scanning")
    
    from check_privacy import inspect
    
    # Create a fake binary with embedded string
    binary_data = b'\x7fELF\x02\x01\x01\x00'  # ELF header
    binary_data += b'\x00' * 100  # Null bytes
    binary_data += b'ssh user@' + 'p'.encode() + 'a'.encode() + 'x'.encode() + b'.example.com'
    binary_data += b'\x00' * 100
    
    labels = inspect(binary_data, filename='binary_executable')
    
    # Extract just the rule names (ignore line numbers)
    rule_names = [lbl[0] if isinstance(lbl, tuple) else lbl for lbl in labels]
    
    if 'private hostname' in rule_names:
        print("  ✓ PASS: Detected hostname in binary via strings scan")
        return True
    else:
        print("  ✗ FAIL: Did not detect hostname in binary")
        return False


def test_ssh_identity_files():
    """Test that SSH identity file patterns are detected."""
    print("Test: SSH identity file detection")
    
    from check_privacy import inspect
    
    ssh_config = b"""
Host production
    HostName 10.0.1.50
    User deployer
    IdentityFile ~/.ssh/production_rsa
    ProxyCommand ssh bastion -W %h:%p
"""
    
    labels = inspect(ssh_config, filename='ssh_config')
    
    # Extract just the rule names (ignore line numbers)
    rule_names = [lbl[0] if isinstance(lbl, tuple) else lbl for lbl in labels]
    
    if 'ssh config' in rule_names:
        print("  ✓ PASS: Detected SSH config entries")
        return True
    else:
        print("  ✗ FAIL: Did not detect SSH config entries")
        return False


def test_private_git_host():
    """Test that private git hosts are detected."""
    print("Test: Private git host detection")
    
    from check_privacy import inspect
    
    # Build git host from fragments
    git_host = 'github.' + 'r' + 'p' + 'i' + '.edu'
    content = f'git clone https://{git_host}/user/repo.git'.encode()
    
    labels = inspect(content, filename='README.md')
    
    # Extract just the rule names (ignore line numbers)
    rule_names = [lbl[0] if isinstance(lbl, tuple) else lbl for lbl in labels]
    
    if 'private git host' in rule_names:
        print("  ✓ PASS: Detected private git host")
        return True
    else:
        print("  ✗ FAIL: Did not detect private git host")
        return False


def test_gzip_decompression():
    """Test that .gz files are decompressed and scanned."""
    print("Test: Gzip decompression")
    
    from check_privacy import inspect
    import gzip
    
    # Compress content with private path
    original_content = b'Configuration: /home/testuser/secret/config.yaml'
    compressed_content = gzip.compress(original_content)
    
    labels = inspect(compressed_content, filename='data.json.gz')
    
    # Extract just the rule names (ignore line numbers)
    rule_names = [lbl[0] if isinstance(lbl, tuple) else lbl for lbl in labels]
    
    if 'private filesystem path' in rule_names:
        print("  ✓ PASS: Detected private path in gzipped file")
        return True
    else:
        print("  ✗ FAIL: Did not detect private path in gzipped file")
        return False


def test_plotly_context_exclusion():
    """Test that plotly.min.js false positives pass only in exact context."""
    print("Test: Plotly context-specific exclusion")
    
    from check_privacy import inspect
    
    # Build the hostname from fragments
    h_fragment = 'P' + 'a' + 'x'
    
    # Test 1: Maya calendar context in the correct file PASSES
    maya_calendar_content = f'"Mol","Chen","Yax","Zac","Ceh","Mac","Kankin","Muan","{h_fragment}","Kayab","Cumku","Uayeb"'.encode()
    labels = inspect(maya_calendar_content, filename='assets/plotly.min.js')
    rule_names = [lbl[0] if isinstance(lbl, tuple) else lbl for lbl in labels]
    
    if 'private hostname' not in rule_names:
        print("  ✓ PASS: Maya calendar context in correct file excluded")
    else:
        print("  ✗ FAIL: Maya calendar context should be excluded in correct file")
        return False
    
    # Test 2: Same word elsewhere in the SAME file FAILS
    other_context_content = f'server: {h_fragment}\nconnection established'.encode()
    labels = inspect(other_context_content, filename='assets/plotly.min.js')
    rule_names = [lbl[0] if isinstance(lbl, tuple) else lbl for lbl in labels]
    
    if 'private hostname' in rule_names:
        print("  ✓ PASS: Same word in different context of same file detected")
    else:
        print("  ✗ FAIL: Same word outside calendar context should be detected")
        return False
    
    # Test 3: Exact same calendar text in DIFFERENT file FAILS
    labels = inspect(maya_calendar_content, filename='data/calendars.js')
    rule_names = [lbl[0] if isinstance(lbl, tuple) else lbl for lbl in labels]
    
    if 'private hostname' in rule_names:
        print("  ✓ PASS: Same calendar text in different file detected")
    else:
        print("  ✗ FAIL: Calendar text in different file should be detected")
        return False
    
    # Test 4: Incomplete context in correct file FAILS (missing "Muan" before)
    incomplete_before = f'"Kankin","{h_fragment}","Kayab","Cumku"'.encode()
    labels = inspect(incomplete_before, filename='assets/plotly.min.js')
    rule_names = [lbl[0] if isinstance(lbl, tuple) else lbl for lbl in labels]
    
    if 'private hostname' in rule_names:
        print("  ✓ PASS: Incomplete context (missing required before) detected")
    else:
        print("  ✗ FAIL: Should detect when required before-context is missing")
        return False
    
    # Test 5: Incomplete context in correct file FAILS (missing "Kayab" after)
    incomplete_after = f'"Muan","{h_fragment}","Uayeb"'.encode()
    labels = inspect(incomplete_after, filename='assets/plotly.min.js')
    rule_names = [lbl[0] if isinstance(lbl, tuple) else lbl for lbl in labels]
    
    if 'private hostname' in rule_names:
        print("  ✓ PASS: Incomplete context (missing required after) detected")
    else:
        print("  ✗ FAIL: Should detect when required after-context is missing")
        return False
    
    # Test 6: OppAxisClassName in correct file PASSES
    opp_axis_class = b'OppAxisClassName'
    labels = inspect(opp_axis_class, filename='assets/plotly.min.js')
    rule_names = [lbl[0] if isinstance(lbl, tuple) else lbl for lbl in labels]
    
    if 'private hostname' not in rule_names:
        print("  ✓ PASS: OppAxisClassName in correct file excluded")
    else:
        print("  ✗ FAIL: OppAxisClassName should be excluded in correct file")
        return False
    
    # Test 7: rangeslider-mask-opp-axis in correct file PASSES
    rangeslider = b'rangeslider-mask-opp-axis'
    labels = inspect(rangeslider, filename='assets/plotly.min.js')
    rule_names = [lbl[0] if isinstance(lbl, tuple) else lbl for lbl in labels]
    
    if 'private hostname' not in rule_names:
        print("  ✓ PASS: rangeslider-mask-opp-axis in correct file excluded")
        return True
    else:
        print("  ✗ FAIL: rangeslider-mask-opp-axis should be excluded in correct file")
        return False


def test_github_token_patterns():
    """Test that GitHub token patterns are detected."""
    print("Test: GitHub token detection")
    
    from check_privacy import inspect
    
    # Build tokens from fragments to avoid GitHub push protection
    ghp_prefix = 'gh' + 'p_'
    ghp_token = ghp_prefix + '1234567890abcdefghijklmnopqrstuvwxyz123'
    pat_prefix = 'github' + '_pat_'
    pat_token = pat_prefix + '123456789012345678901234567890123456'
    
    test_cases = [
        (f'export GITHUB_TOKEN={ghp_token}'.encode(), 'ghp_ token'),
        (f'token = "{pat_token}"'.encode(), 'github_pat_ token'),
    ]
    
    all_passed = True
    for content, description in test_cases:
        labels = inspect(content, filename='config.txt')
        
        # Extract just the rule names (ignore line numbers)
        rule_names = [lbl[0] if isinstance(lbl, tuple) else lbl for lbl in labels]
        
        if 'GitHub token' in rule_names:
            print(f"  ✓ PASS: Detected {description}")
        else:
            print(f"  ✗ FAIL: Did not detect {description}")
            all_passed = False
    
    return all_passed


def test_openai_api_key():
    """Test that OpenAI API keys are detected."""
    print("Test: OpenAI API key detection")
    
    from check_privacy import inspect
    
    # Build key from fragments to avoid GitHub push protection
    key_prefix = 's' + 'k-proj-'
    key_value = key_prefix + 'abcdefghijklmnopqrstuvwxyz123456'
    content = f'OPENAI_API_KEY={key_value}'.encode()
    labels = inspect(content, filename='config.txt')
    
    # Extract just the rule names (ignore line numbers)
    rule_names = [lbl[0] if isinstance(lbl, tuple) else lbl for lbl in labels]
    
    if 'service token' in rule_names:
        print("  ✓ PASS: Detected OpenAI API key")
        return True
    else:
        print("  ✗ FAIL: Did not detect OpenAI API key")
        return False


def test_slack_token():
    """Test that Slack tokens are detected."""
    print("Test: Slack token detection")
    
    from check_privacy import inspect
    
    # Build token from fragments to avoid GitHub push protection
    token_prefix = 'xox' + 'b-'
    token_value = token_prefix + '1234567890-1234567890123-abcdefghijklmnopqrstuvwxyz'
    content = f'SLACK_BOT_TOKEN={token_value}'.encode()
    labels = inspect(content, filename='config.txt')
    
    # Extract just the rule names (ignore line numbers)
    rule_names = [lbl[0] if isinstance(lbl, tuple) else lbl for lbl in labels]
    
    if 'service token' in rule_names:
        print("  ✓ PASS: Detected Slack token")
        return True
    else:
        print("  ✗ FAIL: Did not detect Slack token")
        return False


def main():
    """Run all tests."""
    print("Running check_privacy.py tests\n")
    
    # Import the module to test
    sys.path.insert(0, str(Path(__file__).parent))
    
    results = []
    
    # Run all tests
    test_result = test_pdf_with_dirty_attachment()
    if test_result is not None:
        results.append(test_result)
    print()
    
    results.append(test_hostname_detection_case_insensitive())
    print()
    results.append(test_protein_sequence_exclusion())
    print()
    results.append(test_tailscale_and_private_networks())
    print()
    results.append(test_python_script_with_hardcoded_hostname())
    print()
    results.append(test_png_text_chunks())
    print()
    results.append(test_binary_strings_scan())
    print()
    results.append(test_ssh_identity_files())
    print()
    results.append(test_private_git_host())
    print()
    results.append(test_gzip_decompression())
    print()
    results.append(test_plotly_context_exclusion())
    print()
    results.append(test_github_token_patterns())
    print()
    results.append(test_openai_api_key())
    print()
    results.append(test_slack_token())
    print()
    
    passed = sum(results)
    total = len(results)
    
    print(f"\n{'='*60}")
    print(f"Test Results: {passed}/{total} passed")
    print(f"{'='*60}")
    
    if passed == total:
        print("✓ All tests passed!")
        return 0
    else:
        print(f"✗ {total - passed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
