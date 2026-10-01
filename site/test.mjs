import test from "node:test";
import assert from "node:assert/strict";
import { once } from "node:events";
import { readFile } from "node:fs/promises";
import { server } from "./serve.mjs";
test("public preview serves intended portfolio and stylesheet with protective headers", async (t) => {
  const app = server().listen(0, "127.0.0.1");
  await once(app, "listening");
  t.after(() => new Promise((r) => app.close(r)));
  const base = `http://127.0.0.1:${app.address().port}`;
  const response = await fetch(base);
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Incident Replay Lab/);
  assert.match(html, /AI Inference Gateway/);
  assert.match(html, /Agent Eval Control Plane/);
  assert.match(html, /Infrastructure Change Evidence Lab/);
  assert.match(html, /Delivery Command Ledger/);
  assert.match(html, /Messenger Reliability Lab/);
  assert.match(html, /GPU Topology Reliability Lab/);
  assert.match(html, /Agentic SDLC Control Plane/);
  assert.match(html, /Service Mesh Release Safety Lab/);
  assert.match(html, /Kubernetes Capacity Budget Lab/);
  assert.match(html, /Network Path Triage Lab/);
  assert.match(html, /SLO Burn Evidence Lab/);
  assert.match(html, /Query Plan Evidence Lab/);
  assert.match(html, /Incident Dependency Triage Lab/);
  assert.match(html, /Tail Latency Attribution Lab/);
  assert.match(html, /Delivery Handoff Evidence Lab/);
  assert.match(html, /Spatial Network Evidence Lab/);
  assert.match(html, /Factory Event Evidence Lab/);
  assert.match(html, /Robot Command Evidence Lab/);
  assert.match(html, /Settlement Reconciliation Evidence Lab/);
  assert.match(html, /결제 시도·제공자 응답 근거 실습/);
  assert.match(html, /서비스 변경 계약 영향 실습/);
  assert.match(html, /공간 데이터 배포 영향 실습/);
  assert.match(html, /계좌 이벤트 순서·멱등 재생 실습/);
  assert.match(html, /32 \/ PROJECTS/);
  assert.match(html, /답변 근거 추적 실습/);
  assert.match(html, /상품 변경 안전 검토 실습/);
  assert.match(html, /구독 접근권·제휴사 확인 대조 실습/);
  assert.match(html, /가상 이체 기장 완결성 검사/);
  assert.match(html, /관계형 스키마 순차 배포 호환성 실습/);
  assert.match(html, /가상 이체 트랜잭션·발행 대기 복구 실습/);
  assert.match(html, /PG 인증 귀환·서버 확인 대조 실습/);
  assert.match(html, /lang="ko"/);
  assert.match(html, /실행 중인 API 데모가 아닙니다/);
  assert.match(
    response.headers.get("content-security-policy"),
    /form-action 'none'/,
  );
  for (const href of html.matchAll(/href="#([^"]+)"/g))
    assert.ok(html.includes(`id="${href[1]}"`));
  const css = await fetch(base + "/styles.css");
  assert.match(await css.text(), /@media\s*\(max-width:\s*800px\)/);
  assert.equal(await (await fetch(base, { method: "HEAD" })).text(), "");
});
test("private paths, API requests and writes cannot pass through public preview", async (t) => {
  const app = server().listen(0, "127.0.0.1");
  await once(app, "listening");
  t.after(() => new Promise((r) => app.close(r)));
  const base = `http://127.0.0.1:${app.address().port}`;
  for (const path of [
    "/.git/config",
    "/ai/sre/data/lab.sqlite",
    "/api/sim/state",
    "/serve.mjs",
    "/test.mjs",
    "/%2e%2e/private",
  ])
    assert.equal((await fetch(base + path)).status, 404);
  assert.equal(
    (await fetch(base, { method: "POST", body: "synthetic" })).status,
    405,
  );
});
test("public assets have no forms, scripts, tracking, personal contacts or local data paths", async () => {
  const html = await readFile(new URL("index.html", import.meta.url), "utf8");
  assert.doesNotMatch(
    html,
    /<script|<form|<iframe|mailto:|tel:|010[- ]?\d{4}|ijinz91@|C:\\PRJ|localStorage|fetch\(/i,
  );
  for (const link of html.matchAll(/href="(https:[^"]+)"/g))
    assert.ok(
      link[1].startsWith("https://github.com/ijinz9191-tech/portfolio"),
    );
});

test("local font and license are served without exposing other font paths", async (t) => {
  const app = server().listen(0, "127.0.0.1");
  await once(app, "listening");
  t.after(() => new Promise((r) => app.close(r)));
  const base = `http://127.0.0.1:${app.address().port}`;
  const font = await fetch(base + "/fonts/PretendardVariable.woff2");
  assert.equal(font.status, 200);
  assert.equal(font.headers.get("content-type"), "font/woff2");
  assert.equal(
    Buffer.from(await font.arrayBuffer())
      .subarray(0, 4)
      .toString(),
    "wOF2",
  );
  const license = await fetch(base + "/fonts/OFL.txt");
  assert.match(await license.text(), /SIL OPEN FONT LICENSE/);
  assert.equal((await fetch(base + "/fonts/other.woff2")).status, 404);
});
