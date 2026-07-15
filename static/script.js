// Show the spinner and message initially
document.addEventListener("DOMContentLoaded", () => {
    const syncStatus = document.getElementById("sync-status");
    const syncText = document.getElementById("sync-text");
    const spinner = document.getElementById("spinner");

    if (!syncStatus || !syncText || !spinner) {
        return;
    }

    // Show spinner and message
    syncStatus.style.display = "flex";

    // Function to poll the backend for sync status
    const checkSyncStatus = async () => {
        try {
            const response = await fetch("/sync-status"); // Endpoint for sync status
            const data = await response.json();

            if (!data.ongoing) {
                // Hide the spinner and show the success message
                spinner.style.display = "none";
                syncText.textContent = "😊 Background Sync Completed!";
                syncText.style.color = "green";

                // Stop polling once sync is complete
                clearInterval(syncInterval);
            }
        } catch (error) {
            console.error("Error checking sync status:", error);
        }
    };

    // Poll the sync status every 2 seconds
    const syncInterval = setInterval(checkSyncStatus, 2000);
});

document.addEventListener("DOMContentLoaded", () => {
    const reportContent = document.getElementById("report-content");
    const progressFill = document.getElementById("report-progress-fill");
    const progressPercent = document.getElementById("report-progress-percent");
    const progressMessage = document.getElementById("report-progress-message");
    const loadingPanel = document.getElementById("report-loading-panel");

    if (!reportContent || !progressFill || !progressPercent || !progressMessage || !loadingPanel) {
        return;
    }

    const params = new URLSearchParams({
        year: document.body.dataset.reportYear || "fy26",
        include_voided: document.body.dataset.includeVoided || "0",
        refresh: document.body.dataset.forceRefresh || "0"
    });

    const updateProgress = (progress, message) => {
        const safeProgress = Math.max(0, Math.min(100, Number(progress) || 0));
        progressFill.style.width = `${safeProgress}%`;
        progressPercent.textContent = `${safeProgress}%`;
        progressMessage.textContent = message || "Loading report";
    };

    const loadReportContent = async (jobId) => {
        const response = await fetch(`/reports/content/${jobId}`);
        if (!response.ok) {
            throw new Error("Unable to load completed report content.");
        }

        reportContent.innerHTML = await response.text();
        setupSortableReportTables(reportContent);
        setupProductViewToggle();
        setupJobProfitabilityView();
        setupCalendarView();
        loadingPanel.style.display = "none";
    };

    const pollReportStatus = (jobId) => {
        const interval = setInterval(async () => {
            try {
                const response = await fetch(`/reports/status/${jobId}`);
                const data = await response.json();
                updateProgress(data.progress, data.message);

                if (data.status === "complete") {
                    clearInterval(interval);
                    await loadReportContent(jobId);
                } else if (data.status === "error") {
                    clearInterval(interval);
                    progressMessage.textContent = `Report load failed: ${data.message}`;
                    progressMessage.classList.add("error-message");
                }
            } catch (error) {
                clearInterval(interval);
                progressMessage.textContent = "Report load failed.";
                progressMessage.classList.add("error-message");
                console.error("Error loading report:", error);
            }
        }, 1000);
    };

    const startReportLoad = async () => {
        try {
            updateProgress(0, "Queued report load");
            const response = await fetch(`/reports/start?${params.toString()}`);
            const data = await response.json();
            pollReportStatus(data.job_id);
        } catch (error) {
            progressMessage.textContent = "Report load failed.";
            progressMessage.classList.add("error-message");
            console.error("Error starting report load:", error);
        }
    };

    startReportLoad();
});

function setupSortableReportTables(container = document) {
    const tables = container.querySelectorAll(".sortable-report-table");

    tables.forEach((table) => {
        const headers = table.querySelectorAll(":scope > thead th");

        headers.forEach((header, columnIndex) => {
            if (header.dataset.sortableReady === "1") {
                return;
            }

            const existingExplain = header.querySelector(".explain-tooltip");
            const explainTitle = existingExplain?.getAttribute("title");
            const label = Array.from(header.childNodes)
                .filter((node) => node !== existingExplain)
                .map((node) => node.textContent)
                .join("")
                .trim();
            const button = document.createElement("button");
            const labelText = document.createElement("span");
            const indicator = document.createElement("span");

            header.textContent = "";
            header.dataset.sortableReady = "1";
            header.setAttribute("aria-sort", "none");
            button.type = "button";
            button.className = "sortable-header-button";
            labelText.className = "sort-label";
            labelText.textContent = label;
            indicator.className = "sort-indicator";
            indicator.setAttribute("aria-hidden", "true");
            indicator.textContent = "↕";
            button.appendChild(labelText);
            button.appendChild(indicator);

            button.addEventListener("click", () => {
                const currentColumn = Number(table.dataset.sortColumn);
                const currentDirection = table.dataset.sortDirection || "asc";
                const nextDirection = currentColumn === columnIndex && currentDirection === "asc" ? "desc" : "asc";

                sortReportTable(table, columnIndex, nextDirection);
            });

            header.appendChild(button);
            if (explainTitle) {
                const explain = document.createElement("span");
                explain.className = "explain-tooltip";
                explain.tabIndex = 0;
                explain.title = explainTitle;
                explain.textContent = "?";
                header.appendChild(explain);
            }
        });
    });
}

function setSortableHeaderLabel(header, label) {
    const labelText = header?.querySelector(".sort-label");

    if (labelText) {
        labelText.textContent = label;
        return;
    }

    if (header) {
        header.textContent = label;
    }
}

function sortReportTable(table, columnIndex, direction) {
    const tbody = table.querySelector(":scope > tbody");
    const headers = table.querySelectorAll(":scope > thead th");
    const sortType = headers[columnIndex]?.dataset.sortType || "string";

    if (!tbody) {
        return;
    }

    const rowGroups = [];
    const summaryRows = [];
    const rows = Array.from(tbody.querySelectorAll(":scope > tr"));

    for (let index = 0; index < rows.length; index += 1) {
        const row = rows[index];

        if (row.classList.contains("invoice-line-items-row")) {
            continue;
        }

        if (row.classList.contains("product-filter-summary-row")) {
            summaryRows.push(row);
            continue;
        }

        const group = [row];
        let nextIndex = index + 1;
        while (nextIndex < rows.length && rows[nextIndex].classList.contains("invoice-line-items-row")) {
            group.push(rows[nextIndex]);
            nextIndex += 1;
        }

        rowGroups.push(group);
        index = nextIndex - 1;
    }

    rowGroups.sort((leftGroup, rightGroup) => {
        const leftValue = getSortableCellValue(leftGroup[0].children[columnIndex], sortType);
        const rightValue = getSortableCellValue(rightGroup[0].children[columnIndex], sortType);
        const comparison = compareSortableValues(leftValue, rightValue, sortType);

        return direction === "asc" ? comparison : -comparison;
    });

    rowGroups.forEach((group) => {
        group.forEach((row) => tbody.appendChild(row));
    });
    summaryRows.forEach((row) => tbody.appendChild(row));

    table.dataset.sortColumn = String(columnIndex);
    table.dataset.sortDirection = direction;
    updateSortHeaderState(headers, columnIndex, direction);
}

function getSortableCellValue(cell, sortType) {
    if (!cell) {
        return "";
    }

    const rawValue = cell.dataset.sortValue ?? cell.textContent.trim();

    if (sortType === "number") {
        const parsedNumber = Number(String(rawValue).replace(/[^0-9.-]/g, ""));
        return Number.isNaN(parsedNumber) ? null : parsedNumber;
    }

    if (sortType === "date") {
        const parsedDate = Date.parse(rawValue);
        return Number.isNaN(parsedDate) ? null : parsedDate;
    }

    return rawValue.toLocaleLowerCase();
}

function compareSortableValues(leftValue, rightValue, sortType) {
    if (leftValue === null && rightValue === null) {
        return 0;
    }

    if (leftValue === null) {
        return 1;
    }

    if (rightValue === null) {
        return -1;
    }

    if (sortType === "number" || sortType === "date") {
        return leftValue - rightValue;
    }

    return leftValue.localeCompare(rightValue, undefined, {
        numeric: true,
        sensitivity: "base"
    });
}

function updateSortHeaderState(headers, sortedColumnIndex, direction) {
    headers.forEach((header, index) => {
        const indicator = header.querySelector(".sort-indicator");
        const isSorted = index === sortedColumnIndex;

        header.setAttribute("aria-sort", isSorted ? (direction === "asc" ? "ascending" : "descending") : "none");

        if (indicator) {
            indicator.textContent = isSorted ? (direction === "asc" ? "▲" : "▼") : "↕";
        }
    });
}

