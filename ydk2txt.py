# -*- coding: utf-8 -*-
#!/usr/bin/env python3
import sys
import sqlite3
import argparse
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, NamedTuple

# Try to import clipboard library
try:
    import pyperclip
    HAS_PYPERCLIP = True
except ImportError:
    HAS_PYPERCLIP = False


# ==================== Data Structures ====================
class YdkDeck(NamedTuple):
    main: List[int]
    extra: List[int]
    side: List[int]


# ==================== YDK Parser ====================
class YdkParser:
    @staticmethod
    def parse(file_path: str) -> YdkDeck:
        """Parse YDK file and return YdkDeck object."""
        main: List[int] = []
        extra: List[int] = []
        side: List[int] = []
        current_section: Optional[str] = None

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line == '#main':
                    current_section = 'main'
                    continue
                elif line == '#extra':
                    current_section = 'extra'
                    continue
                elif line == '!side':
                    current_section = 'side'
                    continue
                if line.startswith('#') or line.startswith('!'):
                    continue
                if not line.isdigit():
                    continue
                card_id = int(line)
                if current_section == 'main':
                    main.append(card_id)
                elif current_section == 'extra':
                    extra.append(card_id)
                elif current_section == 'side':
                    side.append(card_id)
        return YdkDeck(main, extra, side)


