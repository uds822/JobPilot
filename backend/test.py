from app.core.redis import redis_client

redis_client.set("fastapi_test", "hello", ex=30)

print(redis_client.get("fastapi_test"))
print(redis_client.ttl("fastapi_test"))