function setupProductViewToggle() {
    const button = document.getElementById("product-view-button");
    const invoiceView = document.getElementById("invoice-view");
    const productView = document.getElementById("product-view");
    const productViewBody = document.getElementById("product-view-body");
    const productPriceHeading = document.getElementById("product-price-heading");
    const productSmartFilter = document.getElementById("product-smart-filter");
    const combineProductCodes = document.getElementById("combine-product-codes");
    const productListPriceInput = document.getElementById("product-list-price");
    const includeMidTierPrice = document.getElementById("include-mid-tier-price");
    const productMidPriceField = document.getElementById("product-mid-price-field");
    const productMidPriceInput = document.getElementById("product-mid-price");
    const productVolumePriceInput = document.getElementById("product-volume-price");
    const generateProductMetricsButton = document.getElementById("generate-product-metrics");
    const productPricingMetrics = document.getElementById("product-pricing-metrics");
    let currentVisibleProducts = [];
    let productMetricsGenerated = false;

    if (!button || !invoiceView || !productView || !productViewBody || !productPriceHeading) {
        return;
    }

    const formatCurrency = (value) => {
        return new Intl.NumberFormat("en-AU", {
            style: "currency",
            currency: "AUD"
        }).format(value);
    };

    const formatQuantity = (value) => {
        return Number.isInteger(value) ? String(value) : value.toFixed(2);
    };

    const escapeHtml = (value) => {
        const element = document.createElement("div");
        element.textContent = value;
        return element.innerHTML;
    };

    const explanationText = {
        unitPrice: "The unit price used for this product row. In combined product mode this becomes the weighted average price.",
        weightedAverage: "Average price weighted by quantity sold, so high-volume prices count more than one-off prices. Example: $10 sold once and $20 sold 100 times has a normal average of $15, but a weighted average of $19.90.",
        median: "The middle selling price by quantity. Half of units sold at or below this price.",
        percentileRange: "The middle 50% of sold quantities. This is the normal trading price band.",
        p10P90: "A wider expected price range that excludes the lowest 10% and highest 10% of sold quantities.",
        minMax: "The lowest and highest unit prices found for this product or filtered group.",
        spread: "The difference between P75 and P25. A larger spread means less consistent pricing.",
        priceRisk: "Price Risk is chosen in priority order: Stable if there is one unique price; otherwise Discount review if 15% or more of quantity is below P25; otherwise Variable if P25-P75 spread is more than 20% of median and there are at least 3 prices; otherwise Premium spread if 15% or more of quantity is above P75 and spread is more than 15%; otherwise Stable.",
        stable: "Stable means there is one unique price, or multiple prices that do not meet the Discount review, Variable, or Premium spread thresholds.",
        variable: "Variable means Discount review did not trigger, there are at least 3 unique prices, and the P25-P75 spread is more than 20% of the median price.",
        discountReview: "Discount review means 15% or more of quantity sold below P25. This is checked before Variable and Premium spread because it may indicate discount leakage.",
        premiumSpread: "Premium spread means Discount review and Variable did not trigger, 15% or more of quantity sold above P75, and the P25-P75 spread is more than 15% of median.",
        totalQtyRevenue: "Total quantity sold and total revenue for this product or filtered group.",
        revenueBelowP25: "Revenue from prices below the normal price band. Useful for spotting possible underpricing.",
        potentialUpliftToP25: "Potential uplift if below-normal units were repriced to the P25 benchmark. Calculated as (P25 price - actual price) times quantity for each below-P25 price bucket. This is an opportunity estimate, not guaranteed recoverable revenue.",
        revenueAboveP75: "Revenue from prices above the normal price band. Useful for spotting premium pricing opportunities.",
        listPrice: "The standard list price entered by the user for this product and financial year.",
        midPrice: "The mid tier price entered by the user for this product and financial year. This sits between volume price and list price.",
        volumePrice: "The approved volume or bulk order price entered by the user for this product and financial year.",
        volumeDependency: "The share of total quantity sold at or below the volume price. Higher values mean this product is more dependent on volume/bulk pricing.",
        upliftToVolumeFloor: "Potential uplift if every unit sold below the volume price was lifted to the volume price. Calculated as (volume price - actual price) times quantity for below-volume buckets. This is an estimate, not guaranteed recoverable revenue.",
        upliftPerDollarVolumeIncrease: "Estimated revenue gained for each $1 increase to the volume price, based only on units currently sold exactly at the volume price.",
        upliftPerDollarMidIncrease: "Estimated revenue gained for each $1 increase to the mid tier price, based only on units currently sold exactly at the mid tier price.",
        upliftPerDollarListIncrease: "Estimated revenue gained for each $1 increase to the list price, based only on units currently sold exactly at the list price.",
        pricePosition: "Groups units by where their actual selling price sits compared with the entered volume, mid tier, and list prices.",
        qtyShare: "The percentage of total matched quantity represented by this price-position group.",
        volumeScenario: "Simple revenue scenarios based on units currently sold exactly at the volume price. They do not account for demand changes, customer sensitivity, or negotiated exceptions.",
        midScenario: "Simple revenue scenarios based on units currently sold exactly at the mid tier price. They do not account for demand changes, customer sensitivity, or negotiated exceptions.",
        listScenario: "Simple revenue scenarios based on units currently sold exactly at the list price. They do not account for demand changes, customer sensitivity, or negotiated exceptions.",
        normalBand: "Normal means the price sits inside the P25-P75 trading range.",
        belowNormalBand: "Below normal means the price is below P25, outside the normal trading range.",
        premiumBand: "Premium means the price is above P75, outside the normal trading range."
    };

    const getRiskExplanation = (riskLabel) => {
        if (riskLabel === "Discount review") {
            return explanationText.discountReview;
        }

        if (riskLabel === "Premium spread") {
            return explanationText.premiumSpread;
        }

        if (riskLabel === "Variable") {
            return explanationText.variable;
        }

        return explanationText.stable;
    };

    const getBandExplanation = (bandLabel) => {
        if (bandLabel === "Below normal") {
            return explanationText.belowNormalBand;
        }

        if (bandLabel === "Premium") {
            return explanationText.premiumBand;
        }

        return explanationText.normalBand;
    };

    const buildExplain = (text) => {
        return `<span class="explain-tooltip" tabindex="0" title="${escapeHtml(text)}">?</span>`;
    };

    const parsePriceInput = (input) => {
        const value = Number(input?.value);
        return Number.isFinite(value) && value >= 0 ? value : null;
    };

    const pricesMatch = (left, right) => {
        return Math.abs(left - right) < 0.005;
    };

    const sumBuckets = (priceBuckets, predicate) => {
        return Array.from(priceBuckets.values()).reduce((summary, bucket) => {
            if (!predicate(bucket.unitPrice)) {
                return summary;
            }

            summary.quantity += bucket.quantity;
            summary.revenue += bucket.unitPrice * bucket.quantity;
            return summary;
        }, { quantity: 0, revenue: 0 });
    };

    const emptyBucketSummary = () => ({ quantity: 0, revenue: 0 });

    const computeProductLevelMetrics = (priceBuckets, listPrice, midPrice, volumePrice) => {
        const hasMidTierPrice = midPrice !== null;
        const stats = computePricingStats(priceBuckets);
        const atList = sumBuckets(priceBuckets, (unitPrice) => pricesMatch(unitPrice, listPrice));
        const atMid = hasMidTierPrice
            ? sumBuckets(priceBuckets, (unitPrice) => pricesMatch(unitPrice, midPrice))
            : emptyBucketSummary();
        const atVolume = sumBuckets(priceBuckets, (unitPrice) => pricesMatch(unitPrice, volumePrice));
        const belowVolume = sumBuckets(priceBuckets, (unitPrice) => unitPrice < volumePrice && !pricesMatch(unitPrice, volumePrice));
        const betweenVolumeAndMid = hasMidTierPrice
            ? sumBuckets(
                priceBuckets,
                (unitPrice) => unitPrice > volumePrice && unitPrice < midPrice
            )
            : emptyBucketSummary();
        const betweenMidAndList = hasMidTierPrice
            ? sumBuckets(
                priceBuckets,
                (unitPrice) => unitPrice > midPrice && unitPrice < listPrice
            )
            : emptyBucketSummary();
        const betweenVolumeAndList = hasMidTierPrice
            ? emptyBucketSummary()
            : sumBuckets(
                priceBuckets,
                (unitPrice) => unitPrice > volumePrice && unitPrice < listPrice
            );
        const aboveList = sumBuckets(priceBuckets, (unitPrice) => unitPrice > listPrice && !pricesMatch(unitPrice, listPrice));
        const potentialUpliftToVolume = Array.from(priceBuckets.values()).reduce((sum, bucket) => {
            if (bucket.unitPrice >= volumePrice || pricesMatch(bucket.unitPrice, volumePrice)) {
                return sum;
            }

            return sum + (volumePrice - bucket.unitPrice) * bucket.quantity;
        }, 0);
        const qtyAtOrBelowVolume = belowVolume.quantity + atVolume.quantity;
        const volumeDependencyPct = stats.totalQuantity
            ? (qtyAtOrBelowVolume / stats.totalQuantity) * 100
            : 0;

        return {
            ...stats,
            listPrice,
            midPrice,
            volumePrice,
            atList,
            atMid,
            atVolume,
            belowVolume,
            betweenVolumeAndMid,
            betweenMidAndList,
            betweenVolumeAndList,
            aboveList,
            potentialUpliftToVolume,
            qtyAtOrBelowVolume,
            volumeDependencyPct,
            upliftPerDollarVolumeIncrease: atVolume.quantity,
            upliftPerDollarMidIncrease: atMid.quantity,
            upliftPerDollarListIncrease: atList.quantity,
            scenario5: atVolume.quantity * 5,
            scenario10: atVolume.quantity * 10,
            scenario15: atVolume.quantity * 15,
            midScenario5: atMid.quantity * 5,
            midScenario10: atMid.quantity * 10,
            midScenario15: atMid.quantity * 15,
            listScenario5: atList.quantity * 5,
            listScenario10: atList.quantity * 10,
            listScenario15: atList.quantity * 15
        };
    };

    const formatPercent = (value) => {
        return `${value.toFixed(1)}%`;
    };

    const quantityShare = (quantity, totalQuantity) => {
        return totalQuantity ? formatPercent((quantity / totalQuantity) * 100) : "0.0%";
    };

    const renderProductMetricsMessage = (message, isError = false) => {
        if (!productPricingMetrics) {
            return;
        }

        productPricingMetrics.hidden = false;
        productPricingMetrics.innerHTML = `<p class="${isError ? "error-message" : "product-pricing-metrics-message"}">${escapeHtml(message)}</p>`;
    };

    const isMidTierEnabled = () => Boolean(includeMidTierPrice?.checked);

    const syncMidTierPriceInput = () => {
        const enabled = isMidTierEnabled();

        if (productMidPriceField) {
            productMidPriceField.hidden = !enabled;
        }

        if (productMidPriceInput) {
            productMidPriceInput.disabled = !enabled;
        }
    };

    const renderProductLevelMetrics = () => {
        if (!productPricingMetrics) {
            return;
        }

        const filterLabel = (productSmartFilter?.value || "").trim();
        const listPrice = parsePriceInput(productListPriceInput);
        const midTierEnabled = isMidTierEnabled();
        const midPrice = midTierEnabled ? parsePriceInput(productMidPriceInput) : null;
        const volumePrice = parsePriceInput(productVolumePriceInput);

        if (!filterLabel) {
            renderProductMetricsMessage("Enter a Smart filter before generating product-level metrics.", true);
            return;
        }

        if (currentVisibleProducts.length === 0) {
            renderProductMetricsMessage("No products match the current Smart filter.", true);
            return;
        }

        if (listPrice === null || volumePrice === null || (midTierEnabled && midPrice === null)) {
            const requiredPrices = midTierEnabled
                ? "List price, Mid tier price, and Volume price"
                : "List price and Volume price";
            renderProductMetricsMessage(`Enter ${requiredPrices} as positive dollar values.`, true);
            return;
        }

        if (midTierEnabled && (volumePrice > midPrice || midPrice > listPrice)) {
            renderProductMetricsMessage("Prices should be ordered as Volume price <= Mid tier price <= List price.", true);
            return;
        }

        if (!midTierEnabled && volumePrice > listPrice) {
            renderProductMetricsMessage("Prices should be ordered as Volume price <= List price.", true);
            return;
        }

        const combinedPriceBuckets = mergePriceBuckets(currentVisibleProducts);
        const metrics = computeProductLevelMetrics(combinedPriceBuckets, listPrice, midPrice, volumePrice);
        const volumeDependencyLabel = metrics.volumeDependencyPct >= 50
            ? "Volume-price dominated"
            : metrics.volumeDependencyPct >= 25
                ? "Moderate volume-price dependency"
                : "Low volume-price dependency";
        const belowVolumeInsight = metrics.belowVolume.quantity > 0
            ? `Below-volume leakage: ${formatCurrency(metrics.potentialUpliftToVolume)} potential uplift if ${formatQuantity(metrics.belowVolume.quantity)} units were lifted to ${formatCurrency(volumePrice)}.`
            : "No below-volume price buckets detected.";
        const midPriceCard = midTierEnabled
            ? `<div class="product-pricing-metric-card"><strong>Mid Tier Price ${buildExplain(explanationText.midPrice)}</strong><span>${escapeHtml(formatCurrency(midPrice))}</span></div>`
            : "";
        const midUpliftCard = midTierEnabled
            ? `<div class="product-pricing-metric-card"><strong>Uplift Per $1 Mid Tier Increase ${buildExplain(explanationText.upliftPerDollarMidIncrease)}</strong><span>${escapeHtml(formatCurrency(metrics.upliftPerDollarMidIncrease))}</span></div>`
            : "";
        const midPositionRows = midTierEnabled
            ? `
                    <tr>
                        <td>At mid tier price (${escapeHtml(formatCurrency(midPrice))})</td>
                        <td>${escapeHtml(formatQuantity(metrics.atMid.quantity))}</td>
                        <td>${escapeHtml(quantityShare(metrics.atMid.quantity, metrics.totalQuantity))}</td>
                        <td>${escapeHtml(formatCurrency(metrics.atMid.revenue))}</td>
                    </tr>
                    <tr>
                        <td>Between volume and mid tier</td>
                        <td>${escapeHtml(formatQuantity(metrics.betweenVolumeAndMid.quantity))}</td>
                        <td>${escapeHtml(quantityShare(metrics.betweenVolumeAndMid.quantity, metrics.totalQuantity))}</td>
                        <td>${escapeHtml(formatCurrency(metrics.betweenVolumeAndMid.revenue))}</td>
                    </tr>
                    <tr>
                        <td>Between mid tier and list</td>
                        <td>${escapeHtml(formatQuantity(metrics.betweenMidAndList.quantity))}</td>
                        <td>${escapeHtml(quantityShare(metrics.betweenMidAndList.quantity, metrics.totalQuantity))}</td>
                        <td>${escapeHtml(formatCurrency(metrics.betweenMidAndList.revenue))}</td>
                    </tr>`
            : `
                    <tr>
                        <td>Between volume and list</td>
                        <td>${escapeHtml(formatQuantity(metrics.betweenVolumeAndList.quantity))}</td>
                        <td>${escapeHtml(quantityShare(metrics.betweenVolumeAndList.quantity, metrics.totalQuantity))}</td>
                        <td>${escapeHtml(formatCurrency(metrics.betweenVolumeAndList.revenue))}</td>
                    </tr>`;
        const midScenario = midTierEnabled
            ? `
            <div class="product-pricing-scenarios">
                <strong>Mid tier price increase scenarios ${buildExplain(explanationText.midScenario)} based on ${escapeHtml(formatQuantity(metrics.atMid.quantity))} units currently at mid tier price:</strong>
                <span>+$5: ${escapeHtml(formatCurrency(metrics.midScenario5))}</span>
                <span>+$10: ${escapeHtml(formatCurrency(metrics.midScenario10))}</span>
                <span>+$15: ${escapeHtml(formatCurrency(metrics.midScenario15))}</span>
            </div>`
            : "";

        productPricingMetrics.hidden = false;
        productPricingMetrics.innerHTML = `
            <h3>Product-Level Pricing Metrics: ${escapeHtml(filterLabel)}</h3>
            <p><strong>${escapeHtml(volumeDependencyLabel)}.</strong> ${escapeHtml(belowVolumeInsight)}</p>
            <div class="product-pricing-metric-grid">
                <div class="product-pricing-metric-card"><strong>List Price ${buildExplain(explanationText.listPrice)}</strong><span>${escapeHtml(formatCurrency(listPrice))}</span></div>
                ${midPriceCard}
                <div class="product-pricing-metric-card"><strong>Volume Price ${buildExplain(explanationText.volumePrice)}</strong><span>${escapeHtml(formatCurrency(volumePrice))}</span></div>
                <div class="product-pricing-metric-card"><strong>Total Qty ${buildExplain(explanationText.totalQtyRevenue)}</strong><span>${escapeHtml(formatQuantity(metrics.totalQuantity))}</span></div>
                <div class="product-pricing-metric-card"><strong>Total Revenue ${buildExplain(explanationText.totalQtyRevenue)}</strong><span>${escapeHtml(formatCurrency(metrics.totalRevenue))}</span></div>
                <div class="product-pricing-metric-card"><strong>Weighted Avg ${buildExplain(explanationText.weightedAverage)}</strong><span>${escapeHtml(formatCurrency(metrics.weightedAverage))}</span></div>
                <div class="product-pricing-metric-card"><strong>Volume Dependency ${buildExplain(explanationText.volumeDependency)}</strong><span>${escapeHtml(formatPercent(metrics.volumeDependencyPct))}</span></div>
                <div class="product-pricing-metric-card"><strong>Uplift To Volume Floor ${buildExplain(explanationText.upliftToVolumeFloor)}</strong><span>${escapeHtml(formatCurrency(metrics.potentialUpliftToVolume))}</span></div>
                <div class="product-pricing-metric-card"><strong>Uplift Per $1 Volume Increase ${buildExplain(explanationText.upliftPerDollarVolumeIncrease)}</strong><span>${escapeHtml(formatCurrency(metrics.upliftPerDollarVolumeIncrease))}</span></div>
                ${midUpliftCard}
                <div class="product-pricing-metric-card"><strong>Uplift Per $1 List Increase ${buildExplain(explanationText.upliftPerDollarListIncrease)}</strong><span>${escapeHtml(formatCurrency(metrics.upliftPerDollarListIncrease))}</span></div>
            </div>
            <table class="product-pricing-metrics-table">
                <thead>
                    <tr>
                        <th>Price Position ${buildExplain(explanationText.pricePosition)}</th>
                        <th>Qty</th>
                        <th>Qty Share ${buildExplain(explanationText.qtyShare)}</th>
                        <th>Revenue</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>At list price (${escapeHtml(formatCurrency(listPrice))})</td>
                        <td>${escapeHtml(formatQuantity(metrics.atList.quantity))}</td>
                        <td>${escapeHtml(quantityShare(metrics.atList.quantity, metrics.totalQuantity))}</td>
                        <td>${escapeHtml(formatCurrency(metrics.atList.revenue))}</td>
                    </tr>
                    <tr>
                        <td>At volume price (${escapeHtml(formatCurrency(volumePrice))})</td>
                        <td>${escapeHtml(formatQuantity(metrics.atVolume.quantity))}</td>
                        <td>${escapeHtml(quantityShare(metrics.atVolume.quantity, metrics.totalQuantity))}</td>
                        <td>${escapeHtml(formatCurrency(metrics.atVolume.revenue))}</td>
                    </tr>
                    <tr>
                        <td>Below volume price</td>
                        <td>${escapeHtml(formatQuantity(metrics.belowVolume.quantity))}</td>
                        <td>${escapeHtml(quantityShare(metrics.belowVolume.quantity, metrics.totalQuantity))}</td>
                        <td>${escapeHtml(formatCurrency(metrics.belowVolume.revenue))}</td>
                    </tr>
                    ${midPositionRows}
                    <tr>
                        <td>Above list price</td>
                        <td>${escapeHtml(formatQuantity(metrics.aboveList.quantity))}</td>
                        <td>${escapeHtml(quantityShare(metrics.aboveList.quantity, metrics.totalQuantity))}</td>
                        <td>${escapeHtml(formatCurrency(metrics.aboveList.revenue))}</td>
                    </tr>
                </tbody>
            </table>
            <div class="product-pricing-scenarios">
                <strong>Volume price increase scenarios ${buildExplain(explanationText.volumeScenario)} based on ${escapeHtml(formatQuantity(metrics.atVolume.quantity))} units currently at volume price:</strong>
                <span>+$5: ${escapeHtml(formatCurrency(metrics.scenario5))}</span>
                <span>+$10: ${escapeHtml(formatCurrency(metrics.scenario10))}</span>
                <span>+$15: ${escapeHtml(formatCurrency(metrics.scenario15))}</span>
            </div>
            ${midScenario}
            <div class="product-pricing-scenarios">
                <strong>List price increase scenarios ${buildExplain(explanationText.listScenario)} based on ${escapeHtml(formatQuantity(metrics.atList.quantity))} units currently at list price:</strong>
                <span>+$5: ${escapeHtml(formatCurrency(metrics.listScenario5))}</span>
                <span>+$10: ${escapeHtml(formatCurrency(metrics.listScenario10))}</span>
                <span>+$15: ${escapeHtml(formatCurrency(metrics.listScenario15))}</span>
            </div>
        `;
    };

    const computePricingStats = (priceBuckets) => {
        const buckets = Array.from(priceBuckets.values())
            .filter((bucket) => bucket.quantity > 0)
            .sort((left, right) => left.unitPrice - right.unitPrice);
        const totalQuantity = buckets.reduce((sum, bucket) => sum + bucket.quantity, 0);
        const totalRevenue = buckets.reduce(
            (sum, bucket) => sum + bucket.unitPrice * bucket.quantity,
            0
        );

        const emptyStats = {
            totalQuantity: 0,
            totalRevenue: 0,
            weightedAverage: 0,
            median: 0,
            p10: 0,
            p25: 0,
            p50: 0,
            p75: 0,
            p90: 0,
            minPrice: 0,
            maxPrice: 0,
            iqr: 0,
            spreadPct: 0,
            qtyBelowP25: 0,
            revenueBelowP25: 0,
            potentialUpliftToP25: 0,
            qtyAboveP75: 0,
            revenueAboveP75: 0,
            uniquePrices: 0,
            riskLabel: "Stable",
            riskClass: "price-risk-stable"
        };

        if (totalQuantity === 0) {
            return emptyStats;
        }

        const weightedPercentile = (percentile) => {
            const target = (percentile / 100) * totalQuantity;
            let cumulative = 0;

            for (const bucket of buckets) {
                cumulative += bucket.quantity;
                if (cumulative >= target) {
                    return bucket.unitPrice;
                }
            }

            return buckets[buckets.length - 1].unitPrice;
        };

        const p10 = weightedPercentile(10);
        const p25 = weightedPercentile(25);
        const p50 = weightedPercentile(50);
        const p75 = weightedPercentile(75);
        const p90 = weightedPercentile(90);
        const minPrice = buckets[0].unitPrice;
        const maxPrice = buckets[buckets.length - 1].unitPrice;
        const weightedAverage = totalRevenue / totalQuantity;
        const iqr = p75 - p25;
        const spreadPct = p50 > 0 ? (iqr / p50) * 100 : 0;

        let qtyBelowP25 = 0;
        let revenueBelowP25 = 0;
        let potentialUpliftToP25 = 0;
        let qtyAboveP75 = 0;
        let revenueAboveP75 = 0;

        buckets.forEach((bucket) => {
            const revenue = bucket.unitPrice * bucket.quantity;

            if (bucket.unitPrice < p25) {
                qtyBelowP25 += bucket.quantity;
                revenueBelowP25 += revenue;
                potentialUpliftToP25 += (p25 - bucket.unitPrice) * bucket.quantity;
            }

            if (bucket.unitPrice > p75) {
                qtyAboveP75 += bucket.quantity;
                revenueAboveP75 += revenue;
            }
        });

        const uniquePrices = buckets.length;
        let riskLabel = "Stable";
        let riskClass = "price-risk-stable";
        const belowShare = qtyBelowP25 / totalQuantity;
        const aboveShare = qtyAboveP75 / totalQuantity;

        if (uniquePrices === 1) {
            riskLabel = "Stable";
        } else if (belowShare >= 0.15) {
            riskLabel = "Discount review";
            riskClass = "price-risk-discount";
        } else if (spreadPct > 20 && uniquePrices >= 3) {
            riskLabel = "Variable";
            riskClass = "price-risk-variable";
        } else if (aboveShare >= 0.15 && spreadPct > 15) {
            riskLabel = "Premium spread";
            riskClass = "price-risk-premium";
        }

        return {
            totalQuantity,
            totalRevenue,
            weightedAverage,
            median: p50,
            p10,
            p25,
            p50,
            p75,
            p90,
            minPrice,
            maxPrice,
            iqr,
            spreadPct,
            qtyBelowP25,
            revenueBelowP25,
            potentialUpliftToP25,
            qtyAboveP75,
            revenueAboveP75,
            uniquePrices,
            riskLabel,
            riskClass
        };
    };

    const getPriceBand = (unitPrice, stats) => {
        if (stats.uniquePrices <= 1) {
            return { label: "Normal", className: "band-normal" };
        }

        if (unitPrice < stats.p25) {
            return { label: "Below normal", className: "band-below" };
        }

        if (unitPrice > stats.p75) {
            return { label: "Premium", className: "band-premium" };
        }

        return { label: "Normal", className: "band-normal" };
    };

    const getBarColor = (unitPrice, stats) => {
        if (stats.uniquePrices <= 1) {
            return "#007bff";
        }

        if (unitPrice < stats.p25) {
            return "#e67e22";
        }

        if (unitPrice > stats.p75) {
            return "#6f42c1";
        }

        return "#007bff";
    };

    const formatPercentileRange = (stats) => {
        if (stats.uniquePrices <= 1) {
            return formatCurrency(stats.minPrice);
        }

        return `${formatCurrency(stats.p25)} – ${formatCurrency(stats.p75)}`;
    };

    const buildPricingInsight = (stats) => {
        if (stats.totalQuantity === 0) {
            return "No sales data available.";
        }

        if (stats.uniquePrices === 1) {
            return `All ${formatQuantity(stats.totalQuantity)} units sold at a single price of ${formatCurrency(stats.minPrice)}.`;
        }

        const belowPct = ((stats.qtyBelowP25 / stats.totalQuantity) * 100).toFixed(0);
        return `Most sales occurred between ${formatCurrency(stats.p25)} and ${formatCurrency(stats.p75)}; ${belowPct}% of quantity sold below the normal price band.`;
    };

    const appendRiskBadge = (cell, stats) => {
        const badge = document.createElement("span");
        badge.className = `price-risk-badge ${stats.riskClass}`;
        badge.textContent = stats.riskLabel;
        badge.title = getRiskExplanation(stats.riskLabel);
        cell.appendChild(badge);
        cell.dataset.sortValue = stats.riskLabel.toLocaleLowerCase();
    };

    const appendPricingCells = (row, stats) => {
        const medianCell = document.createElement("td");
        const rangeCell = document.createElement("td");
        const riskCell = document.createElement("td");

        medianCell.textContent = formatCurrency(stats.median || 0);
        medianCell.dataset.sortValue = stats.median || 0;
        rangeCell.textContent = formatPercentileRange(stats);
        rangeCell.dataset.sortValue = stats.p25 || 0;
        appendRiskBadge(riskCell, stats);
        row.appendChild(medianCell);
        row.appendChild(rangeCell);
        row.appendChild(riskCell);
    };

    const drawDistributionChart = (canvas, data, stats) => {
        const context = canvas.getContext("2d");
        const width = canvas.width;
        const height = canvas.height;
        const margin = {
            top: 40,
            right: 30,
            bottom: 80,
            left: 90
        };
        const chartWidth = width - margin.left - margin.right;
        const chartHeight = height - margin.top - margin.bottom;
        const maxQuantity = Math.max(...data.map((item) => item.quantity), 1);
        const barGap = 16;
        const barWidth = Math.max(8, Math.min(80, (chartWidth - barGap * (data.length - 1)) / data.length));

        context.clearRect(0, 0, width, height);
        context.fillStyle = "#ffffff";
        context.fillRect(0, 0, width, height);
        context.strokeStyle = "#333333";
        context.lineWidth = 2;
        context.beginPath();
        context.moveTo(margin.left, margin.top);
        context.lineTo(margin.left, height - margin.bottom);
        context.lineTo(width - margin.right, height - margin.bottom);
        context.stroke();

        context.fillStyle = "#333333";
        context.font = "14px Arial, sans-serif";
        context.textAlign = "center";
        context.fillText("Price", margin.left + chartWidth / 2, height - 20);

        context.save();
        context.translate(24, margin.top + chartHeight / 2);
        context.rotate(-Math.PI / 2);
        context.fillText("Quantity", 0, 0);
        context.restore();

        context.textAlign = "right";
        context.textBaseline = "middle";
        for (let i = 0; i <= 4; i += 1) {
            const quantity = (maxQuantity / 4) * i;
            const y = height - margin.bottom - (quantity / maxQuantity) * chartHeight;
            context.strokeStyle = "#e0e0e0";
            context.lineWidth = 1;
            context.beginPath();
            context.moveTo(margin.left, y);
            context.lineTo(width - margin.right, y);
            context.stroke();
            context.fillStyle = "#333333";
            context.fillText(formatQuantity(quantity), margin.left - 10, y);
        }

        const priceToX = (price) => {
            if (data.length === 1) {
                return margin.left + barWidth / 2;
            }

            const minPrice = data[0].unitPrice;
            const maxPrice = data[data.length - 1].unitPrice;
            const priceSpan = maxPrice - minPrice || 1;
            const normalized = (price - minPrice) / priceSpan;
            return margin.left + normalized * (chartWidth - barWidth) + barWidth / 2;
        };

        const drawPercentileMarker = (price, label, color) => {
            const x = priceToX(price);
            context.strokeStyle = color;
            context.lineWidth = 2;
            context.setLineDash([6, 4]);
            context.beginPath();
            context.moveTo(x, margin.top);
            context.lineTo(x, height - margin.bottom);
            context.stroke();
            context.setLineDash([]);
            context.fillStyle = color;
            context.font = "12px Arial, sans-serif";
            context.textAlign = "center";
            context.textBaseline = "bottom";
            context.fillText(label, x, margin.top - 8);
        };

        if (stats.uniquePrices > 1) {
            drawPercentileMarker(stats.p25, "P25", "#e67e22");
            drawPercentileMarker(stats.p50, "Median", "#28a745");
            drawPercentileMarker(stats.p75, "P75", "#6f42c1");
        }

        data.forEach((item, index) => {
            const x = margin.left + index * (barWidth + barGap);
            const barHeight = (item.quantity / maxQuantity) * chartHeight;
            const y = height - margin.bottom - barHeight;

            context.fillStyle = getBarColor(item.unitPrice, stats);
            context.fillRect(x, y, barWidth, barHeight);
            context.fillStyle = "#333333";
            context.textAlign = "center";
            context.textBaseline = "bottom";
            context.fillText(formatQuantity(item.quantity), x + barWidth / 2, y - 6);
            context.textBaseline = "top";
            context.fillText(formatCurrency(item.unitPrice), x + barWidth / 2, height - margin.bottom + 10);
        });

        context.fillStyle = "#555555";
        context.font = "12px Arial, sans-serif";
        context.textAlign = "left";
        context.textBaseline = "top";
        context.fillText("Blue = normal band | Orange = below P25 | Purple = above P75", margin.left, height - margin.bottom + 42);
    };

    const mergePriceBuckets = (products) => {
        const combined = new Map();

        products.forEach((product) => {
            product.priceBuckets.forEach((bucket, priceKey) => {
                const existing = combined.get(priceKey) || {
                    unitPrice: bucket.unitPrice,
                    quantity: 0,
                    revenue: 0
                };
                existing.quantity += bucket.quantity;
                existing.revenue = existing.unitPrice * existing.quantity;
                combined.set(priceKey, existing);
            });
        });

        return combined;
    };

    const buildDistributionDetailRows = (distributionData, stats) => {
        return distributionData.map((item) => {
            const revenue = item.unitPrice * item.quantity;
            const qtyShare = stats.totalQuantity
                ? ((item.quantity / stats.totalQuantity) * 100).toFixed(1)
                : "0.0";
            const revenueShare = stats.totalRevenue
                ? ((revenue / stats.totalRevenue) * 100).toFixed(1)
                : "0.0";
            const band = getPriceBand(item.unitPrice, stats);

            return `<tr class="${band.className}">
                <td>${escapeHtml(formatCurrency(item.unitPrice))}</td>
                <td>${escapeHtml(formatQuantity(item.quantity))}</td>
                <td>${escapeHtml(formatCurrency(revenue))}</td>
                <td>${escapeHtml(`${qtyShare}%`)}</td>
                <td>${escapeHtml(`${revenueShare}%`)}</td>
                <td><span title="${escapeHtml(getBandExplanation(band.label))}">${escapeHtml(band.label)}</span></td>
            </tr>`;
        }).join("");
    };

    const escapeCsvCell = (value) => {
        const text = String(value ?? "");

        if (/[",\r\n]/.test(text)) {
            return `"${text.replace(/"/g, '""')}"`;
        }

        return text;
    };

    const buildDistributionCsvRows = (distributionData, stats) => {
        const rows = [["Price", "Qty", "Revenue", "Share of Qty", "Share of Revenue", "Band"]];

        distributionData.forEach((item) => {
            const revenue = item.unitPrice * item.quantity;
            const qtyShare = stats.totalQuantity
                ? ((item.quantity / stats.totalQuantity) * 100).toFixed(1)
                : "0.0";
            const revenueShare = stats.totalRevenue
                ? ((revenue / stats.totalRevenue) * 100).toFixed(1)
                : "0.0";
            const band = getPriceBand(item.unitPrice, stats);

            rows.push([
                formatCurrency(item.unitPrice),
                formatQuantity(item.quantity),
                formatCurrency(revenue),
                `${qtyShare}%`,
                `${revenueShare}%`,
                band.label
            ]);
        });

        return rows;
    };

    const downloadCsv = (targetWindow, filename, rows) => {
        const csvContent = rows
            .map((row) => row.map(escapeCsvCell).join(","))
            .join("\r\n");
        const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const link = targetWindow.document.createElement("a");

        link.href = url;
        link.download = filename;
        targetWindow.document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    };

    const buildDistributionCsvFilename = (title) => {
        const safeTitle = String(title || "price-distribution")
            .trim()
            .replace(/[^a-z0-9]+/gi, "-")
            .replace(/^-+|-+$/g, "")
            .toLowerCase();

        return `${safeTitle || "price-distribution"}-price-distribution.csv`;
    };

    const openDistributionChart = (title, priceBuckets, options = {}) => {
        const distributionData = Array.from(priceBuckets.values())
            .sort((a, b) => a.unitPrice - b.unitPrice)
            .filter((item) => item.quantity > 0);
        const stats = computePricingStats(priceBuckets);
        const chartWindow = window.open("", "_blank");
        const escapedTitle = escapeHtml(title);
        const escapedDescription = escapeHtml(options.description || buildPricingInsight(stats));
        const escapedInsight = escapeHtml(buildPricingInsight(stats));
        const canvasWidth = Math.max(1000, distributionData.length * 96 + 120);
        const detailRows = buildDistributionDetailRows(distributionData, stats);
        const belowPct = stats.totalQuantity
            ? ((stats.qtyBelowP25 / stats.totalQuantity) * 100).toFixed(0)
            : "0";
        const abovePct = stats.totalQuantity
            ? ((stats.qtyAboveP75 / stats.totalQuantity) * 100).toFixed(0)
            : "0";
        const potentialUpliftLine = (stats.qtyBelowP25 > 0 || stats.riskLabel === "Discount review")
            ? `<br>
        <strong>Potential uplift to P25 ${buildExplain(explanationText.potentialUpliftToP25)}:</strong> ${escapeHtml(formatCurrency(stats.potentialUpliftToP25))} across ${escapeHtml(formatQuantity(stats.qtyBelowP25))} below-band units`
            : "";

        if (!chartWindow) {
            alert("Unable to open the distribution chart. Please allow pop-ups for this site.");
            return;
        }

        chartWindow.document.open();
        chartWindow.document.write(`<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${escapedTitle} Price Distribution</title>
    <style>
        body {
            color: #333333;
            font-family: Arial, sans-serif;
            margin: 24px;
        }
        .pricing-insight {
            background-color: #f8fbff;
            border: 1px solid #cfe3ff;
            border-radius: 6px;
            margin: 16px 0;
            padding: 12px 16px;
        }
        .pricing-kpi-grid {
            display: grid;
            gap: 12px;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            margin: 16px 0;
        }
        .pricing-kpi-card {
            background-color: #ffffff;
            border: 1px solid #d7e7fb;
            border-radius: 6px;
            padding: 12px;
        }
        .pricing-kpi-card strong {
            align-items: center;
            color: #555555;
            display: flex;
            font-size: 12px;
            gap: 6px;
            justify-content: space-between;
            margin-bottom: 6px;
        }
        .pricing-kpi-card span {
            font-size: 18px;
            font-weight: bold;
        }
        .explain-tooltip {
            background-color: #eef6ff;
            border: 1px solid #cfe3ff;
            border-radius: 999px;
            color: #0056b3;
            cursor: help;
            display: inline-block;
            font-size: 11px;
            font-weight: bold;
            height: 16px;
            line-height: 1;
            padding: 3px;
            text-align: center;
            text-transform: uppercase;
            width: 16px;
        }
        .pricing-kpi-card strong .explain-tooltip,
        .pricing-commercial-insight .explain-tooltip {
            font-size: 11px;
            font-weight: bold;
        }
        .pricing-commercial-insight {
            background-color: #e8f4ea;
            border-radius: 6px;
            margin: 16px 0;
            padding: 12px 16px;
        }
        .pricing-detail-table {
            border-collapse: collapse;
            margin-top: 20px;
            width: 100%;
        }
        .pricing-detail-table th,
        .pricing-detail-table td {
            border: 1px solid #d7e7fb;
            padding: 8px 10px;
            text-align: left;
        }
        .pricing-detail-table th {
            background-color: #007bff;
            color: #ffffff;
        }
        .distribution-actions {
            align-items: center;
            display: flex;
            justify-content: flex-end;
            margin-top: 20px;
        }
        .download-table-button {
            background-color: #007bff;
            border: 0;
            border-radius: 4px;
            color: #ffffff;
            cursor: pointer;
            font-size: 14px;
            padding: 10px 14px;
        }
        .download-table-button:hover,
        .download-table-button:focus {
            background-color: #0056b3;
        }
        .band-below td:last-child {
            color: #c0392b;
            font-weight: bold;
        }
        .band-premium td:last-child {
            color: #6f42c1;
            font-weight: bold;
        }
        canvas {
            border: 1px solid #d7e7fb;
            display: block;
            margin-top: 20px;
            max-width: 100%;
        }
    </style>
</head>
<body>
    <h1>${escapedTitle} Price Distribution</h1>
    <p class="pricing-insight">${escapedDescription}</p>
    <p class="pricing-insight"><strong>Commercial insight:</strong> ${escapedInsight}</p>
    <div class="pricing-kpi-grid">
        <div class="pricing-kpi-card"><strong>Weighted Avg ${buildExplain(explanationText.weightedAverage)}</strong><span>${escapeHtml(formatCurrency(stats.weightedAverage))}</span></div>
        <div class="pricing-kpi-card"><strong>Median ${buildExplain(explanationText.median)}</strong><span>${escapeHtml(formatCurrency(stats.median))}</span></div>
        <div class="pricing-kpi-card"><strong>P25 – P75 ${buildExplain(explanationText.percentileRange)}</strong><span>${escapeHtml(formatPercentileRange(stats))}</span></div>
        <div class="pricing-kpi-card"><strong>P10 – P90 ${buildExplain(explanationText.p10P90)}</strong><span>${escapeHtml(formatCurrency(stats.p10))} – ${escapeHtml(formatCurrency(stats.p90))}</span></div>
        <div class="pricing-kpi-card"><strong>Min / Max ${buildExplain(explanationText.minMax)}</strong><span>${escapeHtml(formatCurrency(stats.minPrice))} / ${escapeHtml(formatCurrency(stats.maxPrice))}</span></div>
        <div class="pricing-kpi-card"><strong>Spread (IQR) ${buildExplain(explanationText.spread)}</strong><span>${escapeHtml(formatCurrency(stats.iqr))} (${escapeHtml(stats.spreadPct.toFixed(1))}%)</span></div>
        <div class="pricing-kpi-card"><strong>Price Risk ${buildExplain(explanationText.priceRisk)}</strong><span title="${escapeHtml(getRiskExplanation(stats.riskLabel))}">${escapeHtml(stats.riskLabel)}</span></div>
        <div class="pricing-kpi-card"><strong>Total Qty / Revenue ${buildExplain(explanationText.totalQtyRevenue)}</strong><span>${escapeHtml(formatQuantity(stats.totalQuantity))} / ${escapeHtml(formatCurrency(stats.totalRevenue))}</span></div>
    </div>
    <div class="pricing-commercial-insight">
        <strong>Pricing consistency:</strong> ${escapeHtml(stats.uniquePrices <= 1 ? "Single price point." : stats.spreadPct > 20 ? "High variation across price points." : "Moderate variation across price points.")}
        <br>
        <strong>Revenue below P25 ${buildExplain(explanationText.revenueBelowP25)}:</strong> ${escapeHtml(formatCurrency(stats.revenueBelowP25))} (${escapeHtml(belowPct)}% of quantity)
        ${potentialUpliftLine}
        <br>
        <strong>Revenue above P75 ${buildExplain(explanationText.revenueAboveP75)}:</strong> ${escapeHtml(formatCurrency(stats.revenueAboveP75))} (${escapeHtml(abovePct)}% of quantity)
    </div>
    <canvas id="distribution-chart" width="${canvasWidth}" height="640"></canvas>
    <div class="distribution-actions">
        <button type="button" id="download-distribution-table" class="download-table-button">Download Table</button>
    </div>
    <table class="pricing-detail-table">
        <thead>
            <tr>
                <th>Price</th>
                <th>Qty</th>
                <th>Revenue</th>
                <th>Share of Qty</th>
                <th>Share of Revenue</th>
                <th>Band</th>
            </tr>
        </thead>
        <tbody>${detailRows}</tbody>
    </table>
</body>
</html>`);
        chartWindow.document.close();

        const canvas = chartWindow.document.getElementById("distribution-chart");
        drawDistributionChart(canvas, distributionData, stats);

        const downloadButton = chartWindow.document.getElementById("download-distribution-table");
        downloadButton?.addEventListener("click", () => {
            downloadCsv(
                chartWindow,
                buildDistributionCsvFilename(title),
                buildDistributionCsvRows(distributionData, stats)
            );
        });
    };

    const attachPriceLink = (cell, displayPrice, onClick) => {
        const priceLink = document.createElement("a");

        priceLink.href = "#";
        priceLink.textContent = formatCurrency(displayPrice || 0);
        priceLink.title = "Show Distribution";
        priceLink.setAttribute("aria-label", "Show Distribution");
        priceLink.addEventListener("click", (event) => {
            event.preventDefault();
            onClick();
        });
        cell.dataset.sortValue = displayPrice || 0;
        cell.appendChild(priceLink);
    };

    const openInvoice = (invoice) => {
        if (!invoice?.url) {
            alert("This invoice could not be opened because it is missing an invoice link.");
            return;
        }

        window.open(invoice.url, "_blank", "noopener");
    };

    const getUniqueInvoices = (invoices) => {
        const uniqueInvoices = new Map();

        invoices.forEach((invoice) => {
            if (!invoice.id && !invoice.number) {
                return;
            }

            uniqueInvoices.set(invoice.id || invoice.number, invoice);
        });

        return Array.from(uniqueInvoices.values());
    };

    const closeInvoiceChooser = () => {
        document.querySelector(".invoice-chooser-overlay")?.remove();
    };

    const openInvoiceChooser = (invoices) => {
        const uniqueInvoices = getUniqueInvoices(invoices);
        const overlay = document.createElement("div");
        const dialog = document.createElement("div");
        const heading = document.createElement("h3");
        const closeButton = document.createElement("button");
        const table = document.createElement("table");
        const tbody = document.createElement("tbody");

        closeInvoiceChooser();
        overlay.className = "invoice-chooser-overlay";
        dialog.className = "invoice-chooser-dialog";
        dialog.setAttribute("role", "dialog");
        dialog.setAttribute("aria-modal", "true");
        dialog.setAttribute("aria-labelledby", "invoice-chooser-title");
        heading.id = "invoice-chooser-title";
        heading.textContent = "Choose an invoice";
        closeButton.type = "button";
        closeButton.className = "invoice-chooser-close";
        closeButton.textContent = "Close";
        closeButton.addEventListener("click", closeInvoiceChooser);
        table.className = "invoice-chooser-table";
        table.innerHTML = `
            <thead>
                <tr>
                    <th>Invoice Number</th>
                    <th>Customer</th>
                    <th>Invoice Date</th>
                    <th>View Invoice</th>
                </tr>
            </thead>
        `;

        uniqueInvoices.forEach((invoice) => {
            const row = document.createElement("tr");
            const invoiceNumberCell = document.createElement("td");
            const customerCell = document.createElement("td");
            const dateCell = document.createElement("td");
            const viewCell = document.createElement("td");
            const viewButton = document.createElement("button");

            invoiceNumberCell.textContent = invoice.number || "";
            customerCell.textContent = invoice.customer || "";
            dateCell.textContent = invoice.date || "";
            viewButton.type = "button";
            viewButton.className = "report-view-button";
            viewButton.textContent = "View Invoice";
            viewButton.addEventListener("click", () => {
                openInvoice(invoice);
            });
            viewCell.appendChild(viewButton);
            row.appendChild(invoiceNumberCell);
            row.appendChild(customerCell);
            row.appendChild(dateCell);
            row.appendChild(viewCell);
            tbody.appendChild(row);
        });

        table.appendChild(tbody);
        dialog.appendChild(closeButton);
        dialog.appendChild(heading);
        dialog.appendChild(table);
        overlay.appendChild(dialog);
        overlay.addEventListener("click", (event) => {
            if (event.target === overlay) {
                closeInvoiceChooser();
            }
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                closeInvoiceChooser();
            }
        }, { once: true });
        document.body.appendChild(overlay);
    };

    const appendInvoiceButtonCell = (row, invoices) => {
        const cell = document.createElement("td");
        const button = document.createElement("button");
        const uniqueInvoices = getUniqueInvoices(invoices);

        cell.dataset.sortValue = uniqueInvoices.length ? uniqueInvoices[0].number || "" : "";
        button.type = "button";
        button.className = "report-view-button";
        button.textContent = "View Invoice";
        button.disabled = uniqueInvoices.length === 0;
        button.addEventListener("click", () => {
            if (uniqueInvoices.length === 1) {
                openInvoice(uniqueInvoices[0]);
                return;
            }

            openInvoiceChooser(uniqueInvoices);
        });
        cell.appendChild(button);
        row.appendChild(cell);
    };

    const productMatchesFilter = (productCode, filterQuery) => {
        const productCodeSearchValue = productCode.toLocaleLowerCase();

        if (filterQuery.startsWith("^")) {
            return productCodeSearchValue.startsWith(filterQuery.slice(1));
        }

        return productCodeSearchValue.includes(filterQuery);
    };

    const appendProductRow = (product, shouldCombineProductCodes) => {
        const row = document.createElement("tr");
        const productCodeCell = document.createElement("td");
        const unitPriceCell = document.createElement("td");
        const quantityCell = document.createElement("td");
        const sumValueCell = document.createElement("td");
        const stats = computePricingStats(product.priceBuckets);
        const averagePrice = product.quantity ? product.totalValue / product.quantity : 0;
        const displayPrice = shouldCombineProductCodes
            ? averagePrice
            : product.unitPrice;

        productCodeCell.textContent = product.productCode;
        productCodeCell.dataset.sortValue = product.productCode;
        attachPriceLink(unitPriceCell, displayPrice, () => {
            openDistributionChart(product.productCode, product.priceBuckets, {
                description: buildPricingInsight(stats)
            });
        });
        quantityCell.textContent = formatQuantity(product.quantity);
        quantityCell.dataset.sortValue = product.quantity;
        sumValueCell.textContent = formatCurrency(product.totalValue || 0);
        sumValueCell.dataset.sortValue = product.totalValue || 0;
        row.appendChild(productCodeCell);
        row.appendChild(unitPriceCell);
        appendPricingCells(row, stats);
        row.appendChild(quantityCell);
        row.appendChild(sumValueCell);
        appendInvoiceButtonCell(row, product.invoices);
        productViewBody.appendChild(row);
    };

    const appendFilterSummaryRow = (filterLabel, matchedProducts) => {
        const totalQuantity = matchedProducts.reduce((sum, product) => sum + product.quantity, 0);
        const totalSumValue = matchedProducts.reduce((sum, product) => sum + product.totalValue, 0);
        const averagePrice = totalQuantity ? totalSumValue / totalQuantity : 0;
        const combinedPriceBuckets = mergePriceBuckets(matchedProducts);
        const stats = computePricingStats(combinedPriceBuckets);
        const row = document.createElement("tr");
        const productCodeCell = document.createElement("td");
        const unitPriceCell = document.createElement("td");
        const quantityCell = document.createElement("td");
        const sumValueCell = document.createElement("td");

        row.className = "product-filter-summary-row";
        productCodeCell.textContent = `Summary: ${filterLabel}`;
        productCodeCell.dataset.sortValue = `summary-${filterLabel}`;
        attachPriceLink(unitPriceCell, averagePrice, () => {
            openDistributionChart(`Smart Filter: ${filterLabel}`, combinedPriceBuckets, {
                description: `Includes ${matchedProducts.length} product rows, total qty ${formatQuantity(totalQuantity)}, total value ${formatCurrency(totalSumValue || 0)}, average price ${formatCurrency(averagePrice || 0)}. ${buildPricingInsight(stats)}`
            });
        });
        quantityCell.textContent = formatQuantity(totalQuantity);
        quantityCell.dataset.sortValue = totalQuantity;
        sumValueCell.textContent = formatCurrency(totalSumValue || 0);
        sumValueCell.dataset.sortValue = totalSumValue || 0;
        row.appendChild(productCodeCell);
        row.appendChild(unitPriceCell);
        appendPricingCells(row, stats);
        row.appendChild(quantityCell);
        row.appendChild(sumValueCell);
        appendInvoiceButtonCell(row, matchedProducts.flatMap((product) => product.invoices));
        productViewBody.appendChild(row);
    };

    const buildProductRows = () => {
        const products = new Map();
        const lineItems = document.querySelectorAll(".invoice-line-item");
        const shouldCombineProductCodes = combineProductCodes && combineProductCodes.checked;
        const filterQuery = (productSmartFilter?.value || "").trim().toLocaleLowerCase();

        setSortableHeaderLabel(productPriceHeading, shouldCombineProductCodes ? "Average Price" : "Unit Price");

        lineItems.forEach((lineItem) => {
            const productCode = lineItem.dataset.productCode || "Unknown";
            const unitPrice = Number(lineItem.dataset.unitPrice || 0);
            const quantity = Number(lineItem.dataset.quantity || 0);
            const key = shouldCombineProductCodes ? productCode : `${productCode}|${unitPrice.toFixed(4)}`;
            const invoice = {
                id: lineItem.dataset.invoiceId || "",
                number: lineItem.dataset.invoiceNumber || "",
                customer: lineItem.dataset.invoiceCustomer || "",
                date: lineItem.dataset.invoiceDate || "",
                url: lineItem.dataset.invoiceUrl || ""
            };
            const existing = products.get(key) || {
                productCode,
                unitPrice,
                quantity: 0,
                totalValue: 0,
                priceBuckets: new Map(),
                invoices: []
            };
            const priceKey = unitPrice.toFixed(4);
            const priceBucket = existing.priceBuckets.get(priceKey) || {
                unitPrice,
                quantity: 0,
                revenue: 0
            };

            existing.quantity += quantity;
            existing.totalValue += unitPrice * quantity;
            priceBucket.quantity += quantity;
            priceBucket.revenue = priceBucket.unitPrice * priceBucket.quantity;
            existing.priceBuckets.set(priceKey, priceBucket);
            existing.invoices.push(invoice);
            products.set(key, existing);
        });

        const sortedProducts = Array.from(products.values())
            .sort((a, b) => a.productCode.localeCompare(b.productCode) || a.unitPrice - b.unitPrice);
        const visibleProducts = filterQuery
            ? sortedProducts.filter((product) => productMatchesFilter(product.productCode, filterQuery))
            : sortedProducts;
        currentVisibleProducts = visibleProducts;

        productViewBody.innerHTML = "";
        visibleProducts.forEach((product) => {
            appendProductRow(product, shouldCombineProductCodes);
        });

        if (filterQuery && visibleProducts.length > 0) {
            appendFilterSummaryRow(productSmartFilter.value.trim(), visibleProducts);
        }

        const productTable = productView.querySelector(".sortable-report-table");
        if (productTable?.dataset.sortColumn) {
            sortReportTable(
                productTable,
                Number(productTable.dataset.sortColumn),
                productTable.dataset.sortDirection || "asc"
            );
        }

        if (productMetricsGenerated) {
            renderProductLevelMetrics();
        }
    };

    if (combineProductCodes) {
        combineProductCodes.addEventListener("change", () => {
            if (!productView.hidden) {
                buildProductRows();
            }
        });
    }

    if (productSmartFilter) {
        productSmartFilter.addEventListener("input", () => {
            if (!productView.hidden) {
                buildProductRows();
            }
        });
    }

    if (generateProductMetricsButton) {
        generateProductMetricsButton.addEventListener("click", () => {
            productMetricsGenerated = true;
            renderProductLevelMetrics();
        });
    }

    if (includeMidTierPrice) {
        includeMidTierPrice.addEventListener("change", () => {
            syncMidTierPriceInput();

            if (productMetricsGenerated) {
                renderProductLevelMetrics();
            }
        });
    }

    [productListPriceInput, productMidPriceInput, productVolumePriceInput].forEach((input) => {
        if (!input) {
            return;
        }

        input.addEventListener("input", () => {
            if (productMetricsGenerated) {
                renderProductLevelMetrics();
            }
        });
    });

    syncMidTierPriceInput();

    button.addEventListener("click", () => {
        if (!productView.hidden) {
            showReportView("invoice");
            return;
        }

        buildProductRows();
        showReportView("product");
    });
}

