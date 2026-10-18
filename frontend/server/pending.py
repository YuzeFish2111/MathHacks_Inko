"""Recent results kept in memory so they can be saved after the fact (a guest who signs
in right after a scan, or "Use this photo anyway" on a tilted photo)."""
import time
from collections import OrderedDict


class PendingResults:
    def __init__(self, limit: int = 200, ttl: int = 3600):
        self.items: OrderedDict[str, dict] = OrderedDict()
        self.limit, self.ttl = limit, ttl

    def put(self, result_id: str, entry: dict) -> None:
        self.items[result_id] = {**entry, "_t": time.time()}
        while len(self.items) > self.limit:
            self.items.popitem(last=False)

    def get(self, result_id: str) -> dict | None:
        entry = self.items.get(result_id)
        if entry and time.time() - entry["_t"] < self.ttl:
            return entry
        return None


pending = PendingResults()
