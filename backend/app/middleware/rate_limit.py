from fastapi import HTTPException
from app.core.redis import redis_client


RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])

if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end

return count
"""


def check_rate_limit(
    key: str,
    limit: int,
    window_seconds: int,
):
    count = redis_client.eval(
        RATE_LIMIT_SCRIPT,
        1,
        key,
        window_seconds,
    )

    if count > limit:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again later.",
        )