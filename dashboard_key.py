"""Set the passphrase that encrypts the web-published term board.

Run this yourself, in your own terminal — not through Claude:

    python3 dashboard_key.py

The passphrase is stored in the macOS Keychain and never touches this repo,
git, or a conversation.

If the stocks dashboard already has a passphrase, this offers to reuse it so
one phrase unlocks every dashboard on the site. Reusing it is the whole point
of consolidating; generating a second one is offered for anyone who wants the
two separated.

On strength: the encrypted blob is served from a public URL, so anyone who
wants it can copy it once and then guess offline, forever, at whatever rate
their hardware allows. No server is there to rate-limit them. That makes the
passphrase the entire security model, which is why this generates one for you
instead of trusting a phrase you invent.
"""
import secrets
import sys
from math import log2

import keyring

SERVICE = "geoffreybian-dashboards"
ACCOUNT = "passphrase"
# Where the stocks dashboard keeps its own, so the two can be made identical.
STOCKS_SERVICE = "wealthsimple-stocks-folder"
STOCKS_ACCOUNT = "dashboard-passphrase"

WORDLIST = "/usr/share/dict/words"
N_WORDS = 6


def get_key() -> str:
    """Read the passphrase, falling back to the stocks one if it's the same key."""
    value = keyring.get_password(SERVICE, ACCOUNT)
    if value:
        return value
    value = keyring.get_password(STOCKS_SERVICE, STOCKS_ACCOUNT)
    if value:
        return value
    raise SystemExit(
        "No passphrase set. Run this yourself, in your own terminal:\n"
        "    python3 ~/dev/school/dashboard_key.py")


def _pool() -> list[str]:
    with open(WORDLIST) as fh:
        words = {w.strip().lower() for w in fh}
    return sorted(w for w in words if 4 <= len(w) <= 7 and w.isalpha() and w.isascii())


def main() -> None:
    existing = keyring.get_password(SERVICE, ACCOUNT)
    if existing:
        print(f"A passphrase is already set for {SERVICE}.")
        if input("Replace it? [y/N] ").strip().lower() != "y":
            return

    shared = keyring.get_password(STOCKS_SERVICE, STOCKS_ACCOUNT)
    if shared and not existing:
        print("The stocks dashboard already has a passphrase.")
        if input("Reuse it, so one phrase unlocks both? [Y/n] ").strip().lower() != "n":
            keyring.set_password(SERVICE, ACCOUNT, shared)
            print("Reusing the stocks passphrase. Nothing new to write down.")
            return

    pool = _pool()
    phrase = " ".join(secrets.choice(pool) for _ in range(N_WORDS))
    bits = N_WORDS * log2(len(pool))
    keyring.set_password(SERVICE, ACCOUNT, phrase)
    print(f"\n  {phrase}\n")
    print(f"{bits:.0f} bits from a {len(pool):,}-word pool. Saved to the Keychain.")
    print("Write it down somewhere you trust. Re-run this to rotate it, then")
    print("re-run publish_web.py — the old ciphertext is force-pushed away.")


if __name__ == "__main__":
    main()
