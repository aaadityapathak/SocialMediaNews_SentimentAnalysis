"""Small Server-Sent Events decoder shared by Mastodon stream consumers."""

from collections.abc import AsyncIterator


async def iter_events(
    lines: AsyncIterator[str],
) -> AsyncIterator[tuple[str, str] | None]:
    """Decode blank-line-delimited events, comments and multiline data fields."""
    event = "message"
    data = []
    async for line in lines:
        if not line:
            if data:
                yield event, "\n".join(data)
            event, data = "message", []
            continue
        if line.startswith(":"):
            yield None
            continue
        key, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if key == "event":
            event = value
        elif key == "data":
            data.append(value)
    if data:
        yield event, "\n".join(data)
