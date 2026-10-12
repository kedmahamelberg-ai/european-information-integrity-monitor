"""Service-role-only Supabase RPC client; no public access to raw observations."""

import copy
import json, os, time, urllib.request, urllib.error
from .core import digest

WRITE_CHUNK_SIZE = 200


class Store:
    def __init__(self, url=None, key=None, public_pipeline_only=False):
        self.url = (url or os.environ["SUPABASE_URL"]).rstrip("/")
        self.key = (
            key
            or os.environ.get("SUPABASE_SECRET_KEY")
            or os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        )
        if not self.url.startswith("https://"):
            raise ValueError("HTTPS Supabase URL required")
        # A workflow repeatedly asks for the same immutable batch tables while
        # moving through collection, classification and publication.  Keep one
        # process-local copy so those reads do not repeatedly transfer multi-MB
        # JSON payloads from Supabase.  Writes below update any populated cache.
        self._read_cache = {}
        self.public_pipeline_only = public_pipeline_only

    def rpc(self, name, args):
        headers = {"apikey": self.key, "Content-Type": "application/json"}
        if self.key.startswith("eyJ"):
            headers["Authorization"] = "Bearer " + self.key
        req = urllib.request.Request(
            self.url + "/rest/v1/rpc/" + name,
            data=json.dumps(args, ensure_ascii=False).encode(),
            headers=headers,
        )
        # Reads and immutable envelope writes are safe to retry.  eiim_write is
        # atomic and uses immutable IDs with ON CONFLICT DO NOTHING, so repeating
        # the exact request after a lost response cannot duplicate observations.
        # Never print a response body or authorization headers.
        attempts = 3 if name in {
            "eiim_read",
            "eiim_read_pipeline_public",
            "eiim_progress",
            "eiim_write",
        } else 1
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(req, timeout=60) as response:
                    return json.load(response)
            except urllib.error.HTTPError as e:
                if e.code in {429, 500, 502, 503, 504} and attempt + 1 < attempts:
                    e.close()
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(
                    f"Supabase RPC {name} failed (HTTP {e.code}); no source data or credentials logged"
                ) from None
            except (urllib.error.URLError, TimeoutError):
                if attempt + 1 < attempts:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(
                    f"Supabase RPC {name} failed (network unavailable); no source data or credentials logged"
                ) from None

    def batch(self, window, config_hash):
        result = self.rpc(
            "eiim_batch",
            {"p_id": window["id"], "p_payload": window, "p_config_hash": config_hash},
        )
        self._read_cache.pop(("weekly_batches", None), None)
        self._read_cache.pop(("weekly_batches", window["id"]), None)
        return result

    def read(self, table, batch=None):
        key = (table, batch)
        if key not in self._read_cache:
            if table == "pipeline_runs" and self.public_pipeline_only:
                self._read_cache[key] = self.rpc(
                    "eiim_read_pipeline_public", {"p_batch": batch}
                )
            else:
                self._read_cache[key] = self.rpc(
                    "eiim_read", {"p_table": table, "p_batch": batch}
                )
        return copy.deepcopy(self._read_cache[key])

    def write(self, batch, rows, stage=None):
        # Discovery can produce thousands of raw API envelopes.  Sending all of
        # them in one RPC can exceed the database statement/client timeout.  A
        # stage is recorded only with the final chunk, after every prior chunk
        # has been accepted.  Empty stage-only writes remain supported.
        chunks = [rows[i : i + WRITE_CHUNK_SIZE] for i in range(0, len(rows), WRITE_CHUNK_SIZE)]
        if not chunks:
            chunks = [[]]
        accepted = 0
        result = None
        for index, chunk in enumerate(chunks):
            chunk_stage = stage if index == len(chunks) - 1 else None
            result = self.rpc(
                "eiim_write",
                {"p_batch": batch, "p_stage": chunk_stage, "p_rows": chunk},
            )
            accepted += int(result.get("accepted", 0))
        result = dict(result or {})
        result["accepted"] = accepted
        result["stage"] = stage
        for entry in rows:
            table = entry["table"]
            row = copy.deepcopy(entry["record"])
            for key in ((table, batch), (table, None)):
                cached = self._read_cache.get(key)
                if cached is None:
                    continue
                existing = next((r for r in cached if r["id"] == row["id"]), None)
                if existing is None:
                    cached.append(copy.deepcopy(row))
                elif existing.get("payload_hash") != row.get("payload_hash"):
                    # The database rejects this immutable conflict.  This is a
                    # defensive guard for nonstandard RPC test doubles.
                    self._read_cache.pop(key, None)
        if stage is not None:
            self._read_cache.pop(("weekly_batches", None), None)
            self._read_cache.pop(("weekly_batches", batch), None)
        return result

    def progress(self):
        return self.rpc("eiim_progress", {})

    def purge(self, days=30):
        result = self.rpc("eiim_purge", {"p_days": days})
        self._read_cache.clear()
        return result


def record(table, batch, id, payload, video_id=None):
    return {
        "table": table,
        "record": {
            "id": str(id),
            "batch_id": batch,
            "video_id": video_id,
            "payload": payload,
            "payload_hash": digest(payload),
        },
    }


class ReadSnapshot:
    """Explicit, run-scoped read cache for immutable calibration inputs only."""

    def __init__(self, store):
        self.store = store
        self.rows = {}

    def read(self, table, batch=None):
        key = (table, batch)
        if key not in self.rows:
            self.rows[key] = self.store.read(table, batch)
        return copy.deepcopy(self.rows[key])


class MemoryStore:
    """Explicit test double. Production CLI never selects this adapter."""

    def progress(self):
        return {"batches": [], "coverage": []}

    def __init__(self):
        self.tables = {}
        self.batches = {}

    def batch(self, window, config_hash):
        b = self.batches.setdefault(
            window["id"],
            {
                "id": window["id"],
                "payload": window,
                "config_hash": config_hash,
                "status": "started",
                "completed_stages": [],
            },
        )
        if b["config_hash"] != config_hash:
            raise ValueError("Configuration differs")
        return b

    def read(self, table, batch=None):
        rows = (
            list(self.batches.values())
            if table == "weekly_batches"
            else list(self.tables.get(table, {}).values())
        )
        return [
            r
            for r in rows
            if batch is None
            or (r["id"] if table == "weekly_batches" else r["batch_id"]) == batch
        ]

    def write(self, batch, rows, stage=None):
        import copy

        updated = copy.deepcopy(self.tables)
        for row in rows:
            table = row["table"]
            r = row["record"]
            dst = updated.setdefault(table, {})
            if r["batch_id"] != batch:
                raise ValueError("Wrong batch")
            if r["id"] in dst and dst[r["id"]]["payload_hash"] != r["payload_hash"]:
                raise ValueError("Immutable conflict")
            dst[r["id"]] = r
        self.tables = updated
        if stage:
            b = self.batches[batch]
            b["status"] = stage
            if (
                stage not in ["failed", "pending_budget", "awaiting_validation"]
                and stage not in b["completed_stages"]
            ):
                b["completed_stages"].append(stage)
        return {"accepted": len(rows)}