function showReportView(name) {
    const invoiceView = document.getElementById("invoice-view");
    const productView = document.getElementById("product-view");
    const profitabilityView = document.getElementById("job-profitability-view");
    const calendarView = document.getElementById("calendar-view");
    const productButton = document.getElementById("product-view-button");
    const profitabilityButton = document.getElementById("job-profitability-view-button");
    const calendarButton = document.getElementById("calendar-view-button");

    if (invoiceView) {
        invoiceView.hidden = name !== "invoice";
    }
    if (productView) {
        productView.hidden = name !== "product";
    }
    if (profitabilityView) {
        profitabilityView.hidden = name !== "profitability";
    }
    if (calendarView) {
        calendarView.hidden = name !== "calendar";
    }
    if (productButton) {
        productButton.textContent = name === "product" ? "Invoice View" : "Product View";
    }
    if (profitabilityButton) {
        profitabilityButton.textContent = name === "profitability" ? "Invoice View" : "Job Profitability View";
    }
    if (calendarButton) {
        calendarButton.textContent = name === "calendar" ? "Invoice View" : "Calendar View";
    }
}

function escapeReportHtml(value) {
    const element = document.createElement("div");
    element.textContent = value ?? "";
    return element.innerHTML;
}

function capitalizeWord(value) {
    const text = String(value || "");
    return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

function formatDatetimeLabel(value) {
    if (!value) {
        return "";
    }

    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
        return value;
    }

    return parsed.toLocaleString("en-AU", {
        weekday: "short",
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit"
    });
}

