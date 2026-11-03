"""Compatibility entry point for the single maintained shared checker."""
import sys
from structure_clustering.cli import main
raise SystemExit(main(["check-privacy", *(sys.argv[1:] or ["--tracked"])]))
