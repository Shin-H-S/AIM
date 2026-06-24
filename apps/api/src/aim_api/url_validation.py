import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network
from urllib.parse import urlparse


class UrlValidationError(Exception):
    """Raised when a user-provided service URL is unsafe to store or scan."""


@dataclass(frozen=True)
class ResolvedAddress:
    host: str
    ip: str


AddressResolver = Callable[[str, int | None], Iterable[ResolvedAddress]]

CLOUD_METADATA_IPS = frozenset(
    {
        ip_address("169.254.169.254"),
        ip_address("169.254.170.2"),
        ip_address("100.100.100.200"),
    }
)
CLOUD_METADATA_NETWORKS = tuple(
    ip_network(value)
    for value in (
        "169.254.169.254/32",
        "169.254.170.2/32",
        "100.100.100.200/32",
    )
)
CLOUD_METADATA_HOSTS = frozenset(
    {
        "metadata",
        "metadata.google.internal",
        "metadata.google.internal.",
        "instance-data",
        "instance-data.ec2.internal",
        "169.254.169.254",
        "169.254.170.2",
        "100.100.100.200",
    }
)


def validate_service_url(
    raw_url: str,
    *,
    resolver: AddressResolver | None = None,
) -> None:
    parsed_url = urlparse(raw_url)
    scheme = parsed_url.scheme.lower()

    if scheme not in {"http", "https"}:
        raise UrlValidationError("Only HTTP and HTTPS service URLs are allowed.")

    if parsed_url.username is not None or parsed_url.password is not None:
        raise UrlValidationError("Service URLs must not include credentials.")

    hostname = parsed_url.hostname
    if hostname is None:
        raise UrlValidationError("Service URL must include a hostname.")

    normalized_hostname = normalize_hostname(hostname)
    if is_blocked_hostname(normalized_hostname):
        raise UrlValidationError("Service URL host is not allowed.")

    try:
        port = parsed_url.port
    except ValueError as exc:
        raise UrlValidationError("Service URL port is invalid.") from exc

    direct_ip = parse_ip_address(normalized_hostname)
    if direct_ip is not None:
        validate_public_ip(str(direct_ip))
        return

    resolve_addresses = resolver or resolve_host_addresses
    addresses = list(resolve_addresses(normalized_hostname, port))
    if not addresses:
        raise UrlValidationError("Service URL host could not be resolved.")

    for address in addresses:
        validate_public_ip(address.ip)


def normalize_hostname(hostname: str) -> str:
    return hostname.strip().lower().rstrip(".")


def is_blocked_hostname(hostname: str) -> bool:
    labels = hostname.split(".")
    if hostname in CLOUD_METADATA_HOSTS:
        return True

    return hostname == "localhost" or labels[-1] == "localhost"


def parse_ip_address(value: str) -> IPv4Address | IPv6Address | None:
    try:
        return ip_address(value)
    except ValueError:
        return None


def validate_public_ip(value: str) -> None:
    try:
        address = ip_address(value)
    except ValueError as exc:
        raise UrlValidationError("Service URL resolved to an invalid address.") from exc

    if address in CLOUD_METADATA_IPS:
        raise UrlValidationError("Service URL resolved to a cloud metadata address.")

    if any(address in network for network in CLOUD_METADATA_NETWORKS):
        raise UrlValidationError("Service URL resolved to a cloud metadata address.")

    if (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise UrlValidationError("Service URL resolved to a non-public address.")

    if not address.is_global:
        raise UrlValidationError("Service URL resolved to a non-public address.")


def resolve_host_addresses(hostname: str, port: int | None) -> list[ResolvedAddress]:
    try:
        results = socket.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise UrlValidationError("Service URL host could not be resolved.") from exc

    resolved_addresses: list[ResolvedAddress] = []
    seen_ips: set[str] = set()
    for result in results:
        sockaddr = result[4]
        ip = str(sockaddr[0])
        if ip in seen_ips:
            continue

        seen_ips.add(ip)
        resolved_addresses.append(ResolvedAddress(host=hostname, ip=ip))

    return resolved_addresses
