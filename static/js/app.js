// WebSocket connection
const socket = io();

// DOM Elements
const uploadSection = document.getElementById("upload-section");
const progressSection = document.getElementById("progress-section");
const resultsSection = document.getElementById("results-section");
const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const progressFill = document.getElementById("progress-fill");
const progressText = document.getElementById("progress-text");
const logsContainer = document.getElementById("logs");

// Chart instance
let portfolioChart = null;
let yearlyCharts = {};

// Socket event listeners
socket.on("connect", () => {
  console.log("Connected to server");
});

socket.on("status", (data) => {
  updateProgress(data.progress || 0, data.step || "Processing...");
  updateStepStatus(data.step);
});

socket.on("log", (data) => {
  addLog(data.message, data.level);
});

socket.on("results", (data) => {
  displayResults(data);
});

socket.on("error", (data) => {
  showError(data.message);
});

// Drag and Drop
dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("dragover");
});

dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("dragover");
});

dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("dragover");

  const files = e.dataTransfer.files;
  if (files.length > 0) {
    handleFile(files[0]);
  }
});

// File input change
fileInput.addEventListener("change", (e) => {
  if (e.target.files.length > 0) {
    handleFile(e.target.files[0]);
  }
});

// Handle file upload
function handleFile(file) {
  if (!file.name.endsWith(".csv")) {
    alert("⚠️ Veuillez sélectionner un fichier CSV");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  // Show progress section
  uploadSection.classList.add("hidden");
  progressSection.classList.remove("hidden");

  // Upload file
  fetch("/upload", {
    method: "POST",
    body: formData,
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.error) {
        showError(data.error);
      }
    })
    .catch((error) => {
      showError("Erreur lors de l'upload: " + error);
    });
}

// Update progress bar
function updateProgress(percent, text) {
  progressFill.style.width = percent + "%";
  progressText.textContent = text;
}

// Update step status
function updateStepStatus(stepText) {
  // Reset all steps
  document.querySelectorAll(".step").forEach((step) => {
    step.classList.remove("active", "completed");
  });

  // Determine which step is active
  if (stepText.includes("Étape A") || stepText.includes("Chargement")) {
    document.getElementById("step-1").classList.add("active");
    document
      .getElementById("step-1")
      .querySelector(".step-status").textContent = "En cours...";
  } else if (stepText.includes("Étape B") || stepText.includes("flux")) {
    document.getElementById("step-1").classList.add("completed");
    document
      .getElementById("step-1")
      .querySelector(".step-status").textContent = "✅ Terminé";
    document.getElementById("step-2").classList.add("active");
    document
      .getElementById("step-2")
      .querySelector(".step-status").textContent = "En cours...";
  } else if (stepText.includes("Étape C") || stepText.includes("graphiques")) {
    document.getElementById("step-1").classList.add("completed");
    document.getElementById("step-2").classList.add("completed");
    document
      .getElementById("step-2")
      .querySelector(".step-status").textContent = "✅ Terminé";
    document.getElementById("step-3").classList.add("active");
    document
      .getElementById("step-3")
      .querySelector(".step-status").textContent = "En cours...";
  } else if (stepText.includes("Étape D") || stepText.includes("fiscal")) {
    document.getElementById("step-1").classList.add("completed");
    document.getElementById("step-2").classList.add("completed");
    document.getElementById("step-3").classList.add("completed");
    document
      .getElementById("step-3")
      .querySelector(".step-status").textContent = "✅ Terminé";
    document.getElementById("step-4").classList.add("active");
    document
      .getElementById("step-4")
      .querySelector(".step-status").textContent = "En cours...";
  } else if (stepText.includes("terminée") || stepText.includes("completed")) {
    document.querySelectorAll(".step").forEach((step) => {
      step.classList.add("completed");
      step.querySelector(".step-status").textContent = "✅ Terminé";
    });
  }
}

// Add log entry
function addLog(message, level) {
  const logEntry = document.createElement("div");
  logEntry.className = `log-entry ${level}`;
  logEntry.textContent = message;
  logsContainer.appendChild(logEntry);
  logsContainer.scrollTop = logsContainer.scrollHeight;
}

// Display results
function displayResults(data) {
  progressSection.classList.add("hidden");
  resultsSection.classList.remove("hidden");

  // Update summary cards
  document.getElementById("net-invested").textContent = formatCurrency(
    data.net_invested
  );
  document.getElementById("current-value").textContent = formatCurrency(
    data.net_invested
  ); // Placeholder
  document.getElementById("total-transactions").textContent =
    data.total_transactions;

  // Create yearly charts
  createYearlyCharts(data.charts);

  // Display fiscal report
  displayFiscalReport(data.fiscal_report);

  // Display EUR transactions
  displayEurTransactions(data.eur_transactions);

  // Display holdings
  displayHoldings(data.final_wallet);
}

