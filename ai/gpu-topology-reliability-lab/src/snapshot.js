import { createHash } from "node:crypto";
import { DomainError } from "./errors.js";

const canonical = (value) => JSON.stringify(value);
export function createSnapshot(cluster, events) {
  const body = { schemaVersion: 1, cluster, events };
  return { body, sha256: createHash("sha256").update(canonical(body)).digest("hex") };
}
export function restoreSnapshot(snapshot) {
  const actual = createHash("sha256").update(canonical(snapshot?.body)).digest("hex");
  if (!snapshot?.body || snapshot.sha256 !== actual || snapshot.body.schemaVersion !== 1) throw new DomainError("CORRUPT_SNAPSHOT", "snapshot integrity validation failed");
  return structuredClone(snapshot.body);
}