function staffStatusMessage(status) {
    if (status === "diy_pickup") {
        return "DIY/Pickup job — customer collects and returns, no staff required.";
    }

    if (status === "needs_datetime") {
        return "No staff matched yet — resolve the install/removal datetime first.";
    }

    if (status === "no_match") {
        return "No timesheet shifts matched this job's datetimes.";
    }

    return "No staff allocated.";
}

function setDatetimeCell(cell, value, ok, invoiceId) {
    if (!cell) {
        return;
    }

    cell.dataset.sortValue = value || "";
    cell.innerHTML = "";

    if (value && ok) {
        cell.textContent = formatDatetimeLabel(value);
        return;
    }

    if (value) {
        const partial = document.createElement("span");
        partial.className = "datetime-partial";
        partial.textContent = value;
        cell.appendChild(partial);
    }

    const button = document.createElement("button");
    button.type = "button";
    button.className = "ai-parse-datetime report-view-button";
    button.dataset.invoiceId = invoiceId;
    button.textContent = "Parse with AI";
    cell.appendChild(button);
}

function renderStaffRow(staffRow, data) {
    const cell = staffRow?.querySelector("td");
    if (!cell) {
        return;
    }

    const allocations = data.staff_allocations || [];
    if (allocations.length === 0) {
        cell.innerHTML = `<p class="staff-allocations-empty">${escapeReportHtml(staffStatusMessage(data.staff_status))}</p>`;
        return;
    }

    const rows = allocations.map((allocation) => `
        <tr>
            <td>${escapeReportHtml(allocation.name)}</td>
            <td>${escapeReportHtml(capitalizeWord(allocation.kind))}</td>
            <td>${escapeReportHtml(allocation.shift_span)}</td>
            <td>${Number(allocation.hours || 0).toFixed(2)}</td>
        </tr>
    `).join("");

    cell.innerHTML = `
        <table class="invoice-line-items-table staff-allocations-table">
            <thead>
                <tr>
                    <th>Staff</th>
                    <th>Event</th>
                    <th>Shift Span</th>
                    <th>Allocated Hours</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    `;
}

