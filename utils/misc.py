import ipaddress
import urllib
import discord
import asyncio
import functools
import os
from asyncio.subprocess import PIPE
from typing import Awaitable, Callable, Tuple, Union


def parse_content_disposition(header_value: str):
    """Parses the Content-Disposition header using basic logic."""
    parts = header_value.split(";")
    params = {}

    for part in parts[1:]:
        if '=' in part:
            key, value = part.strip().split("=", 1)
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            params[key.lower()] = value

    return parts[0].strip().lower(), params


async def get_filename_from_header(session, url: str):
    async with session.head(url) as resp:
        if resp.status != 200:
            return None

        cd = resp.headers.get('Content-Disposition', '')
        filename = None

        if cd:
            _, params = parse_content_disposition(cd)

            if 'filename*' in params:
                # RFC 5987 encoding: filename*=utf-8''encoded_filename
                _, _, encoded_filename = params['filename*'].partition("''")
                filename = urllib.parse.unquote(encoded_filename)
            elif 'filename' in params:
                filename = params['filename']

        if not filename:
            parsed_url = urllib.parse.urlparse(url)
            filename = os.path.basename(parsed_url.path)

        return filename


def check_os() -> Tuple[str, str]:
    if os.name == "posix":  # Unix-like system
        shell = "/bin/bash"
        ext = ""
    elif os.name == 'nt':  # Windows
        shell = "powershell.exe"
        ext = ".exe"
    else:
        raise OSError("Unsupported operating system")
    return shell, ext


SHELL, _ = check_os()


async def run_process_shell(cmd: str, timeout: float = 90.0) -> Tuple[str, str]:
    if os.name == 'posix':
        sequence = f"{SHELL} -c '{cmd}'"
        proc = await asyncio.create_subprocess_shell(sequence, stdout=PIPE, stderr=PIPE)
    else:  # Windows
        proc = await asyncio.create_subprocess_exec(SHELL, '-Command', cmd, stdout=PIPE, stderr=PIPE)

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as e:
        proc.kill()
        await proc.wait()
        raise RuntimeError("Process timed out") from e
    else:
        return stdout.decode(), stderr.decode()


async def run_process_exec(
        program: str, *args: str, timeout: float = 90.0
) -> Tuple[str, str]:
    proc = await asyncio.create_subprocess_exec(
        program, *args, stdout=PIPE, stderr=PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as e:
        proc.kill()
        await proc.wait()
        raise RuntimeError("Process timed out") from e
    else:
        return stdout.decode(), stderr.decode()


def executor(func: Callable):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        fn = functools.partial(func, *args, **kwargs)
        return await loop.run_in_executor(None, fn)

    return wrapper


async def maybe_coroutine(func: Union[Awaitable, Callable], *args, **kwargs):
    if asyncio.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    else:
        return func(*args, **kwargs)


def rating() -> list:
    return [
        discord.SelectOption(label="Rating: ★☆☆☆☆", value="0"),
        discord.SelectOption(label="Rating: ★★☆☆☆", value="1"),
        discord.SelectOption(label="Rating: ★★★☆☆", value="2"),
        discord.SelectOption(label="Rating: ★★★★☆", value="3"),
        discord.SelectOption(label="Rating: ★★★★★", value="4"),
    ]


def ip_matches(ip: str, target: str) -> bool:
    ip = ip.strip()
    target = target.strip()

    if ip == target:
        return True

    if "-" in target:
        start_ip, end_ip = target.split("-", 1)
        try:
            start = int(ipaddress.IPv4Address(start_ip.strip()))
            end = int(ipaddress.IPv4Address(end_ip.strip()))
            current = int(ipaddress.IPv4Address(ip))
            return start <= current <= end
        except ipaddress.AddressValueError:
            return False

    return False
