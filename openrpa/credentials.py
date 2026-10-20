"""OS-vault adapter. Unsupported or plaintext keyring backends are rejected."""

SAFE_BACKEND_MARKERS = (
    "keyring.backends.Windows.WinVaultKeyring",
    "keyring.backends.macOS.Keyring",
    "keyring.backends.SecretService.Keyring",
)


def get_safe_keyring():
    try:
        import keyring
    except ImportError as exc:
        raise RuntimeError("Secure credentials require the optional keyring package and an OS credential vault") from exc
    backend=keyring.get_keyring()
    backend_name=f"{type(backend).__module__}.{type(backend).__name__}"
    if not any(backend_name.startswith(marker) for marker in SAFE_BACKEND_MARKERS):
        raise RuntimeError(f"Refusing credential access through non-approved keyring backend: {backend_name}")
    return keyring