function applyDatetimeResult(container, invoiceId, data) {
    const selector = `[data-invoice-id="${invoiceId}"]`;
    const invoiceRow = container.querySelector(`tr.profitability-invoice-row${selector}`);
    const staffRow = container.querySelector(`tr.profitability-staff-row${selector}`);

    if (invoiceRow) {
        setDatetimeCell(invoiceRow.querySelector(".datetime-install"), data.install_datetime, data.install_ok, invoiceId);
        setDatetimeCell(invoiceRow.querySelector(".datetime-removal"), data.removal_datetime, data.removal_ok, invoiceId);
    }

    if (staffRow) {
        renderStaffRow(staffRow, data);
    }
}

function setupAiParseQueue(container) {
    const queue = [];
    let processing = false;

    const processNext = async () => {
        if (processing || queue.length === 0) {
            return;
        }

        processing = true;
        const button = queue.shift();
        const invoiceId = button.dataset.invoiceId;
        button.disabled = true;
        button.textContent = "Parsing…";

        try {
            const response = await fetch(`/invoices/${encodeURIComponent(invoiceId)}/parse-datetimes`, {
                method: "POST"
            });

            if (!response.ok) {
                const errorBody = await response.json().catch(() => ({}));
                throw new Error(errorBody.error || `Request failed (${response.status})`);
            }

            const data = await response.json();
            applyDatetimeResult(container, invoiceId, data);
        } catch (error) {
            console.error("AI datetime parse failed:", error);
            button.disabled = false;
            button.textContent = "Retry AI";
            button.title = error.message || "AI parse failed";
        } finally {
            processing = false;
            processNext();
        }
    };

    container.addEventListener("click", (event) => {
        const button = event.target.closest(".ai-parse-datetime");
        if (!button || button.disabled || !container.contains(button)) {
            return;
        }

        queue.push(button);
        processNext();
    });
}

