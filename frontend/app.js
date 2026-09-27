const API_BASE_URL = "http://127.0.0.1:8000/api";

const elements = {
  body: document.querySelector("#contracts-table-body"),
  closeDrawerButton: document.querySelector("#close-drawer-button"),
  contractCount: document.querySelector("#contract-count"),
  drawer: document.querySelector("#contract-drawer"),
  drawerBackdrop: document.querySelector("#drawer-backdrop"),
  drawerBody: document.querySelector("#drawer-body"),
  drawerTitle: document.querySelector("#drawer-title"),
  error: document.querySelector("#error-message"),
  head: document.querySelector("#contracts-table-head"),
  loadingCellTemplate: document.querySelector("#loading-cell-template"),
  metricsButton: document.querySelector("#metrics-button"),
  metricsPanel: document.querySelector("#metrics-panel"),
  screenButton: document.querySelector("#screen-button"),
  screenButtonLabel: document.querySelector("#screen-button-label"),
  screenButtonSpinner: document.querySelector("#screen-button-spinner"),
  status: document.querySelector("#table-status"),
};

let contracts = [];
let hasScreeningColumns = false;
let latestMetrics = null;
let resultsByContractId = new Map();

function boolLabel(value) {
  return value ? "はい" : "いいえ";
}

function createCell(content, className = "") {
  const cell = document.createElement("td");
  cell.className = className;
  if (content instanceof Node) {
    cell.append(content);
  } else {
    cell.textContent = content;
  }
  return cell;
}

function makeLoadingCell() {
  return elements.loadingCellTemplate.content.cloneNode(true);
}

function createScoredDecision(value, affirmativeScore) {
  const decision = document.createElement("div");
  decision.className = "decision-cell";
  const primary = document.createElement("span");
  primary.textContent = boolLabel(value);
  decision.append(primary);
  if (typeof affirmativeScore === "number") {
    const score = document.createElement("small");
    const displayedScore = value ? affirmativeScore : 1 - affirmativeScore;
    score.textContent = `score: ${displayedScore.toFixed(3)}`;
    decision.append(score);
  }
  return decision;
}

function renderTableHead() {
  const headings = ["No.", "契約書タイトル", "データセット類型"];
  if (hasScreeningColumns) {
    headings.push(
      "改正個人情報保護法判定",
      "要配慮個人情報",
      "こども・未成年",
      "顔特徴・生体情報",
      "再委託",
      "越境移転",
    );
  }
  const row = document.createElement("tr");
  headings.forEach((heading) => {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = heading;
    row.append(cell);
  });
  elements.head.replaceChildren(row);
}

function renderResultCells(row, contractId) {
  const result = resultsByContractId.get(contractId);
  if (!result) {
    for (let index = 0; index < 6; index += 1) {
      row.append(createCell(makeLoadingCell(), "result-cell"));
    }
    return;
  }

  row.append(
    createCell(
      createScoredDecision(
        result.is_personal_data_entrustment,
        result.jev_score,
      ),
      "result-cell",
    ),
  );

  const flags = result.risk_flags;
  const scores = result.risk_scores;
  [
    [flags.sensitive_personal_info, scores.sensitive_personal_info],
    [flags.childrens_data, scores.childrens_data],
    [flags.biometric_facial_data, scores.biometric_facial_data],
    [flags.subcontracting_possible, scores.subcontracting_possible],
    [flags.cross_border_transfer, scores.cross_border_transfer],
  ].forEach(([value, score]) => {
    row.append(createCell(createScoredDecision(value, score), "result-cell"));
  });
}

function renderContracts() {
  renderTableHead();
  const rows = contracts.map((contract) => {
    const row = document.createElement("tr");
    row.append(createCell(String(contract.index), "index-cell"));

    const titleButton = document.createElement("button");
    titleButton.className = "title-button";
    titleButton.type = "button";
    titleButton.textContent = contract.title;
    titleButton.addEventListener("click", () => openContract(contract.id));
    row.append(createCell(titleButton, "title-cell"));
    row.append(createCell(contract.dataset_category, "dataset-category-cell"));

    if (hasScreeningColumns) {
      renderResultCells(row, contract.id);
    }
    return row;
  });
  elements.body.replaceChildren(...rows);
}

