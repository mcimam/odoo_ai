# Part of ci_ai.

"""HTTPS base URL validation, safe HTTP helpers, and sanitized provider errors."""

from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import logging
import re
import socket
from typing import Callable, NoReturn
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

TRANSCRIPTION_MAX_BYTES = 25 * 1024 * 1024
HTTP_ERROR_LOG_MAX = 512
# Ollama default; keep loopback SSRF surface tiny for Settings admins.
ALLOWED_LOOPBACK_PORTS = frozenset({11434})

_SAFE_FORM_NAME = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')
_SAFE_FILENAME = re.compile(r'^[a-zA-Z0-9._-]{1,128}$')
_MIMETYPE_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9+.-]*/[a-zA-Z0-9][a-zA-Z0-9+.-]*$')
_SAFE_URL_PATH = re.compile(r'^(/[a-zA-Z0-9._-]+)+/?$')


class ProviderHttpError(UserError):
    """User-facing provider HTTP failure that still exposes the status code."""

    def __init__(self, message, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class _RejectRedirects(HTTPRedirectHandler):
    """Block redirects so allowlisted hosts cannot bounce off-allowlist."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: PLR0913
        raise URLError(
            'HTTP redirects are not allowed for CI AI provider requests '
            f'(status {code} -> {newurl}).'
        )


_HTTP_OPENER = build_opener(_RejectRedirects)


def is_allowed_openai_host(host: str) -> bool:
    """Allow first-party OpenAI, Azure OpenAI, and known compatible SaaS hosts."""
    host = (host or '').lower().rstrip('.')
    if host == 'api.openai.com':
        return True
    if host.endswith('.openai.azure.com'):
        return True
    # Imported lazily to avoid circular imports at module load in some test orders.
    from .openai_gateways import OPENAI_COMPAT_PUBLIC_HOSTS
    return host in OPENAI_COMPAT_PUBLIC_HOSTS


def is_allowed_openai_loopback_host(host: str) -> bool:
    """Local Ollama / loopback-only OpenAI-compatible hosts."""
    host = (host or '').lower().rstrip('.')
    return host in {'localhost', '127.0.0.1'}


def is_allowed_anthropic_host(host: str) -> bool:
    return (host or '').lower().rstrip('.') == 'api.anthropic.com'


def is_allowed_google_host(host: str) -> bool:
    host = (host or '').lower().rstrip('.')
    return host in {
        'generativelanguage.googleapis.com',
        'aiplatform.googleapis.com',
    }


def _is_public_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _is_loopback_ip(ip_str: str) -> bool:
    try:
        return ipaddress.ip_address(ip_str).is_loopback
    except ValueError:
        return False


def _hostname_resolves_to_public_ips(host: str) -> bool:
    """Reject hostnames that resolve only to private/link-local addresses."""
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    if not infos:
        return False
    for family, _type, _proto, _canon, sockaddr in infos:
        if family not in (socket.AF_INET, socket.AF_INET6):
            continue
        addr = sockaddr[0]
        if isinstance(addr, str) and addr.startswith('::ffff:'):
            addr = addr.rsplit(':', 1)[-1]
        if not _is_public_ip(addr):
            return False
    return True


def _hostname_resolves_to_loopback(host: str) -> bool:
    """Require every resolved address for a loopback hostname to be loopback."""
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    if not infos:
        return False
    saw_ip = False
    for family, _type, _proto, _canon, sockaddr in infos:
        if family not in (socket.AF_INET, socket.AF_INET6):
            continue
        addr = sockaddr[0]
        if isinstance(addr, str) and addr.startswith('::ffff:'):
            addr = addr.rsplit(':', 1)[-1]
        saw_ip = True
        if not _is_loopback_ip(addr):
            return False
    return saw_ip


def validate_https_base_url(
    raw_url: str,
    *,
    default_url: str,
    host_allowed: Callable[[str], bool],
    field_label: str,
    allow_path: bool = False,
    allow_loopback: bool = False,
) -> str:
    """Normalize and validate a provider base URL (SSRF guard).

    ``allow_path``: permit a simple path prefix (e.g. ``/openai``, ``/api``) for
    OpenAI-compatible gateways. The adapter still appends ``/v1/...``.

    ``allow_loopback``: permit ``localhost`` / ``127.0.0.1`` and HTTP (Ollama)
    on :attr:`ALLOWED_LOOPBACK_PORTS` only. Loopback hosts skip the public-DNS
    check but ``localhost`` must resolve to loopback addresses.
    """
    url = (raw_url or '').strip() or default_url
    parsed = urlparse(url)
    scheme = (parsed.scheme or '').lower()
    host = parsed.hostname
    if not host:
        raise ValidationError('%s is missing a hostname.' % field_label)

    host_l = host.lower().rstrip('.')
    is_loopback = allow_loopback and is_allowed_openai_loopback_host(host_l)

    if is_loopback:
        if scheme not in ('http', 'https'):
            raise ValidationError(
                '%s must use HTTP or HTTPS for local gateways (got %s).'
                % (field_label, scheme or 'none')
            )
    elif scheme != 'https':
        raise ValidationError(
            '%s must use HTTPS (got %s).' % (field_label, scheme or 'none')
        )

    if parsed.username or parsed.password:
        raise ValidationError('%s must not embed credentials in the URL.' % field_label)
    if parsed.query or parsed.fragment:
        raise ValidationError('%s must not include query or fragment.' % field_label)

    path = parsed.path or ''
    if path in ('', '/'):
        path = ''
    elif allow_path:
        if not _SAFE_URL_PATH.match(path):
            raise ValidationError(
                '%s path is not allowed: %s' % (field_label, path)
            )
        path = path.rstrip('/')
    else:
        raise ValidationError('%s must not include a path.' % field_label)

    if is_loopback:
        # Allow 127.0.0.1 literal; reject other IPs even when allow_loopback.
        try:
            ip = ipaddress.ip_address(host_l)
            if not ip.is_loopback:
                raise ValidationError(
                    '%s only allows localhost / 127.0.0.1 for local gateways.'
                    % field_label
                )
        except ValueError:
            if host_l != 'localhost':
                raise ValidationError(
                    '%s hostname is not allowed: %s' % (field_label, host)
                ) from None
            if not _hostname_resolves_to_loopback(host_l):
                raise ValidationError(
                    '%s hostname localhost must resolve to a loopback address.'
                    % field_label
                )
        port = parsed.port
        if port not in ALLOWED_LOOPBACK_PORTS:
            raise ValidationError(
                '%s local gateway must use port %s (got %s).'
                % (
                    field_label,
                    ', '.join(str(p) for p in sorted(ALLOWED_LOOPBACK_PORTS)),
                    port or 'default',
                )
            )
    else:
        try:
            ipaddress.ip_address(host)
            raise ValidationError(
                '%s must be a public hostname, not an IP address.' % field_label
            )
        except ValueError:
            pass

        if not host_allowed(host):
            raise ValidationError(
                '%s hostname is not allowed: %s' % (field_label, host)
            )
        if not _hostname_resolves_to_public_ips(host):
            raise ValidationError(
                '%s hostname resolves to a non-public address: %s' % (field_label, host)
            )
        port = parsed.port

    default_port = 80 if scheme == 'http' else 443
    if port and port != default_port:
        authority = f'{host_l}:{port}'
    else:
        authority = host_l
    return f'{scheme}://{authority}{path}'


def build_api_url(base_url: str, path: str) -> str:
    base = (base_url or '').rstrip('/')
    if not path.startswith('/'):
        path = '/' + path
    return base + path


def sanitize_multipart_field_name(name: str) -> str:
    if not _SAFE_FORM_NAME.match(name or ''):
        raise UserError('Invalid multipart form field name.')
    return name


def sanitize_multipart_field_value(value: str) -> str:
    text = (value or '').replace('\r', '').replace('\n', '')
    if len(text) > 4096:
        raise UserError('Multipart form value is too long.')
    return text


def sanitize_upload_filename(filename: str) -> str:
    name = (filename or 'upload.bin').split('/')[-1].split('\\')[-1]
    if not _SAFE_FILENAME.match(name):
        name = 'upload.bin'
    return name


def sanitize_mimetype(mimetype: str | None) -> str:
    mime = (mimetype or 'application/octet-stream').split(';')[0].strip().lower()
    if not _MIMETYPE_RE.match(mime):
        return 'application/octet-stream'
    return mime


def decode_transcription_audio(audio_base64: str, *, max_bytes: int = TRANSCRIPTION_MAX_BYTES) -> bytes:
    if not audio_base64:
        raise UserError('No audio data provided for transcription.')
    try:
        # Browser data-URLs sometimes omit padding or include whitespace.
        payload = ''.join((audio_base64 or '').split())
        padding = (-len(payload)) % 4
        if padding:
            payload += '=' * padding
        audio_bytes = base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError) as err:
        raise UserError('Invalid base64 audio payload for transcription.') from err
    if not audio_bytes:
        raise UserError('Empty audio payload for transcription.')
    if len(audio_bytes) > max_bytes:
        raise UserError('Audio file is too large for transcription (max 25 MB).')
    return audio_bytes


def _truncate_for_log(text: str, *, limit: int = HTTP_ERROR_LOG_MAX) -> str:
    cleaned = (text or '').replace('\r', ' ').replace('\n', ' ').strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + '…'


def raise_sanitized_http_error(provider_label: str, err: Exception, method: str, url: str) -> NoReturn:
    if isinstance(err, HTTPError):
        detail = err.read().decode('utf-8', errors='replace')
        _logger.error(
            '%s HTTP %s %s: %s',
            provider_label, method, url, _truncate_for_log(detail),
        )
        raise ProviderHttpError(
            '%s API request failed (HTTP %s). Please try again later.'
            % (provider_label, err.code),
            status_code=err.code,
        ) from err
    if isinstance(err, URLError):
        _logger.error('%s network error %s %s: %s', provider_label, method, url, err.reason)
        raise UserError(
            '%s API is unreachable. Please try again later.' % provider_label
        ) from err
    if isinstance(err, TimeoutError):
        _logger.error('%s request timed out %s %s', provider_label, method, url)
        raise UserError(
            '%s API request timed out. Please try again later.' % provider_label
        ) from err
    raise err


def http_json(
    provider_label: str,
    method: str,
    url: str,
    headers: dict,
    body: dict | None = None,
    timeout: int = 120,
) -> dict:
    body_keys = sorted((body or {}).keys())
    _logger.debug(
        'CI AI HTTP %s %s %s body_keys=%s timeout=%s',
        provider_label, method, url, body_keys, timeout,
    )
    data = None if body is None else json.dumps(body).encode('utf-8')
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with _HTTP_OPENER.open(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8')
            payload = json.loads(raw) if raw else {}
            _logger.debug(
                'CI AI HTTP %s %s %s -> ok bytes=%s',
                provider_label, method, url, len(raw or ''),
            )
            return payload
    except (HTTPError, URLError, TimeoutError) as err:
        raise_sanitized_http_error(provider_label, err, method, url)


def http_multipart_post(
    provider_label: str,
    url: str,
    headers: dict,
    fields: dict[str, str],
    files: list[tuple[str, str, str, bytes]],
    *,
    boundary: str,
    timeout: int = 120,
) -> bytes:
    file_meta = [
        (field, filename, content_type, len(data or b''))
        for field, filename, content_type, data in (files or [])
    ]
    _logger.debug(
        'CI AI HTTP %s POST multipart %s fields=%s files=%s timeout=%s',
        provider_label, url, sorted((fields or {}).keys()), file_meta, timeout,
    )
    body = bytearray()
    for name, value in (fields or {}).items():
        safe_name = sanitize_multipart_field_name(name)
        safe_value = sanitize_multipart_field_value(value)
        body.extend(
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="{safe_name}"\r\n\r\n'
            f'{safe_value}\r\n'.encode()
        )
    for field, filename, content_type, data in files or []:
        safe_field = sanitize_multipart_field_name(field)
        safe_filename = sanitize_upload_filename(filename)
        safe_type = sanitize_mimetype(content_type)
        body.extend(
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="{safe_field}"; '
            f'filename="{safe_filename}"\r\n'
            f'Content-Type: {safe_type}\r\n\r\n'.encode()
        )
        body.extend(data)
        body.extend(b'\r\n')
    body.extend(f'--{boundary}--\r\n'.encode())

    req_headers = {
        **headers,
        'content-type': f'multipart/form-data; boundary={boundary}',
    }
    req = Request(url, data=bytes(body), headers=req_headers, method='POST')
    try:
        with _HTTP_OPENER.open(req, timeout=timeout) as resp:
            raw = resp.read()
            _logger.debug(
                'CI AI HTTP %s POST multipart %s -> ok bytes=%s',
                provider_label, url, len(raw or b''),
            )
            return raw
    except (HTTPError, URLError, TimeoutError) as err:
        raise_sanitized_http_error(provider_label, err, 'POST', url)
