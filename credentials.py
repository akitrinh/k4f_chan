"""Current-user Windows vault storage; no files, roaming, or import-time OS calls.

Translation secrets are namespaced by the canonical HTTPS API base endpoint,
including its path. Generic secrets (for example ``ai33``) use a separate app
namespace. CRED_PERSIST_LOCAL_MACHINE survives sign-out on this computer for the
same Windows account; it does not make credentials available to other accounts
and does not request enterprise roaming. A portable app folder contains no keys.
This protects storage at rest, not against software already running as that user.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import ipaddress
import re
import sys
from urllib.parse import urlsplit, urlunsplit


class CredentialError(Exception):
    """A safe user-facing message, never native error text or credential data."""


_NAMESPACE = 'NIKKETranslator/v1'
_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2
_ERROR_NOT_FOUND = 1168
_MAX_BLOB_BYTES = 2560
_ENDPOINT_ERROR = 'API base URL phải là HTTPS hợp lệ, không chứa tài khoản, query hoặc fragment.'
_READ_ERROR = 'Không đọc được khóa từ Windows Credential Manager cho tài khoản Windows này.'
_WRITE_ERROR = 'Không lưu được khóa vào Windows Credential Manager cho tài khoản Windows này.'
_VALUE_ERROR = 'Khóa trống, quá dài hoặc chứa ký tự không hợp lệ; chưa lưu vào Windows.'
_UNRESERVED = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~')


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ('Flags', wintypes.DWORD),
        ('Type', wintypes.DWORD),
        ('TargetName', wintypes.LPWSTR),
        ('Comment', wintypes.LPWSTR),
        ('LastWritten', wintypes.FILETIME),
        ('CredentialBlobSize', wintypes.DWORD),
        ('CredentialBlob', ctypes.POINTER(wintypes.BYTE)),
        ('Persist', wintypes.DWORD),
        ('AttributeCount', wintypes.DWORD),
        ('Attributes', ctypes.c_void_p),
        ('TargetAlias', wintypes.LPWSTR),
        ('UserName', wintypes.LPWSTR),
    ]


def normalize_endpoint(endpoint: str) -> str:
    """Canonical, conservative HTTPS scope shared by storage and request setup.

    Host case, IDNA, default port, unreserved escapes and a final slash are
    equivalent. Different ports or base paths remain separate. Ambiguous path
    traversal, separators, userinfo, queries and fragments are rejected rather
    than guessing which server URL a provider might normalize them into.
    """
    try:
        if (not isinstance(endpoint, str) or not endpoint
                or endpoint != endpoint.strip()
                or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in endpoint)
                or '\\' in endpoint or '?' in endpoint or '#' in endpoint):
            raise ValueError
        parsed = urlsplit(endpoint)
        if (parsed.scheme.lower() != 'https' or not parsed.hostname
                or parsed.username is not None or parsed.password is not None):
            raise ValueError
        host = parsed.hostname
        if ':' in host:
            if not re.fullmatch(r'\[[0-9A-Fa-f:.]+\](?::[0-9]+)?', parsed.netloc):
                raise ValueError
            host = '[' + ipaddress.IPv6Address(host).compressed + ']'
        else:
            host = host.encode('idna').decode('ascii').lower()
            # Reject URL delimiters outside normal DNS labels.
            if (len(host) > 253 or not all(
                    re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                    for label in host.split('.'))):
                raise ValueError
        port = parsed.port
        if parsed.netloc.endswith(':') or (port is not None and not 1 <= port <= 65535):
            raise ValueError
        authority = host if port in (None, 443) else f'{host}:{port}'
        path = parsed.path
        if re.search(r'%(?![0-9A-Fa-f]{2})', path) or any(ord(char) > 127 for char in path):
            raise ValueError

        def normalize_escape(match):
            char = chr(int(match.group(1), 16))
            if char in '/\\' or ord(char) < 32 or ord(char) == 127:
                raise ValueError
            return char if char in _UNRESERVED else '%' + match.group(1).upper()

        path = re.sub(r'%([0-9A-Fa-f]{2})', normalize_escape, path)
        if '//' in path or any(part in ('.', '..') for part in path.split('/')):
            raise ValueError
        # These characters are otherwise rewritten by an HTTP URL serializer.
        if any(char not in _UNRESERVED and char not in "/:@!$&'()*+,;=%" for char in path):
            raise ValueError
        return urlunsplit(('https', authority, path.rstrip('/'), '', ''))
    except (ValueError, TypeError, UnicodeError):
        raise CredentialError(_ENDPOINT_ERROR) from None


def _translation_target(endpoint: str) -> str:
    canonical = normalize_endpoint(endpoint)
    digest = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    return f'{_NAMESPACE}/translation/{digest}'


def _secret_target(name: str) -> str:
    if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', name):
        raise CredentialError('Tên khóa ứng dụng không hợp lệ.') from None
    return f'{_NAMESPACE}/secret/{name}'


def _encode_secret(value: str) -> bytes:
    if (not isinstance(value, str) or not value
            or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)):
        raise CredentialError(_VALUE_ERROR) from None
    try:
        blob = value.encode('utf-16-le')
    except UnicodeError:
        raise CredentialError(_VALUE_ERROR) from None
    if len(blob) > _MAX_BLOB_BYTES:
        raise CredentialError(_VALUE_ERROR) from None
    return blob


def _credential_api():
    if sys.platform != 'win32':
        raise CredentialError('Tính năng lưu khóa yêu cầu Windows Credential Manager.') from None
    try:
        api = ctypes.WinDLL('Advapi32.dll', use_last_error=True)
        api.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
        api.CredWriteW.restype = wintypes.BOOL
        api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                 ctypes.POINTER(ctypes.POINTER(_CREDENTIALW))]
        api.CredReadW.restype = wintypes.BOOL
        api.CredFree.argtypes = [ctypes.c_void_p]
        api.CredFree.restype = None
        return api
    except Exception:
        raise CredentialError('Không mở được Windows Credential Manager cho tài khoản Windows này.') from None


def _write_secret(target: str, value: str) -> None:
    blob = _encode_secret(value)
    buffer = (wintypes.BYTE * len(blob)).from_buffer_copy(blob)
    credential = _CREDENTIALW()
    credential.Type = _CRED_TYPE_GENERIC
    credential.TargetName = target
    credential.CredentialBlobSize = len(blob)
    credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(wintypes.BYTE))
    credential.Persist = _CRED_PERSIST_LOCAL_MACHINE
    credential.UserName = 'NIKKETranslator'
    try:
        api = _credential_api()
        if not api.CredWriteW(ctypes.byref(credential), 0):
            raise CredentialError(_WRITE_ERROR) from None
    except CredentialError:
        raise
    except Exception:
        raise CredentialError(_WRITE_ERROR) from None
    finally:
        ctypes.memset(buffer, 0, len(blob))


def _read_secret(target: str) -> str | None:
    credential = ctypes.POINTER(_CREDENTIALW)()
    api = _credential_api()
    try:
        if not api.CredReadW(target, _CRED_TYPE_GENERIC, 0, ctypes.byref(credential)):
            if ctypes.get_last_error() == _ERROR_NOT_FOUND:
                return None
            raise CredentialError(_READ_ERROR) from None
        if not credential:
            raise CredentialError(_READ_ERROR) from None
        stored = credential.contents
        size = stored.CredentialBlobSize
        if (stored.Type != _CRED_TYPE_GENERIC or stored.TargetName != target
                or not 0 < size <= _MAX_BLOB_BYTES or size % 2 or not stored.CredentialBlob):
            raise CredentialError(_READ_ERROR) from None
        value = ctypes.string_at(stored.CredentialBlob, size).decode('utf-16-le')
        _encode_secret(value)
        return value
    except Exception:
        raise CredentialError(_READ_ERROR) from None
    finally:
        if credential:
            # The buffer belongs to CredReadW and must only be freed by CredFree.
            try:
                api.CredFree(credential)
            except Exception:
                pass


def store_translation_key(endpoint: str, key: str) -> None:
    """Explicitly save a key for this exact normalized endpoint and Windows user."""
    _write_secret(_translation_target(endpoint), key)


def load_translation_key(endpoint: str) -> str | None:
    """Return only the key for this endpoint in the current user's Windows vault."""
    return _read_secret(_translation_target(endpoint))


def store_secret(name: str, value: str) -> None:
    """Store a named app secret separately from translation endpoint credentials."""
    _write_secret(_secret_target(name), value)


def load_secret(name: str) -> str | None:
    """Load a named app secret; missing credentials are represented by None."""
    return _read_secret(_secret_target(name))
