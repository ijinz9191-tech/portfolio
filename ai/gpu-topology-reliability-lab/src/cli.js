import { normalizeCluster, summarizeTopology } from "./topology.js";
import { scheduleWorkload } from "./scheduler.js";
import { diagnose } from "./diagnostics.js";
import { RemediationLedger, verifyLedger } from "./remediation.js";
import { sampleCluster } from "./fixtures.js";

const cluster = normalizeCluster(sampleCluster());
const placement = scheduleWorkload(cluster, { id: "llm-train-42", gpuCount: 2, minMemoryGb: 64, networkGbps: 100, preferredFabric: "rocev2" });
const diagnosis = diagnose({ id: "sample-42", gpuUtilization: 0.31, cpuUtilization: 0.9, numaRemoteRatio: 0.38, pcieReplayRate: 0.03, nicRxGbps: 180, nicCapacityGbps: 200, rdmaErrors: 2 });
const ledger = new RemediationLedger();
ledger.propose({ incidentId: "inc-42", action: "REPIN_WORKLOAD", target: "llm-train-42", reason: diagnosis.causes[0].code });
ledger.approve("inc-42", "synthetic-reviewer");
ledger.execute("inc-42", ledger.planHash("inc-42"));
ledger.verify("inc-42", true, { numaRemoteRatio: 0.04 });
console.log(JSON.stringify({ topology: summarizeTopology(cluster), placement, diagnosis, auditValid: verifyLedger(ledger.events), events: ledger.events }, null, 2));