// Create yearly portfolio charts
function createYearlyCharts(chartsByYear) {
  const container = document.getElementById("yearly-charts-container");
  container.innerHTML = "";

  // Destroy existing charts
  Object.values(yearlyCharts).forEach((chart) => chart.destroy());
  yearlyCharts = {};

  Object.entries(chartsByYear).forEach(([year, chartData]) => {
    const yearSection = document.createElement("div");
    yearSection.className = "year-chart-section";

    yearSection.innerHTML = `
      <h4 class="year-chart-title">Année ${year}</h4>
      <div class="chart-wrapper">
        <canvas id="chart-${year}"></canvas>
      </div>
      <div class="chart-stats">
        <div class="stat-item">
          <span class="stat-label">Net Investi Final:</span>
          <span class="stat-value">${formatCurrency(
            chartData.net_invested[chartData.net_invested.length - 1] || 0
          )}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Valeur Portefeuille Finale:</span>
          <span class="stat-value positive">${formatCurrency(
            chartData.portfolio_values[chartData.portfolio_values.length - 1] ||
              0
          )}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Plus-Value Latente:</span>
          <span class="stat-value ${
            chartData.portfolio_values[chartData.portfolio_values.length - 1] -
              chartData.net_invested[chartData.net_invested.length - 1] >=
            0
              ? "positive"
              : "negative"
          }">
            ${formatCurrency(
              (chartData.portfolio_values[
                chartData.portfolio_values.length - 1
              ] || 0) -
                (chartData.net_invested[chartData.net_invested.length - 1] || 0)
            )}
          </span>
        </div>
      </div>
    `;

    container.appendChild(yearSection);

    // Create chart for this year
    const ctx = document.getElementById(`chart-${year}`).getContext("2d");

    yearlyCharts[year] = new Chart(ctx, {
      type: "line",
      data: {
        labels: chartData.dates,
        datasets: [
          {
            label: "Valeur Portefeuille (€)",
            data: chartData.portfolio_values,
            borderColor: "#f3ba2f",
            backgroundColor: "rgba(243, 186, 47, 0.1)",
            fill: true,
            tension: 0.4,
            borderWidth: 3,
            pointRadius: 0,
            pointHoverRadius: 5,
          },
          {
            label: "Net Investi (€)",
            data: chartData.net_invested,
            borderColor: "#1e2329",
            backgroundColor: "rgba(30, 35, 41, 0.1)",
            fill: true,
            tension: 0.4,
            borderWidth: 2,
            borderDash: [5, 5],
            pointRadius: 0,
            pointHoverRadius: 5,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        aspectRatio: 2.5,
        plugins: {
          legend: {
            display: true,
            labels: {
              color: "#ffffff",
              font: {
                size: 12,
                weight: 600,
              },
              padding: 15,
              usePointStyle: true,
            },
            position: "top",
          },
          tooltip: {
            mode: "index",
            intersect: false,
            backgroundColor: "rgba(30, 35, 41, 0.95)",
            titleColor: "#f3ba2f",
            bodyColor: "#ffffff",
            borderColor: "#f3ba2f",
            borderWidth: 1,
            padding: 12,
            displayColors: true,
            callbacks: {
              label: function (context) {
                return (
                  context.dataset.label +
                  ": " +
                  formatCurrency(context.parsed.y)
                );
              },
            },
          },
        },
        interaction: {
          mode: "nearest",
          axis: "x",
          intersect: false,
        },
        scales: {
          x: {
            grid: {
              color: "rgba(255, 255, 255, 0.05)",
              drawBorder: false,
            },
            ticks: {
              color: "#b0b3b8",
              maxRotation: 0,
              autoSkipPadding: 20,
            },
          },
          y: {
            grid: {
              color: "rgba(255, 255, 255, 0.05)",
              drawBorder: false,
            },
            ticks: {
              color: "#b0b3b8",
              callback: function (value) {
                return formatCurrency(value);
              },
            },
          },
        },
      },
    });
  });
}

// Display fiscal report
function displayFiscalReport(fiscalData) {
  const fiscalContainer = document.getElementById("fiscal-data");
  fiscalContainer.innerHTML = "";

  Object.entries(fiscalData).forEach(([year, data]) => {
    const yearDiv = document.createElement("div");
    yearDiv.className = "year-report";

    yearDiv.innerHTML = `
            <h4>Année ${year}</h4>
            <div class="fiscal-stats">
                <div class="fiscal-stat">
                    <div class="fiscal-stat-label">Dépôts Fiat</div>
                    <div class="fiscal-stat-value positive">+${formatCurrency(
                      data.deposits
                    )}</div>
                </div>
                <div class="fiscal-stat">
                    <div class="fiscal-stat-label">Retraits Fiat</div>
                    <div class="fiscal-stat-value negative">-${formatCurrency(
                      data.withdrawals
                    )}</div>
                </div>
                <div class="fiscal-stat highlight">
                    <div class="fiscal-stat-label"><strong>💶 Cessions Imposables (PFU 30%)</strong></div>
                    <div class="fiscal-stat-value ${
                      data.taxable_volume > 0 ? "negative" : ""
                    }">${formatCurrency(data.taxable_volume)}</div>
                </div>
            </div>

            <div class="fiscal-note">
              ℹ️ Seules les ventes vers monnaies fiat (EUR, USD, GBP, etc.) sont imposables.<br>
              Les conversions crypto → stablecoin (BTC → USDT) bénéficient du sursis d'imposition.
            </div>

            ${
              data.sell_transactions.length === 0
                ? '<div class="transactions-list"><p>✅ Aucun événement taxable détecté pour cette année</p></div>'
                : `
                  <div class="transactions-list">
                    <h5>💶 Ventes vers Fiat - IMPOSABLES (${
                      data.sell_transactions.length
                    }):</h5>
                    <p class="sub-label">EUR, USD, GBP, CHF, JPY, etc. - Monnaies à cours légal</p>
                    ${data.sell_transactions
                      .map(
                        (tx) =>
                          `<div class="transaction-item">
                        <span class="tx-date">${tx.date}</span> |
                        <span class="badge badge-taxable">${
                          tx.operation
                        }</span> |
                        <span class="coin-badge">${tx.coin}</span> |
                        <span class="amount negative">+${formatCurrency(
                          tx.amount
                        )}</span>
                      </div>`
                      )
                      .join("")}
                  </div>
                `
            }
        `;

    fiscalContainer.appendChild(yearDiv);
  });
}

// Display EUR Transactions
function displayEurTransactions(eurData) {
  const eurContainer = document.getElementById("eur-transactions-data");
  eurContainer.innerHTML = "";

  Object.entries(eurData).forEach(([year, data]) => {
    const yearDiv = document.createElement("div");
    yearDiv.className = "eur-year-section";

    yearDiv.innerHTML = `
      <h4 class="eur-year-title">Année ${year}</h4>

      <!-- Summary Stats -->
      <div class="eur-summary-stats">
        <div class="eur-stat">
          <span class="eur-stat-label">Dépôts:</span>
          <span class="eur-stat-value positive">${
            data.deposits.length
          } tx | ${formatCurrency(data.total_deposits)}</span>
        </div>
        <div class="eur-stat">
          <span class="eur-stat-label">Retraits:</span>
          <span class="eur-stat-value negative">${
            data.withdrawals.length
          } tx | ${formatCurrency(data.total_withdrawals)}</span>
        </div>
        <div class="eur-stat">
          <span class="eur-stat-label">Converts vers EUR:</span>
          <span class="eur-stat-value">${
            data.converts.filter((c) => c.direction === "to_eur").length
          } tx | ${formatCurrency(data.total_converts_to_eur)}</span>
        </div>
      </div>

      <!-- Tabs -->
      <div class="eur-tabs">
        <button class="eur-tab active" onclick="showEurTab('${year}', 'deposits')">
          💰 Dépôts (${data.deposits.length})
        </button>
        <button class="eur-tab" onclick="showEurTab('${year}', 'withdrawals')">
          💸 Retraits (${data.withdrawals.length})
        </button>
        <button class="eur-tab" onclick="showEurTab('${year}', 'converts')">
          🔄 Converts (${data.converts.length})
        </button>
      </div>

      <!-- Tab Content -->
      <div class="eur-tab-content">
        <!-- Deposits -->
        <div id="eur-${year}-deposits" class="eur-tab-panel active">
          ${
            data.deposits.length === 0
              ? '<p class="no-data">Aucun dépôt pour cette année</p>'
              : `
              <table class="eur-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Opération</th>
                    <th>Montant</th>
                  </tr>
                </thead>
                <tbody>
                  ${data.deposits
                    .map(
                      (tx) => `
                    <tr>
                      <td>${tx.date}</td>
                      <td><span class="badge badge-deposit">${
                        tx.operation
                      }</span></td>
                      <td class="amount positive">+${formatCurrency(
                        tx.amount
                      )}</td>
                    </tr>
                  `
                    )
                    .join("")}
                </tbody>
              </table>
            `
          }
        </div>

        <!-- Withdrawals -->
        <div id="eur-${year}-withdrawals" class="eur-tab-panel">
          ${
            data.withdrawals.length === 0
              ? '<p class="no-data">Aucun retrait pour cette année</p>'
              : `
              <table class="eur-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Opération</th>
                    <th>Montant</th>
                  </tr>
                </thead>
                <tbody>
                  ${data.withdrawals
                    .map(
                      (tx) => `
                    <tr>
                      <td>${tx.date}</td>
                      <td><span class="badge badge-withdrawal">${
                        tx.operation
                      }</span></td>
                      <td class="amount negative">-${formatCurrency(
                        tx.amount
                      )}</td>
                    </tr>
                  `
                    )
                    .join("")}
                </tbody>
              </table>
            `
          }
        </div>

        <!-- Converts -->
        <div id="eur-${year}-converts" class="eur-tab-panel">
          ${
            data.converts.length === 0
              ? '<p class="no-data">Aucune conversion pour cette année</p>'
              : `
              <table class="eur-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>De</th>
                    <th>→</th>
                    <th>Vers</th>
                    <th>Montant EUR</th>
                  </tr>
                </thead>
                <tbody>
                  ${data.converts
                    .map(
                      (tx) => `
                    <tr>
                      <td>${tx.date}</td>
                      <td><span class="coin-badge">${tx.from_coin}</span></td>
                      <td class="arrow">→</td>
                      <td><span class="coin-badge">${tx.to_coin}</span></td>
                      <td class="amount ${
                        tx.direction === "to_eur" ? "positive" : "negative"
                      }">
                        ${
                          tx.direction === "to_eur" ? "+" : "-"
                        }${formatCurrency(tx.amount)}
                      </td>
                    </tr>
                  `
                    )
                    .join("")}
                </tbody>
              </table>
            `
          }
        </div>
      </div>
    `;

    eurContainer.appendChild(yearDiv);
  });
}

// Tab switching function (must be global)
window.showEurTab = function (year, tab) {
  // Remove active from all tabs for this year
  const yearSection = document
    .querySelector(`#eur-${year}-deposits`)
    .closest(".eur-year-section");
  yearSection
    .querySelectorAll(".eur-tab")
    .forEach((t) => t.classList.remove("active"));
  yearSection
    .querySelectorAll(".eur-tab-panel")
    .forEach((p) => p.classList.remove("active"));

  // Add active to selected panel
  document.querySelectorAll(".eur-tab").forEach((btn) => {
    if (
      btn.textContent.includes(
        tab === "deposits"
          ? "Dépôts"
          : tab === "withdrawals"
          ? "Retraits"
          : "Converts"
      )
    ) {
      btn.classList.add("active");
    }
  });
  document.getElementById(`eur-${year}-${tab}`).classList.add("active");
};

// Display holdings
function displayHoldings(holdings) {
  const holdingsList = document.getElementById("holdings-list");
  holdingsList.innerHTML = "";

  if (Object.keys(holdings).length === 0) {
    holdingsList.innerHTML = "<p>Aucun actif en portefeuille</p>";
    return;
  }

  Object.entries(holdings).forEach(([coin, amount]) => {
    const holdingDiv = document.createElement("div");
    holdingDiv.className = "holding-item";
    holdingDiv.innerHTML = `
            <div class="holding-coin">${coin}</div>
            <div class="holding-amount">${amount.toFixed(8)}</div>
        `;
    holdingsList.appendChild(holdingDiv);
  });
}

// Format currency
function formatCurrency(value) {
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

// Show error
function showError(message) {
  alert("❌ Erreur: " + message);
  resetApp();
}

// Reset app
function resetApp() {
  uploadSection.classList.remove("hidden");
  progressSection.classList.add("hidden");
  resultsSection.classList.add("hidden");

  // Reset progress
  progressFill.style.width = "0%";
  progressText.textContent = "Initialisation...";
  logsContainer.innerHTML = "";

  // Reset steps
  document.querySelectorAll(".step").forEach((step) => {
    step.classList.remove("active", "completed");
    step.querySelector(".step-status").textContent = "En attente...";
  });

  // Reset file input
  fileInput.value = "";
}
