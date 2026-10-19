"""Keep invitation tokens and OIDC callback codes out of access logs."""

import logging


class AuthQueryFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        client, method, url, version, status = record.args
        if url.startswith('/auth/'):
            record.args = (client, method, url.partition('?')[0], version, status)
        return True


AUTH_ACCESS_FILTER = AuthQueryFilter()
