"""Service-role-only Supabase RPC client; no public access to raw observations."""

import json, os, urllib.request, urllib.error
from .core import digest


class Store:
    def __init__(self, url=None, key=None):
        self.url = (url or os.environ["SUPABASE_URL"]).rstrip("/")
        self.key = (
            key
            or os.environ.get("SUPABASE_SECRET_KEY")
            or os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        )
        if not self.url.startswith("https://"):
            raise ValueError("HTTPS Supabase URL required")

    def rpc(self, name, args):
        headers = {"apikey": self.key, "Content-Type": "application/json"}
        if self.key.startswith("eyJ"):
            headers["Authorization"] = "Bearer " + self.key
        req = urllib.request.Request(
            self.url + "/rest/v1/rpc/" + name,
            data=json.dumps(args, ensure_ascii=False).encode(),
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as e:
            raise RuntimeError(
                f"Supabase RPC {name} failed (HTTP {e.code}); no source data or credentials logged"
            ) from None

    def batch(self, window, config_hash):
        return self.rpc(
            "eiim_batch",
            {"p_id": window["id"], "p_payload": window, "p_config_hash": config_hash},
        )

    def read(self, table, batch=None):
        return self.rpc("eiim_read", {"p_table": table, "p_batch": batch})

    def write(self, batch, rows, stage=None):
        return self.rpc(
            "eiim_write", {"p_batch": batch, "p_stage": stage, "p_rows": rows}
        )

    def purge(self, days=30):
        return self.rpc("eiim_purge", {"p_days": days})


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


class MemoryStore:
    """Explicit test double. Production CLI never selects this adapter."""

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