# ==================== Card Database ====================
class CardDatabase:
    def __init__(self, db_path: Path):
        if not db_path.exists():
            raise FileNotFoundError(f"Database file not found: {db_path}")
        self.db_path = db_path
        self._validate_table()

    def _validate_table(self):
        """Ensure 'texts' table exists."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='texts'")
            if not cursor.fetchone():
                raise RuntimeError("Database does not contain 'texts' table")

    def get_card_names(self, card_ids: List[int]) -> Dict[int, Optional[str]]:
        """Return dict mapping card ID to card name (None if missing)."""
        if not card_ids:
            return {}
        placeholders = ','.join('?' * len(card_ids))
        query = f"SELECT id, name FROM texts WHERE id IN ({placeholders})"
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, card_ids)
            rows = cursor.fetchall()
        name_map = {row[0]: row[1] for row in rows}
        # Fill missing IDs with None
        for cid in card_ids:
            name_map.setdefault(cid, None)
        return name_map


# ==================== Output Formatter ====================
class OutputFormatter:
    @staticmethod
    def format_deck(deck: YdkDeck, name_map: Dict[int, Optional[str]]) -> str:
        """Generate formatted string with section headers and card counts."""
        lines = []

        if deck.main:
            lines.append(f"#main ({len(deck.main)})")
            lines.extend(OutputFormatter._map_names(deck.main, name_map))

        if deck.extra:
            if lines:
                lines.append("")
            lines.append(f"#extra ({len(deck.extra)})")
            lines.extend(OutputFormatter._map_names(deck.extra, name_map))

        if deck.side:
            if lines:
                lines.append("")
            lines.append(f"!side ({len(deck.side)})")
            lines.extend(OutputFormatter._map_names(deck.side, name_map))

        return "\n".join(lines)

    @staticmethod
    def _map_names(ids: List[int], name_map: Dict[int, Optional[str]]) -> List[str]:
        """Convert list of IDs to list of names (with fallback for missing)."""
        return [
            name_map[cid] if name_map.get(cid) is not None else f"??? (ID:{cid})"
            for cid in ids
        ]


# ==================== Clipboard Utility ====================
class ClipboardUtil:
    @staticmethod
    def copy(text: str) -> bool:
        """Copy text to clipboard, returns True on success."""
        if HAS_PYPERCLIP:
            try:
                pyperclip.copy(text)
                return True
            except Exception as e:
                print(f"pyperclip failed: {e}", file=sys.stderr)

        # Fallback to system commands
        if sys.platform == "win32":
            return ClipboardUtil._copy_windows(text)
        elif sys.platform == "darwin":
            return ClipboardUtil._copy_macos(text)
        else:
            return ClipboardUtil._copy_linux(text)

    @staticmethod
    def _copy_windows(text: str) -> bool:
        try:
            proc = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
            proc.communicate(input=text.encode("utf-16-le"))
            return proc.returncode == 0
        except Exception as e:
            print(f"Windows clip failed: {e}", file=sys.stderr)
            return False

    @staticmethod
    def _copy_macos(text: str) -> bool:
        try:
            proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, text=True)
            proc.communicate(input=text)
            return proc.returncode == 0
        except Exception as e:
            print(f"macOS pbcopy failed: {e}", file=sys.stderr)
            return False

    @staticmethod
    def _copy_linux(text: str) -> bool:
        for cmd in [["xclip", "-selection", "clipboard"], ["xsel", "-i", "-b"]]:
            try:
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, text=True)
                proc.communicate(input=text)
                if proc.returncode == 0:
                    return True
            except FileNotFoundError:
                continue
            except Exception as e:
                print(f"Command {cmd[0]} failed: {e}", file=sys.stderr)
        print("Linux clipboard tools (xclip or xsel) not found", file=sys.stderr)
        return False


# ==================== Main ====================
def get_default_db_path() -> Path:
    """Return default cards.cdb path (same directory as this script)."""
    return Path(sys.argv[0]).resolve().parent / "cards.cdb"


def main():
    # If no arguments provided, show help and exit
    if len(sys.argv) == 1:
        parser = argparse.ArgumentParser(description="Convert YDK deck file to card name list")
        parser.print_help()
        sys.exit(0)

    parser = argparse.ArgumentParser(description="Convert YDK deck file to card name list")
    parser.add_argument("-y", "--ydk", required=True, help="Path to YDK file")
    parser.add_argument("-o", "--output", help="Output to TXT file (default: print to console)")
    parser.add_argument("-c", "--clipboard", action="store_true", help="Copy to clipboard (overrides -o)")
    parser.add_argument("-d", "--db", help="Path to cards.cdb database (default: same directory as this script)")
    parser.add_argument("--encoding", default="utf-8", help="Output file encoding (default: utf-8)")
    args = parser.parse_args()

    # Determine database path
    db_path = Path(args.db) if args.db else get_default_db_path()
    if not db_path.exists():
        sys.exit(f"Error: Database file not found at {db_path}")

    # Parse YDK
    try:
        deck = YdkParser.parse(args.ydk)
    except Exception as e:
        sys.exit(f"Failed to parse YDK file: {e}")

    if not (deck.main or deck.extra or deck.side):
        print("Warning: No card IDs found in YDK file", file=sys.stderr)

    all_ids = list(set(deck.main + deck.extra + deck.side))
    if not all_ids:
        sys.exit("No cards to process, exiting")

    # Query card names
    try:
        db = CardDatabase(db_path)
        name_map = db.get_card_names(all_ids)
    except Exception as e:
        sys.exit(f"Database query failed: {e}")

    # Format output
    output_text = OutputFormatter.format_deck(deck, name_map)

    # Output
    if args.clipboard:
        if ClipboardUtil.copy(output_text):
            print("Card list copied to clipboard")
        else:
            sys.exit(
                "Failed to copy to clipboard.\n"
                "Install pyperclip: pip install pyperclip\n"
                "Or ensure system clipboard tool is available:\n"
                "  Windows: clip (built-in)\n"
                "  macOS: pbcopy (built-in)\n"
                "  Linux: xclip or xsel (install via package manager)"
            )
    elif args.output:
        try:
            with open(args.output, 'w', encoding=args.encoding) as f:
                f.write(output_text)
            print(f"Card list saved to {args.output} (encoding: {args.encoding})")
        except Exception as e:
            sys.exit(f"Failed to write file: {e}")
    else:
        print(output_text)


if __name__ == "__main__":
    main()
