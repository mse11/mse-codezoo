"""CodeZoo: learn real Python through animal coding games."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mse-codezoo")
except PackageNotFoundError:  # running from a source tree that is not installed
    __version__ = "0.0.0"
