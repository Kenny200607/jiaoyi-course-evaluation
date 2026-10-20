"""Line-buffered redaction shared by console and log output."""
import re
from urllib.parse import urlsplit, urlunsplit


def redact(text: str, secrets=()) -> str:
    for secret in sorted((str(s) for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, '[redacted]')

    def safe_url(match):
        raw = match.group(0)
        try:
            parts = urlsplit(raw)
            host = parts.hostname or ''
            if parts.port:
                host += ':' + str(parts.port)
            return urlunsplit((parts.scheme, host, parts.path, '[redacted]' if parts.query else '', ''))
        except ValueError:
            return '[redacted-url]'

    text = re.sub(r'https?://[^\s<>"\']+', safe_url, text)
    fields = r'password|passwd|token|ticket|cookie|authorization|session|recordid|studentid|statekey|username|user_id|webvpn_username|webvpn_password'
    pattern = r'''(?i)(["']?\b(?:''' + fields + r''')\b["']?\s*[:=]\s*)(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,;}]+)'''
    return re.sub(pattern, lambda match: match.group(1) + '"[redacted]"', text)


class RedactingStream:
    def __init__(self, target, secrets=()):
        self.target = target
        self.secrets = tuple(secrets)
        self.pending = ''

    def write(self, text):
        self.pending += text
        while '\n' in self.pending:
            line, self.pending = self.pending.split('\n', 1)
            self.target.write(redact(line, self.secrets) + '\n')
        return len(text)

    def flush(self):
        if self.pending:
            self.target.write(redact(self.pending, self.secrets))
            self.pending = ''
        self.target.flush()

    def isatty(self):
        return bool(getattr(self.target, 'isatty', lambda: False)())

    @property
    def encoding(self):
        return getattr(self.target, 'encoding', 'utf-8')
