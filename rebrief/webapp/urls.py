from __future__ import annotations

from urllib.parse import urlparse

from rebrief.core.remote import RemoteTarget, parse_git_url, parse_github_shorthand

ALLOWED_HOSTS = frozenset(
    {
        "github.com",
        "www.github.com",
        "gitlab.com",
        "www.gitlab.com",
        "bitbucket.org",
        "www.bitbucket.org",
    }
)

INVALID_URL_MESSAGE = (
    "URL must be a public GitHub, GitLab, or Bitbucket HTTPS repository "
    "(or GitHub owner/repo shorthand)."
)

_HOST_ALIASES = {
    "www.github.com": "github.com",
    "www.gitlab.com": "gitlab.com",
    "www.bitbucket.org": "bitbucket.org",
}


class PublicUrlError(ValueError):
    """Raised when a web scan target is not a public allowlisted HTTPS repo."""


def resolve_public_remote(value: str) -> RemoteTarget:
    """Parse and allowlist a public HTTPS GitHub/GitLab/Bitbucket target."""
    stripped = value.strip()
    if not stripped:
        raise PublicUrlError(INVALID_URL_MESSAGE)
    lowered = stripped.lower()
    if lowered.startswith("git@") or lowered.startswith("ssh://"):
        raise PublicUrlError(INVALID_URL_MESSAGE)

    target = parse_git_url(stripped)
    if target is None:
        target = parse_github_shorthand(stripped)
    if target is None:
        raise PublicUrlError(INVALID_URL_MESSAGE)
    if target.clone_url.startswith("git@") or target.clone_url.startswith("ssh://"):
        raise PublicUrlError(INVALID_URL_MESSAGE)

    parsed = urlparse(target.clone_url)
    if parsed.scheme != "https":
        raise PublicUrlError(INVALID_URL_MESSAGE)
    if parsed.username or parsed.password:
        raise PublicUrlError(INVALID_URL_MESSAGE)

    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise PublicUrlError(INVALID_URL_MESSAGE)
    if _is_ip_host(host):
        raise PublicUrlError(INVALID_URL_MESSAGE)

    canonical_host = _HOST_ALIASES.get(host, host)
    clone_url = f"https://{canonical_host}/{target.display_name}"
    return RemoteTarget(clone_url=clone_url, display_name=target.display_name)


def _is_ip_host(host: str) -> bool:
    if host.startswith("[") and host.endswith("]"):
        return True
    parts = host.split(".")
    if len(parts) == 4 and all(part.isdigit() for part in parts):
        return True
    return False
