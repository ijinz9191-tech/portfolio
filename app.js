/* Public data only. Never load applicant source documents or submission records here. */
"use strict";
const statuses = { implemented: "구현됨", planned: "계획", unverified: "미검증" };
function node(tag, content, className) {
  const element = document.createElement(tag);
  if (content !== undefined) element.textContent = content;
  if (className) element.className = className;
  return element;
}
function publicLink(url, label) {
  const parsed = new URL(url);
  if (parsed.protocol !== "https:" || parsed.username || parsed.password) throw new Error("Invalid public link");
  const link = node("a", label);
  link.href = parsed.href;
  link.rel = "noopener noreferrer";
  return link;
}
async function render() {
  try {
    const response = await fetch("public.data.json", { cache: "no-cache" });
    if (!response.ok) throw new Error("Public data unavailable");
    const data = await response.json();
    if (data.schemaVersion !== 1 || !Array.isArray(data.capabilities) || !Array.isArray(data.evidence)) throw new Error("Invalid public data");
    const cards = data.capabilities.map(item => {
      if (!Object.hasOwn(statuses, item.status)) throw new Error("Invalid capability status");
      const article = node("article", undefined, "capability");
      article.append(node("span", statuses[item.status], `status ${item.status}`), node("h3", item.title), node("p", item.description));
      return article;
    });
    const evidence = data.evidence.map(item => {
      const article = node("article", undefined, "evidence-item");
      article.append(node("h4", item.title), node("p", item.description));
      if (item.url) article.append(publicLink(item.url, "공개 근거 열기 ↗"));
      return article;
    });
    document.querySelector("#capabilities").replaceChildren(...cards);
    document.querySelector("#evidence-list").replaceChildren(...evidence);
    document.querySelector("#profile-summary").textContent = data.profileSummary;
    document.querySelector("#revision").textContent = `PUBLIC REVISION / ${data.revision}`;
    if (data.repositoryUrl) document.querySelector("#repository-link").append(publicLink(data.repositoryUrl, "Git 저장소 ↗"));
    if (data.metrics) {
      document.querySelector("#metric-title").textContent = data.metrics.title;
      document.querySelector("#metric-description").textContent = `${data.metrics.description} 측정 범위: ${data.metrics.scope}. 분모: ${data.metrics.denominator}. 확인: ${data.metrics.verifiedAt}.`;
    }
  } catch {
    document.querySelector("#capabilities").replaceChildren(node("p", "프로젝트 상태를 확인할 수 없습니다.", "muted"));
    document.querySelector("#data-error").hidden = false;
  }
}
render();
