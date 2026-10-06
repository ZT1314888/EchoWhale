"""固定窗口限流的原子计数封装（redis-py Script）。

INCR 与"首次 EXPIRE"拆成两条命令时，进程在两命令之间崩溃会留下无 TTL 的键：
计数永不过期、窗口永不翻新，限流键从此变成永久配额黑洞。Lua 脚本把两步合并
成单次 EVAL 原子执行，键的生命周期与计数同生共死。RedisLLMRateLimiter 与
RedisAuthRateLimiter 共用同一脚本常量，键构造（llm:rate:* / auth:rate:*）留在
各自限流器里——server-attested identity 的键来源语义不受脚本影响。
"""

from __future__ import annotations

# INCR + 首次 EXPIRE：仅当计数值为 1（本窗口第一次写入）时设置 TTL，
# 窗口内的续增不会重置过期时间；返回值为当前窗口累计次数。
FIXED_WINDOW_LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


class FixedWindowCounter:
    """INCR + 首次 EXPIRE 的原子封装（redis-py Script：EVALSHA 优先、NOSCRIPT 回退 EVAL）。"""

    def __init__(self, client) -> None:
        self._script = client.register_script(FIXED_WINDOW_LUA)

    def increment(self, key: str, window_seconds: int) -> int:
        """原子递增并返回当前窗口计数；首次递增时原子设置窗口 TTL。"""
        return int(self._script(keys=[key], args=[window_seconds]))