function setupJobProfitabilityView() {
    const button = document.getElementById("job-profitability-view-button");
    const view = document.getElementById("job-profitability-view");

    if (!button || !view) {
        return;
    }

    button.addEventListener("click", () => {
        showReportView(view.hidden ? "profitability" : "invoice");
    });

    setupAiParseQueue(view);
}

function setupCalendarView() {
    const button = document.getElementById("calendar-view-button");
    const view = document.getElementById("calendar-view");

    if (!button || !view) {
        return;
    }

    const grid = document.getElementById("calendar-grid");
    const monthLabel = document.getElementById("calendar-month-label");
    const monthSelect = document.getElementById("calendar-month-select");
    const prevButton = document.getElementById("calendar-prev");
    const nextButton = document.getElementById("calendar-next");
    const detailsPanel = document.getElementById("calendar-day-details");
    const dataElement = document.getElementById("calendar-events-data");

    let rawEvents = [];
    try {
        rawEvents = JSON.parse(dataElement?.textContent || "[]");
    } catch (error) {
        console.error("Unable to parse calendar events:", error);
        rawEvents = [];
    }

    const pad = (value) => String(value).padStart(2, "0");
    const toDayKey = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
    const toMonthKey = (year, month) => `${year}-${pad(month + 1)}`;
    const weekdayNames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

    const formatCurrency = (value) => new Intl.NumberFormat("en-AU", {
        style: "currency",
        currency: "AUD"
    }).format(Number(value) || 0);

    const formatTime = (date) => date.toLocaleTimeString("en-AU", {
        hour: "numeric",
        minute: "2-digit"
    });

    const eventsByDay = new Map();
    const monthsWithEvents = new Set();

    rawEvents.forEach((event) => {
        if (event.type !== "install" && event.type !== "removal") {
            return;
        }

        const date = new Date(event.datetime);
        if (Number.isNaN(date.getTime())) {
            return;
        }

        const dayKey = toDayKey(date);
        if (!eventsByDay.has(dayKey)) {
            eventsByDay.set(dayKey, []);
        }

        eventsByDay.get(dayKey).push({ ...event, date });
        monthsWithEvents.add(toMonthKey(date.getFullYear(), date.getMonth()));
    });

    const sortedMonths = Array.from(monthsWithEvents).sort();
    let current;

    if (sortedMonths.length > 0) {
        const [year, month] = sortedMonths[0].split("-").map(Number);
        current = { year, month: month - 1 };
    } else {
        const now = new Date();
        current = { year: now.getFullYear(), month: now.getMonth() };
    }

    let selectedDayKey = null;

    if (monthSelect) {
        monthSelect.innerHTML = "";

        if (sortedMonths.length === 0) {
            const option = document.createElement("option");
            option.textContent = "No dated jobs";
            monthSelect.appendChild(option);
            monthSelect.disabled = true;
        } else {
            sortedMonths.forEach((key) => {
                const [year, month] = key.split("-").map(Number);
                const option = document.createElement("option");
                option.value = key;
                option.textContent = new Date(year, month - 1, 1).toLocaleDateString("en-AU", {
                    month: "long",
                    year: "numeric"
                });
                monthSelect.appendChild(option);
            });
        }
    }

    const renderDetailsEmpty = () => {
        if (detailsPanel) {
            detailsPanel.innerHTML = `<p class="calendar-details-empty">Select a day to see its installs and removals.</p>`;
        }
    };

    const buildDetailsSection = (title, className, list) => {
        if (list.length === 0) {
            return "";
        }

        const rows = list.map((event) => {
            const estimated = event.ok
                ? ""
                : `<span class="calendar-estimated" title="Estimated from text — confirm before relying on it">est.</span>`;
            const link = event.url
                ? `<a class="report-view-button calendar-invoice-link" href="${escapeReportHtml(event.url)}" target="_blank" rel="noopener">View</a>`
                : "";

            return `
                <tr>
                    <td>${escapeReportHtml(formatTime(event.date))}${estimated}</td>
                    <td>${escapeReportHtml(event.invoiceNumber || "")}</td>
                    <td>${escapeReportHtml(event.customer || "")}</td>
                    <td>${escapeReportHtml(event.job || "")}</td>
                    <td>${escapeReportHtml(formatCurrency(event.amount))}</td>
                    <td>${link}</td>
                </tr>
            `;
        }).join("");

        return `
            <div class="calendar-details-section">
                <h4 class="calendar-details-heading ${className}">${escapeReportHtml(title)} (${list.length})</h4>
                <table class="invoice-line-items-table calendar-details-table">
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Invoice</th>
                            <th>Customer</th>
                            <th>Job</th>
                            <th>Amount Ex Tax</th>
                            <th>View</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        `;
    };

    const renderDetails = (dayKey) => {
        if (!detailsPanel) {
            return;
        }

        const dayEvents = (eventsByDay.get(dayKey) || []).slice().sort((left, right) => left.date - right.date);
        if (dayEvents.length === 0) {
            renderDetailsEmpty();
            return;
        }

        const [year, month, day] = dayKey.split("-").map(Number);
        const heading = new Date(year, month - 1, day).toLocaleDateString("en-AU", {
            weekday: "long",
            day: "numeric",
            month: "long",
            year: "numeric"
        });
        const installs = dayEvents.filter((event) => event.type === "install");
        const removals = dayEvents.filter((event) => event.type === "removal");

        detailsPanel.innerHTML = `
            <h3 class="calendar-details-title">${escapeReportHtml(heading)}</h3>
            ${buildDetailsSection("Installs", "install", installs)}
            ${buildDetailsSection("Removals", "removal", removals)}
        `;
    };

    const render = () => {
        if (!grid) {
            return;
        }

        grid.innerHTML = "";

        if (monthLabel) {
            monthLabel.textContent = new Date(current.year, current.month, 1).toLocaleDateString("en-AU", {
                month: "long",
                year: "numeric"
            });
        }

        if (monthSelect && !monthSelect.disabled) {
            const key = toMonthKey(current.year, current.month);
            if (monthsWithEvents.has(key)) {
                monthSelect.value = key;
            }
        }

        weekdayNames.forEach((name) => {
            const head = document.createElement("div");
            head.className = "calendar-weekday";
            head.textContent = name;
            grid.appendChild(head);
        });

        const firstOfMonth = new Date(current.year, current.month, 1);
        const startOffset = (firstOfMonth.getDay() + 6) % 7;
        const daysInMonth = new Date(current.year, current.month + 1, 0).getDate();
        const todayKey = toDayKey(new Date());

        for (let index = 0; index < startOffset; index += 1) {
            const blank = document.createElement("div");
            blank.className = "calendar-day is-blank";
            grid.appendChild(blank);
        }

        for (let day = 1; day <= daysInMonth; day += 1) {
            const date = new Date(current.year, current.month, day);
            const dayKey = toDayKey(date);
            const dayEvents = eventsByDay.get(dayKey) || [];
            const installCount = dayEvents.filter((event) => event.type === "install").length;
            const removalCount = dayEvents.filter((event) => event.type === "removal").length;

            const cell = document.createElement("div");
            cell.className = "calendar-day";
            cell.dataset.dayKey = dayKey;

            if (dayEvents.length > 0) {
                cell.classList.add("has-events");
            }
            if (dayKey === todayKey) {
                cell.classList.add("is-today");
            }
            if (dayKey === selectedDayKey) {
                cell.classList.add("is-selected");
            }

            const number = document.createElement("div");
            number.className = "calendar-day-number";
            number.textContent = String(day);
            cell.appendChild(number);

            if (installCount > 0) {
                const pill = document.createElement("span");
                pill.className = "calendar-pill install";
                pill.textContent = `${installCount} install${installCount > 1 ? "s" : ""}`;
                cell.appendChild(pill);
            }

            if (removalCount > 0) {
                const pill = document.createElement("span");
                pill.className = "calendar-pill removal";
                pill.textContent = `${removalCount} removal${removalCount > 1 ? "s" : ""}`;
                cell.appendChild(pill);
            }

            if (dayEvents.length > 0) {
                cell.tabIndex = 0;
                cell.setAttribute("role", "button");

                const activate = () => {
                    selectedDayKey = dayKey;
                    grid.querySelectorAll(".calendar-day.is-selected").forEach((element) => {
                        element.classList.remove("is-selected");
                    });
                    cell.classList.add("is-selected");
                    renderDetails(dayKey);
                };

                cell.addEventListener("click", activate);
                cell.addEventListener("keydown", (event) => {
                    if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        activate();
                    }
                });
            }

            grid.appendChild(cell);
        }

        if (selectedDayKey && selectedDayKey.startsWith(toMonthKey(current.year, current.month))) {
            renderDetails(selectedDayKey);
        } else {
            renderDetailsEmpty();
        }
    };

    if (prevButton) {
        prevButton.addEventListener("click", () => {
            const target = new Date(current.year, current.month - 1, 1);
            current = { year: target.getFullYear(), month: target.getMonth() };
            render();
        });
    }

    if (nextButton) {
        nextButton.addEventListener("click", () => {
            const target = new Date(current.year, current.month + 1, 1);
            current = { year: target.getFullYear(), month: target.getMonth() };
            render();
        });
    }

    if (monthSelect) {
        monthSelect.addEventListener("change", () => {
            if (!monthSelect.value) {
                return;
            }

            const [year, month] = monthSelect.value.split("-").map(Number);
            current = { year, month: month - 1 };
            render();
        });
    }

    render();

    button.addEventListener("click", () => {
        showReportView(view.hidden ? "calendar" : "invoice");
    });
}

