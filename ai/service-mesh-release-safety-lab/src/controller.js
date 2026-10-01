import { EvidenceLedger } from "./ledger.js";

const DEFAULT_STEPS = [5, 25, 50, 100];

function assertNumber(name, value, min, max) {
  if (!Number.isFinite(value) || value < min || value > max)
    throw new Error(`${name} must be between ${min} and ${max}`);
}

export class ReleaseController {
  constructor({
    clusters,
    errorBudgetRemaining = 1,
    minErrorBudget = 0.25,
    approvalToken,
    steps = DEFAULT_STEPS,
    requireClusterSamples = false,
    maxSampleAgeMs = 60000,
    clock = () => Date.now(),
  } = {}) {
    if (
      !Array.isArray(clusters) ||
      clusters.length < 2 ||
      new Set(clusters).size !== clusters.length
    )
      throw new Error("at least two unique clusters are required");
    assertNumber("errorBudgetRemaining", errorBudgetRemaining, 0, 1);
    assertNumber("minErrorBudget", minErrorBudget, 0, 1);
    if (!approvalToken) throw new Error("approvalToken is required");
    if (typeof requireClusterSamples !== "boolean")
      throw new Error("requireClusterSamples must be boolean");
    if (!Number.isSafeInteger(maxSampleAgeMs) || maxSampleAgeMs <= 0)
      throw new Error("maxSampleAgeMs must be positive");
    if (typeof clock !== "function")
      throw new Error("clock must be a function");
    if (
      !Array.isArray(steps) ||
      !steps.length ||
      steps.at(-1) !== 100 ||
      steps.some(
        (value, index) =>
          !Number.isFinite(value) ||
          value <= 0 ||
          value > 100 ||
          (index && value <= steps[index - 1]),
      )
    ) {
      throw new Error("steps must be ascending and end at 100");
    }
    this.clusters = [...clusters];
    this.errorBudgetRemaining = errorBudgetRemaining;
    this.minErrorBudget = minErrorBudget;
    this.approvalToken = approvalToken;
    this.steps = [...steps];
    this.requireClusterSamples = requireClusterSamples;
    this.maxSampleAgeMs = maxSampleAgeMs;
    this.clock = clock;
    this.ledger = new EvidenceLedger();
    this.releases = new Map();
  }

  start({ releaseId, service, version, requester, approvalToken }) {
    if (!releaseId || !service || !version || !requester)
      throw new Error("release identity is incomplete");
    if (approvalToken !== this.approvalToken)
      throw new Error("release approval rejected");
    if (this.releases.has(releaseId))
      throw new Error("releaseId already exists");
    if (this.errorBudgetRemaining < this.minErrorBudget)
      throw new Error("error budget gate rejected release");
    const release = {
      releaseId,
      service,
      version,
      requester,
      status: "RUNNING",
      stepIndex: -1,
      trafficPercent: 0,
      clusters: Object.fromEntries(
        this.clusters.map((cluster) => [
          cluster,
          { trafficPercent: 0, state: "STABLE" },
        ]),
      ),
      rollbackReason: null,
      lastObservedAt: {},
    };
    this.releases.set(releaseId, release);
    this.ledger.append("RELEASE_STARTED", {
      releaseId,
      service,
      version,
      requester,
    });
    return structuredClone(release);
  }

