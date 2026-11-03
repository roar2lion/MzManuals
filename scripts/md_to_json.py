"""Put edited Markdown (from json_to_md.py) back into the manuals' JSON.

    python scripts/md_to_json.py                    choose from a list (all if not interactive)
    python scripts/md_to_json.py pypsa-architecture another-id
    python scripts/md_to_json.py --all [--yes]

Reads md/<id>.md and rewrites the JSON it came from. Parts you didn't edit keep
their original text, so the JSON diff shows only your changes. The result is
validated with the builder (scripts/builder/build.py --check); if that fails,
the JSON is put back as it was and the problems are listed.
"""
import argparse
import difflib
import json
import subprocess
import sys

from manual_md import (MD_DIR, ROOT, FormatError, file_hash, from_md, same, set_header_sha, with_nav,
                       write_json_text)

BUILD = ROOT / "scripts" / "builder" / "build.py"


def pick(names, what):
    print(f"{what}:")
    for i, n in enumerate(names, 1):
        print(f"  {i}. {n}")
    ans = input("Numbers separated by spaces, Enter = all: ").strip()
    if not ans:
        return names
    try:
        return [names[int(x) - 1] for x in ans.split()]
    except (ValueError, IndexError):
        sys.exit("Not a number from the list.")


def validate():
    r = subprocess.run([sys.executable, str(BUILD), "--check"], cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def refresh_md(md_path, text, manual, sha):
    """Point the md file at the JSON as now written, and refresh its Contents list and heading anchors."""
    new = with_nav(set_header_sha(text, sha), manual)
    if new != text:
        md_path.write_text(new, encoding="utf-8", newline="\n")


def convert(md_path, yes):
    text = md_path.read_text(encoding="utf-8")
    manual, head = from_md(text)
    target = ROOT / head["source"]
    rel = target.relative_to(ROOT).as_posix()
    old_text = target.read_text(encoding="utf-8") if target.exists() else ""
    if old_text:
        if same(manual, json.loads(old_text)):
            print(f"  {md_path.name}: no changes")
            refresh_md(md_path, text, manual, file_hash(target))
            return True
        if head["sha"] != file_hash(target) and not yes:
            ans = input(f"  {rel} has changed since {md_path.name} was made; writing would undo those changes. "
                        f"Continue? [y/N] ").strip().lower()
            if ans != "y":
                print("  skipped")
                return True
    new_text = write_json_text(manual, old_text)
    target.write_bytes(new_text.encode("utf-8"))
    ok, report = validate()
    if not ok:
        if old_text:
            target.write_bytes(old_text.encode("utf-8"))
        else:
            target.unlink()
        print(f"  {md_path.name}: the result doesn't validate, so {rel} was left unchanged:")
        print("    " + report.replace("\n", "\n    "))
        return False
    refresh_md(md_path, text, manual, file_hash(target))
    diff = [l for l in difflib.unified_diff(old_text.splitlines(), new_text.splitlines(), lineterm="", n=0)
            if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    added = sum(1 for l in diff if l.startswith("+"))
    print(f"  {md_path.name} -> {rel}: {added} line(s) added, {len(diff) - added} removed; validated")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*", help="manual ids (md/<id>.md)")
    ap.add_argument("--all", action="store_true", help="every md file in md/")
    ap.add_argument("--yes", action="store_true", help="don't ask, even if the JSON changed since the export")
    a = ap.parse_args()
    names = sorted(p.stem for p in MD_DIR.glob("*.md")) if MD_DIR.exists() else []
    if not names:
        sys.exit("No md files in md/. Make them with json_to_md first.")
    if a.ids:
        unknown = [i for i in a.ids if i not in names]
        if unknown:
            sys.exit(f"No md/{unknown[0]}.md. Available: {', '.join(names)}")
        chosen = a.ids
    elif a.all or not sys.stdin.isatty():
        chosen = names
    else:
        chosen = pick(names, "Markdown files in md")
    ok = True
    for n in chosen:
        try:
            ok &= convert(MD_DIR / f"{n}.md", a.yes)
        except FormatError as e:
            print(f"  {n}.md: {e}. Nothing written.")
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
