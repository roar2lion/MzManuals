"""Write manuals as Markdown, for reading and editing (e.g. with AI help).

    python scripts/json_to_md.py                    choose from a list (all if not interactive)
    python scripts/json_to_md.py pypsa-architecture another-id
    python scripts/json_to_md.py --all [--force]

Writes md/<id>.md from content/manuals/<id>.json. Bring edits back with
md_to_json.py. An md file holding edits that haven't gone back into the JSON
is only overwritten after you confirm (or with --force).
"""
import argparse
import json
import sys

from manual_md import MANUALS, MD_DIR, ROOT, FormatError, file_hash, from_md, same, to_md


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


def export(path, force):
    manual = json.loads(path.read_text(encoding="utf-8"))
    rel = path.relative_to(ROOT).as_posix()
    md = to_md(manual, rel, file_hash(path))
    back, _ = from_md(md)
    if not same(back, manual):
        raise FormatError(f"{rel}: the Markdown form would lose information; please report this")
    out = MD_DIR / f"{manual['id']}.md"
    if out.exists():
        old = out.read_text(encoding="utf-8")
        if old == md:
            print(f"  {out.relative_to(ROOT).as_posix()}: up to date")
            return True
        try:
            unchanged = same(from_md(old)[0], manual)
        except FormatError:
            unchanged = False
        if not unchanged and not force:
            ans = input(f"  {out.relative_to(ROOT).as_posix()} holds edits not yet in {rel} "
                        f"(or {rel} changed since). Overwrite it? [y/N] ").strip().lower()
            if ans != "y":
                print("  kept as it is")
                return True
    MD_DIR.mkdir(exist_ok=True)
    out.write_text(md, encoding="utf-8", newline="\n")
    print(f"  {rel} -> {out.relative_to(ROOT).as_posix()}")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*", help="manual ids (file names without .json)")
    ap.add_argument("--all", action="store_true", help="every manual")
    ap.add_argument("--force", action="store_true", help="overwrite md files even if they hold edits")
    a = ap.parse_args()
    names = sorted(p.stem for p in MANUALS.glob("*.json"))
    if a.ids:
        unknown = [i for i in a.ids if i not in names]
        if unknown:
            sys.exit(f"No such manual: {', '.join(unknown)}. Manuals: {', '.join(names)}")
        chosen = a.ids
    elif a.all or not sys.stdin.isatty():
        chosen = names
    else:
        chosen = pick(names, "Manuals in content/manuals")
    ok = True
    for n in chosen:
        try:
            ok &= export(MANUALS / f"{n}.json", a.force)
        except (FormatError, json.JSONDecodeError) as e:
            print(f"  {n}: {e}")
            ok = False
    if ok:
        print(f"\nEdit the files in md/, then run md_to_json to put the changes back into the JSON.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
