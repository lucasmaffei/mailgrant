"""mailgrant — multi-mailbox IMAP/SMTP control plane."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mailgrant")
except PackageNotFoundError:
    __version__ = "0.0.0+uninstalled"