  observe(releaseId, sample) {
    const release = this.#getRunning(releaseId);
    const { normalized, breach } = this.#validateObservation(sample);
    // 같은 관측을 다시 제출해 여러 단계로 승격하는 것을 방지한다.
    for (const [cluster, reading] of Object.entries(
      normalized.clusterSamples ?? {},
    )) {
      if (
        release.lastObservedAt[cluster] !== undefined &&
        reading.observedAt <= release.lastObservedAt[cluster]
      ) {
        throw new Error(
          `${cluster} telemetry must advance after the previous observation`,
        );
      }
    }
    const nextStep = this.steps[release.stepIndex + 1];
    if (nextStep === undefined) throw new Error("release already completed");
    this.ledger.append("METRICS_OBSERVED", {
      releaseId,
      intendedTrafficPercent: nextStep,
      ...normalized,
      breach,
    });
    for (const [cluster, reading] of Object.entries(
      normalized.clusterSamples ?? {},
    ))
      release.lastObservedAt[cluster] = reading.observedAt;
    if (breach) return this.rollback(releaseId, breach);
    release.stepIndex += 1;
    release.trafficPercent = nextStep;
    for (const cluster of Object.values(release.clusters))
      cluster.trafficPercent = nextStep;
    if (nextStep === 100) {
      release.status = "COMPLETED";
      this.ledger.append("RELEASE_COMPLETED", {
        releaseId,
        trafficPercent: 100,
      });
    } else {
      this.ledger.append("TRAFFIC_SHIFTED", {
        releaseId,
        trafficPercent: nextStep,
      });
    }
    return structuredClone(release);
  }

  rollback(releaseId, reason = "operator requested") {
    const release = this.#getRunning(releaseId);
    release.status = "ROLLED_BACK";
    release.trafficPercent = 0;
    release.rollbackReason = reason;
    for (const cluster of Object.values(release.clusters)) {
      cluster.trafficPercent = 0;
      cluster.state = "ROLLED_BACK";
    }
    this.ledger.append("RELEASE_ROLLED_BACK", { releaseId, reason });
    return structuredClone(release);
  }

  get(releaseId) {
    return structuredClone(this.#get(releaseId));
  }

  #get(releaseId) {
    const release = this.releases.get(releaseId);
    if (!release) throw new Error("release not found");
    return release;
  }

  #getRunning(releaseId) {
    const release = this.#get(releaseId);
    if (release.status !== "RUNNING")
      throw new Error(`release is ${release.status}`);
    return release;
  }

  #validateSample({
    errorRate,
    p99LatencyMs,
    saturation,
    securityViolations = 0,
  } = {}) {
    assertNumber("errorRate", errorRate, 0, 1);
    assertNumber("p99LatencyMs", p99LatencyMs, 0, 60000);
    assertNumber("saturation", saturation, 0, 1);
    if (!Number.isInteger(securityViolations) || securityViolations < 0)
      throw new Error("securityViolations must be a non-negative integer");
    return { errorRate, p99LatencyMs, saturation, securityViolations };
  }

  #validateObservation(sample) {
    if (sample?.clusterSamples !== undefined) {
      const entries = sample.clusterSamples;
      if (
        !entries ||
        typeof entries !== "object" ||
        Array.isArray(entries) ||
        Object.keys(entries).length !== this.clusters.length ||
        Object.keys(entries).some((cluster) => !this.clusters.includes(cluster))
      ) {
        throw new Error(
          "clusterSamples must cover exactly the configured clusters",
        );
      }
      const now = this.clock();
      if (!Number.isFinite(now)) throw new Error("clock returned invalid time");
      const clusterSamples = {};
      let breach = null;
      for (const cluster of this.clusters) {
        const raw = entries[cluster];
        const observedAt = Date.parse(raw?.observedAt);
        if (
          !Number.isFinite(observedAt) ||
          observedAt > now ||
          now - observedAt > this.maxSampleAgeMs
        ) {
          throw new Error(`${cluster} telemetry is stale or future-dated`);
        }
        clusterSamples[cluster] = {
          ...this.#validateSample(raw),
          observedAt: new Date(observedAt).toISOString(),
        };
        const reason = this.#breach(clusterSamples[cluster]);
        if (reason && !breach) breach = `${cluster}: ${reason}`;
      }
      return { normalized: { clusterSamples }, breach };
    }
    if (this.requireClusterSamples)
      throw new Error("clusterSamples are required");
    const normalized = this.#validateSample(sample);
    return { normalized, breach: this.#breach(normalized) };
  }

  #breach(sample) {
    if (sample.securityViolations > 0) return "security policy violation";
    if (sample.errorRate > 0.01) return "error rate SLO breach";
    if (sample.p99LatencyMs > 500) return "latency SLO breach";
    if (sample.saturation > 0.85) return "resource saturation breach";
    return null;
  }
}
