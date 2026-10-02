"""Docker CLI compatible memory accounting for cgroup v1 and v2."""
def memory_usage(memory):
    usage = memory.get("usage", 0) or 0
    cache = memory.get("stats", {}) or {}
    inactive = cache.get("total_inactive_file", cache.get("inactive_file", 0)) or 0
    return max(0, usage - inactive) if inactive < usage else usage