function displayError(message) {
  elements.error.textContent = message;
  elements.error.hidden = false;
}

function clearError() {
  elements.error.textContent = "";
  elements.error.hidden = true;
}

function setRunning(isRunning) {
  elements.screenButton.disabled = isRunning;
  elements.screenButtonSpinner.hidden = !isRunning;
  elements.screenButtonLabel.textContent = isRunning ? "判定を実行中" : "判定を実行";
}

async function fetchJson(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "サーバーとの通信に失敗しました。");
  }
  return response.json();
}

async function loadContracts() {
  try {
    contracts = await fetchJson("/contracts");
    elements.contractCount.textContent = `${contracts.length} 件`;
    elements.status.textContent = "本文はタイトルから確認できます";
    elements.screenButton.disabled = false;
    renderContracts();
  } catch (error) {
    elements.status.textContent = "読み込みに失敗しました";
    displayError(error.message);
  }
}

async function openContract(contractId) {
  clearError();
  try {
    const contract = await fetchJson(`/contracts/${contractId}`);
    elements.drawerTitle.textContent = contract.title;
    elements.drawerBody.textContent = contract.body;
    elements.drawer.hidden = false;
    elements.drawerBackdrop.hidden = false;
    requestAnimationFrame(() => {
      elements.drawer.classList.add("is-open");
      elements.drawerBackdrop.classList.add("is-open");
    });
    elements.closeDrawerButton.focus();
  } catch (error) {
    displayError(error.message);
  }
}

function closeDrawer() {
  elements.drawer.classList.remove("is-open");
  elements.drawerBackdrop.classList.remove("is-open");
  window.setTimeout(() => {
    elements.drawer.hidden = true;
    elements.drawerBackdrop.hidden = true;
  }, 180);
}

function formatNumber(value, maximumFractionDigits = 0) {
  return new Intl.NumberFormat("ja-JP", { maximumFractionDigits }).format(value);
}

function showMetrics() {
  if (!latestMetrics) {
    return;
  }
  elements.metricsPanel.hidden = !elements.metricsPanel.hidden;
}

function renderMetrics(metrics) {
  latestMetrics = metrics;
  document.querySelector("#elapsed-value").textContent = `${formatNumber(metrics.elapsed_ms)} ms`;
  if (metrics.input_tokens === null) {
    document.querySelector("#tokens-value").textContent = "API未報告";
    document.querySelector("#cost-value").textContent = "算出不可";
    document.querySelector("#pricing-note").textContent =
      "一部のAPI応答で input token 数が報告されなかったため、合計料金は算出していません。";
  } else {
    document.querySelector("#tokens-value").textContent = `${formatNumber(metrics.input_tokens)} token`;
    document.querySelector("#cost-value").textContent =
      `$${formatNumber(metrics.input_cost_usd, 6)} / ¥${formatNumber(metrics.input_cost_jpy, 4)}`;
    document.querySelector("#pricing-note").textContent =
      `Jev input $${metrics.input_price_per_million_usd} / 100万token、1 USD = ¥${metrics.yen_per_usd}。output token は無料です。`;
  }
  elements.metricsButton.disabled = false;
}

async function runScreening() {
  clearError();
  hasScreeningColumns = true;
  resultsByContractId = new Map();
  renderContracts();
  setRunning(true);
  elements.status.textContent = `${contracts.length} 件を並列判定しています`;
  try {
    const batch = await fetchJson("/screenings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contract_ids: contracts.map((contract) => contract.id) }),
    });
    resultsByContractId = new Map(
      batch.results.map((result) => [result.contract_id, result]),
    );
    renderContracts();
    renderMetrics(batch.metrics);
    elements.status.textContent = `${batch.results.length} 件の判定を完了しました`;
  } catch (error) {
    displayError(error.message);
    elements.status.textContent = "判定に失敗しました";
  } finally {
    setRunning(false);
  }
}

elements.screenButton.addEventListener("click", runScreening);
elements.metricsButton.addEventListener("click", showMetrics);
elements.closeDrawerButton.addEventListener("click", closeDrawer);
elements.drawerBackdrop.addEventListener("click", closeDrawer);
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !elements.drawer.hidden) {
    closeDrawer();
  }
});

loadContracts();