function startBackgroundSync() {
    // Show the spinner and status
    document.getElementById("sync-status").style.display = "inline-flex";
    document.getElementById("spinner").style.display = "inline-block";
    document.getElementById("sync-text").textContent = "Background Sync Ongoing";

    // Send the refresh request
    fetch('/refresh')
        .then(response => {
            if (response.ok) {
                pollSyncStatus(); // Start polling the sync status
            } else {
                handleSyncError();
            }
        })
        .catch(handleSyncError);
}

function pollSyncStatus() {
    const syncText = document.getElementById("sync-text");
    const spinner = document.getElementById("spinner");

    const interval = setInterval(() => {
        fetch('/sync-status')
            .then(response => response.json())
            .then(data => {
                if (!data.ongoing) {
                    clearInterval(interval); // Stop polling
                    spinner.style.display = "none"; // Hide the spinner
                    syncText.innerHTML = "😊 Background Sync Completed!";
                }
            })
            .catch(error => {
                console.error('Error checking sync status:', error);
                clearInterval(interval); // Stop polling on error
                spinner.style.display = "none";
                syncText.textContent = "Background Sync Failed!";
            });
    }, 1000); // Poll every second
}

function handleSyncError() {
    const syncText = document.getElementById("sync-text");
    const spinner = document.getElementById("spinner");
    spinner.style.display = "none";
    syncText.textContent = "Background Sync Failed!";
}
