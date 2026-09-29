import logging
import redis
from fastapi import HTTPException
from app.core.redis import redis_client

logger = logging.getLogger(__name__)

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
    try:
        count = redis_client.eval(
            RATE_LIMIT_SCRIPT,
            1,
            key,
            window_seconds,
        )
    except (redis.exceptions.ConnectionError, redis.exceptions.RedisError, Exception) as e:
        logger.warning("Redis rate limiter unavailable (%s); bypassing rate limit check.", e)
        return

    if count > limit:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again later.",
        )