// Telegram Book Search Agent - Frontend Logic

let currentTab = "tab-dashboard";
let batchPollInterval = null;
let currentCandidates = [];

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
    setupNavigation();
    checkTelegramStatus();
    loadDashboardStats();
    loadSettings();

    // Start polling status periodically
    setInterval(checkTelegramStatus, 5000);
    setInterval(updateBatchStatus, 2000);
});

// Navigation
function setupNavigation() {
    document.querySelectorAll(".nav-link").forEach(link => {
        link.addEventListener("click", () => {
            const tabId = link.getAttribute("data-tab");
            switchTab(tabId);
        });
    });
}

function switchTab(tabId) {
    document.querySelectorAll(".nav-link").forEach(l => l.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));

    const activeLink = document.querySelector(`.nav-link[data-tab="${tabId}"]`);
    const activePanel = document.getElementById(tabId);

    if (activeLink) activeLink.classList.add("active");
    if (activePanel) activePanel.classList.add("active");

    currentTab = tabId;
    const titleMap = {
        "tab-dashboard": "Dashboard Overview",
        "tab-books": "Book Queue Management",
        "tab-sources": "Authorized Telegram Sources",
        "tab-search": "Single Book Test Search",
        "tab-batch": "Batch Search Controller",
        "tab-orthodox": "Orthodox Harvester (ኦርቶዶክስ መጽሐፍት ማሰባሰቢያ)",
        "tab-history": "Processing History",
        "tab-settings": "Agent Settings",
        "tab-logs": "Application Logs"
    };
    document.getElementById("page-title").innerText = titleMap[tabId] || "Dashboard";

    // Refresh content for active tab
    refreshCurrentTab();
}

function refreshCurrentTab() {
    if (currentTab === "tab-dashboard") loadDashboardStats();
    else if (currentTab === "tab-books") loadBooks();
    else if (currentTab === "tab-sources") loadSources();
    else if (currentTab === "tab-orthodox") loadOrthodoxStatus();
    else if (currentTab === "tab-history") loadHistory();
    else if (currentTab === "tab-settings") loadSettings();
    else if (currentTab === "tab-logs") loadLogs();
}

// --- 1. Telegram Status & Authentication ---
async function checkTelegramStatus() {
    try {
        const res = await fetch("/api/telegram/status");
        const data = await res.json();
        
        const dot = document.getElementById("tg-status-dot");
        const text = document.getElementById("tg-status-text");
        const user = document.getElementById("tg-status-user");
        const btn = document.getElementById("btn-tg-action");

        dot.className = "status-dot";

        if (data.is_authorized && data.state === "connected") {
            dot.classList.add("connected");
            text.innerText = "🟢 Connected";
            const u = data.user || {};
            const name = u.first_name ? `${u.first_name} ${u.last_name || ""}` : (u.username ? `@${u.username}` : "Authorized User");
            user.innerText = name;
            btn.innerText = "Manage";
        } else if (data.state === "awaiting_code" || data.state === "awaiting_password") {
            dot.classList.add("awaiting");
            text.innerText = "🟡 Awaiting Auth";
            user.innerText = "Verification required";
            btn.innerText = "Enter Code";
        } else {
            text.innerText = "🔴 Disconnected";
            user.innerText = "No Telegram connection";
            btn.innerText = "Connect";
        }
    } catch (e) {
        console.error("Failed to check Telegram status", e);
    }
}

function openAuthModal() {
    document.getElementById("auth-modal").classList.add("active");
    // Check if connected to show disconnect option
    fetch("/api/telegram/status").then(r => r.json()).then(data => {
        const disBtn = document.getElementById("modal-btn-disconnect");
        if (data.is_authorized) {
            disBtn.style.display = "block";
            document.getElementById("modal-btn-connect").innerText = "Re-connect";
        } else {
            disBtn.style.display = "none";
            document.getElementById("modal-btn-connect").innerText = "Send Verification Code";
        }
    });
}

function closeAuthModal() {
    document.getElementById("auth-modal").classList.remove("active");
    resetAuthModal();
}

function resetAuthModal() {
    document.getElementById("auth-step-credentials").style.display = "block";
    document.getElementById("auth-step-code").style.display = "none";
    document.getElementById("auth-step-password").style.display = "none";
}

async function submitTelegramConnect() {
    const api_id = document.getElementById("modal-api-id").value.trim();
    const api_hash = document.getElementById("modal-api-hash").value.trim();
    const phone = document.getElementById("modal-phone").value.trim();

    if (!api_id || !api_hash || !phone) {
        alert("Please provide Telegram API ID, API Hash, and Phone Number.");
        return;
    }

    try {
        const res = await fetch("/api/telegram/connect", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ api_id: parseInt(api_id), api_hash, phone })
        });
        const data = await res.json();
        if (data.success) {
            if (data.status === "already_authorized") {
                alert("Account already connected and authorized!");
                closeAuthModal();
                checkTelegramStatus();
            } else {
                document.getElementById("auth-step-credentials").style.display = "none";
                document.getElementById("auth-step-code").style.display = "block";
            }
        } else {
            alert(data.error || "Failed to start Telegram login.");
        }
    } catch (e) {
        alert("Error connecting to Telegram backend: " + e);
    }
}

async function submitTelegramCode() {
    const code = document.getElementById("modal-code").value.trim();
    if (!code) {
        alert("Please enter the verification code.");
        return;
    }

    try {
        const res = await fetch("/api/telegram/submit-code", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ code })
        });
        const data = await res.json();
        if (data.success) {
            if (data.status === "password_needed") {
                document.getElementById("auth-step-code").style.display = "none";
                document.getElementById("auth-step-password").style.display = "block";
            } else {
                alert("Telegram account connected successfully!");
                closeAuthModal();
                checkTelegramStatus();
                discoverSources(); // Auto-discover after login
            }
        } else {
            alert(data.error || "Invalid verification code.");
        }
    } catch (e) {
        alert("Error verifying code: " + e);
    }
}

async function submitTelegramPassword() {
    const password = document.getElementById("modal-password").value;
    if (!password) {
        alert("Please enter your 2FA password.");
        return;
    }

    try {
        const res = await fetch("/api/telegram/submit-password", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ password })
        });
        const data = await res.json();
        if (data.success) {
            alert("Two-Factor Authentication successful! Telegram Connected.");
            closeAuthModal();
            checkTelegramStatus();
            discoverSources();
        } else {
            alert(data.error || "Invalid 2FA password.");
        }
    } catch (e) {
        alert("Error verifying 2FA: " + e);
    }
}

async function disconnectTelegram() {
    if (!confirm("Are you sure you want to disconnect your Telegram session?")) return;
    try {
        await fetch("/api/telegram/disconnect", { method: "POST" });
        alert("Telegram session disconnected.");
        closeAuthModal();
        checkTelegramStatus();
    } catch (e) {
        alert("Error disconnecting: " + e);
    }
}

// --- 2. Dashboard Stats ---
async function loadDashboardStats() {
    try {
        const [booksRes, histRes, batchRes] = await Promise.all([
            fetch("/api/books").then(r => r.json()),
            fetch("/api/history").then(r => r.json()),
            fetch("/api/batch/status").then(r => r.json())
        ]);

        const total = booksRes.length || 0;
        let sentCount = 0;
        let reviewCount = 0;
        let notFoundCount = 0;

        booksRes.forEach(b => {
            if (b.status === "sent") sentCount++;
            else if (b.status === "review_required") reviewCount++;
            else if (b.status === "not_found") notFoundCount++;
        });

        document.getElementById("stat-total").innerText = total;
        document.getElementById("stat-sent").innerText = sentCount;
        document.getElementById("stat-review").innerText = reviewCount;
        document.getElementById("stat-notfound").innerText = notFoundCount;
        document.getElementById("stat-duplicates").innerText = batchRes.stats?.skipped_duplicates || 0;
        document.getElementById("badge-total-books").innerText = total;

        // Update live batch card
        const badge = document.getElementById("dash-batch-badge");
        if (batchRes.is_running) {
            badge.innerText = batchRes.is_paused ? "PAUSED" : "RUNNING";
            badge.className = batchRes.is_paused ? "badge badge-warning" : "badge badge-success";
        } else {
            badge.innerText = "IDLE";
            badge.className = "badge badge-secondary";
        }

        document.getElementById("dash-current-title").innerText = batchRes.current_title ? `Searching: ${batchRes.current_title}` : "No search running";
        document.getElementById("dash-progress-label").innerText = `${batchRes.progress_percent || 0}%`;
        document.getElementById("dash-progress-bar").style.width = `${batchRes.progress_percent || 0}%`;

    } catch (e) {
        console.error("Error loading dashboard stats", e);
    }
}

// --- 3. Books Management ---
function setAddMode(mode) {
    document.getElementById("form-add-batch").style.display = mode === "batch" ? "block" : "none";
    document.getElementById("form-add-single").style.display = mode === "single" ? "block" : "none";
    document.getElementById("form-add-file").style.display = mode === "file" ? "block" : "none";

    document.getElementById("btn-mode-batch").className = mode === "batch" ? "btn btn-primary" : "btn btn-secondary";
    document.getElementById("btn-mode-single").className = mode === "single" ? "btn btn-primary" : "btn btn-secondary";
    document.getElementById("btn-mode-file").className = mode === "file" ? "btn btn-primary" : "btn btn-secondary";
}

async function submitBatchBooks() {
    const text = document.getElementById("input-batch-text").value.trim();
    if (!text) return alert("Please enter at least one book title.");

    try {
        const res = await fetch("/api/books/batch-text", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text })
        });
        const data = await res.json();
        if (data.success) {
            alert(`Added ${data.count} books to the queue.`);
            document.getElementById("input-batch-text").value = "";
            loadBooks();
            loadDashboardStats();
        }
    } catch (e) {
        alert("Error adding books: " + e);
    }
}

async function submitSingleBook() {
    const title = document.getElementById("input-single-title").value.trim();
    const author = document.getElementById("input-single-author").value.trim();
    const edition = document.getElementById("input-single-edition").value.trim();
    const isbn = document.getElementById("input-single-isbn").value.trim();

    if (!title) return alert("Book title is required.");

    try {
        const res = await fetch("/api/books", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title, author, edition, isbn })
        });
        const data = await res.json();
        if (data.success) {
            alert("Book added successfully.");
            document.getElementById("input-single-title").value = "";
            document.getElementById("input-single-author").value = "";
            document.getElementById("input-single-edition").value = "";
            document.getElementById("input-single-isbn").value = "";
            loadBooks();
            loadDashboardStats();
        }
    } catch (e) {
        alert("Error adding book: " + e);
    }
}

async function submitImportFile() {
    const fileInput = document.getElementById("input-file-upload");
    if (!fileInput.files.length) return alert("Please select a .txt or .csv file.");

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    try {
        const res = await fetch("/api/books/import", {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        if (data.success) {
            alert(`Successfully imported ${data.count} books!`);
            fileInput.value = "";
            loadBooks();
            loadDashboardStats();
        } else {
            alert("Import failed: " + data.error);
        }
    } catch (e) {
        alert("Error importing file: " + e);
    }
}

async function loadBooks() {
    try {
        const res = await fetch("/api/books");
        const books = await res.json();
        const tbody = document.getElementById("books-table-body");
        tbody.innerHTML = "";

        document.getElementById("badge-total-books").innerText = books.length;

        if (!books.length) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No books in queue. Add some above!</td></tr>`;
            return;
        }

        books.forEach(b => {
            const tr = document.createElement("tr");
            let badgeClass = "badge-secondary";
            if (b.status === "sent") badgeClass = "badge-success";
            else if (b.status === "searching") badgeClass = "badge-info";
            else if (b.status === "review_required") badgeClass = "badge-warning";
            else if (b.status === "not_found") badgeClass = "badge-danger";

            tr.innerHTML = `
                <td>#${b.id}</td>
                <td><strong>${escapeHtml(b.title)}</strong></td>
                <td>${escapeHtml(b.author || "-")}</td>
                <td>${escapeHtml(b.edition || "-")}</td>
                <td><span class="badge ${badgeClass}">${b.status}</span></td>
                <td>${b.confidence ? b.confidence + "%" : "-"}</td>
                <td>
                    <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 11px;" onclick="testBookFromList('${escapeHtml(b.title)}')">🔎 Test</button>
                    <button class="btn btn-danger" style="padding: 4px 8px; font-size: 11px;" onclick="deleteBookItem(${b.id})">🗑 Delete</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Error loading books", e);
    }
}

async function deleteBookItem(bookId) {
    if (!confirm("Delete this book?")) return;
    try {
        await fetch(`/api/books/${bookId}`, { method: "DELETE" });
        loadBooks();
        loadDashboardStats();
    } catch (e) {
        alert("Error deleting book: " + e);
    }
}

async function clearBooks() {
    if (!confirm("Are you sure you want to clear ALL books from the list?")) return;
    try {
        await fetch("/api/books", { method: "DELETE" });
        loadBooks();
        loadDashboardStats();
    } catch (e) {
        alert("Error clearing books: " + e);
    }
}

function testBookFromList(title) {
    document.getElementById("test-search-title").value = title;
    switchTab("tab-search");
    runTestSearch();
}

// --- 4. Sources Management ---
async function loadSources() {
    try {
        const res = await fetch("/api/telegram/sources");
        const sources = await res.json();
        const tbody = document.getElementById("sources-table-body");
        tbody.innerHTML = "";

        document.getElementById("badge-total-sources").innerText = sources.length;

        if (!sources.length) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No sources discovered yet. Make sure your Telegram account is connected, then click 'Discover Sources'.</td></tr>`;
            return;
        }

        sources.forEach(s => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>
                    <input type="checkbox" ${s.enabled ? "checked" : ""} onchange="toggleSource(${s.chat_id}, this.checked)">
                </td>
                <td><strong>${escapeHtml(s.name)}</strong></td>
                <td>${s.username ? "@" + escapeHtml(s.username) : "-"}</td>
                <td><span class="badge badge-secondary">${s.type}</span></td>
                <td style="color: var(--text-muted); font-size: 11px;">${s.chat_id}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Error loading sources", e);
    }
}

async function discoverSources() {
    try {
        const res = await fetch("/api/telegram/sources/discover", { method: "POST" });
        const sources = await res.json();
        alert(`Discovered ${sources.length} authorized Telegram chats/channels.`);
        loadSources();
    } catch (e) {
        alert("Failed to discover sources. Ensure your Telegram account is connected.");
    }
}

async function toggleSource(chatId, enabled) {
    try {
        await fetch("/api/telegram/sources/toggle", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ chat_id: chatId, enabled })
        });
    } catch (e) {
        alert("Error toggling source: " + e);
    }
}

// --- 5. Test Search Mode ---
async function runTestSearch() {
    const title = document.getElementById("test-search-title").value.trim();
    const author = document.getElementById("test-search-author").value.trim();

    if (!title) return alert("Please enter a book title to search.");

    const btn = document.getElementById("btn-run-test-search");
    btn.disabled = true;
    btn.innerText = "Searching Telegram...";

    try {
        const res = await fetch("/api/search/test", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title, author })
        });
        const data = await res.json();
        currentCandidates = data.candidates || [];

        const panel = document.getElementById("test-results-panel");
        const countBadge = document.getElementById("test-results-count");
        const list = document.getElementById("test-candidates-list");

        panel.style.display = "block";
        countBadge.innerText = `${currentCandidates.length} candidate(s)`;
        list.innerHTML = "";

        if (!currentCandidates.length) {
            list.innerHTML = `<p style="color: var(--accent-red); font-size: 14px;">❌ No matching files found in your authorized sources.</p>`;
            return;
        }

        currentCandidates.forEach((cand, idx) => {
            const card = document.createElement("div");
            let confClass = "low-confidence";
            if (cand.confidence >= 90) confClass = "high-confidence";
            else if (cand.confidence >= 70) confClass = "medium-confidence";

            const sizeMb = (cand.file_size / (1024 * 1024)).toFixed(1);

            card.className = `candidate-card ${confClass}`;
            card.innerHTML = `
                <div class="candidate-info">
                    <div class="candidate-filename">📄 ${escapeHtml(cand.filename)}</div>
                    <div class="candidate-meta">
                        <span>Source: <strong>${escapeHtml(cand.chat_name)}</strong></span>
                        <span>Size: ${sizeMb} MB</span>
                        <span>Type: ${cand.file_type}</span>
                        <span>Msg ID: ${cand.message_id}</span>
                    </div>
                </div>
                <div style="display: flex; align-items: center; gap: 16px;">
                    <div class="candidate-score">
                        <div style="font-size: 18px; color: ${cand.confidence >= 90 ? 'var(--accent-green)' : (cand.confidence >= 70 ? 'var(--accent-yellow)' : 'var(--accent-red)')};">
                            ${cand.confidence}%
                        </div>
                        <div style="font-size: 10px; color: var(--text-muted);">Confidence</div>
                    </div>
                    <button class="btn btn-success" style="padding: 6px 12px; font-size: 12px;" onclick="sendSingleCandidate(${idx}, '${escapeHtml(title)}', '${escapeHtml(author)}')">
                        📤 Send to Saved Messages
                    </button>
                </div>
            `;
            list.appendChild(card);
        });

    } catch (e) {
        alert("Search error: " + e);
    } finally {
        btn.disabled = false;
        btn.innerText = "Search Telegram Sources";
    }
}

async function sendSingleCandidate(candidateIdx, title, author) {
    const candidate = currentCandidates[candidateIdx];
    if (!candidate) return;

    try {
        const res = await fetch("/api/search/send", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                candidate,
                requested_title: title,
                author: author || "",
                confidence: candidate.confidence,
                force_resend: true
            })
        });
        const data = await res.json();
        if (data.success) {
            alert(`✅ Sent '${candidate.filename}' to your Telegram Saved Messages!`);
            loadDashboardStats();
            loadHistory();
        } else {
            alert("Error sending file: " + data.error);
        }
    } catch (e) {
        alert("Send error: " + e);
    }
}

// --- 6. Batch Automation ---
async function startBatch() {
    try {
        const res = await fetch("/api/batch/start", { method: "POST" });
        const data = await res.json();
        if (data.success) {
            updateBatchStatus();
        } else {
            alert(data.message);
        }
    } catch (e) {
        alert("Batch start error: " + e);
    }
}

async function pauseBatch() {
    try {
        await fetch("/api/batch/pause", { method: "POST" });
        updateBatchStatus();
    } catch (e) {
        alert("Pause error: " + e);
    }
}

async function resumeBatch() {
    try {
        await fetch("/api/batch/resume", { method: "POST" });
        updateBatchStatus();
    } catch (e) {
        alert("Resume error: " + e);
    }
}

async function stopBatch() {
    try {
        await fetch("/api/batch/stop", { method: "POST" });
        updateBatchStatus();
    } catch (e) {
        alert("Stop error: " + e);
    }
}

async function updateBatchStatus() {
    try {
        const res = await fetch("/api/batch/status");
        const status = await res.json();

        // Update Controller UI
        const badge = document.getElementById("batch-status-badge");
        if (status.is_running) {
            badge.innerText = status.is_paused ? "PAUSED" : "RUNNING";
            badge.className = status.is_paused ? "badge badge-warning" : "badge badge-success";
        } else {
            badge.innerText = "IDLE";
            badge.className = "badge badge-secondary";
        }

        document.getElementById("batch-current-title").innerText = status.current_title || "None";
        document.getElementById("batch-current-index").innerText = `${status.current_index} / ${status.total_books}`;
        document.getElementById("batch-progress-bar").style.width = `${status.progress_percent}%`;

        // Update stats
        const st = status.stats || {};
        document.getElementById("batch-stat-requested").innerText = st.requested || 0;
        document.getElementById("batch-stat-found").innerText = st.found || 0;
        document.getElementById("batch-stat-sent").innerText = st.sent || 0;
        document.getElementById("batch-stat-review").innerText = st.needs_review || 0;
        document.getElementById("batch-stat-notfound").innerText = st.not_found || 0;
        document.getElementById("batch-stat-failed").innerText = st.failed || 0;

        // If batch is running or just completed, also refresh books queue
        if (currentTab === "tab-books" && status.is_running) {
            loadBooks();
        }

    } catch (e) {
        console.error("Error updating batch status", e);
    }
}

// --- 7. History & Logs ---
async function loadHistory() {
    const filter = document.getElementById("history-filter").value;
    try {
        const res = await fetch(`/api/history?status=${filter}`);
        const history = await res.json();
        const tbody = document.getElementById("history-table-body");
        tbody.innerHTML = "";

        if (!history.length) {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No history records found.</td></tr>`;
            return;
        }

        history.forEach(h => {
            const tr = document.createElement("tr");
            let badgeClass = "badge-secondary";
            if (h.status === "sent") badgeClass = "badge-success";
            else if (h.status === "not_found") badgeClass = "badge-danger";
            else if (h.status === "review_required") badgeClass = "badge-warning";

            tr.innerHTML = `
                <td style="color: var(--text-secondary); font-size: 11px;">${h.date_found || h.date_sent || "-"}</td>
                <td><strong>${escapeHtml(h.requested_title)}</strong></td>
                <td>${escapeHtml(h.filename || "-")}</td>
                <td>${escapeHtml(h.source || "Unknown")}</td>
                <td>${h.confidence ? h.confidence + "%" : "-"}</td>
                <td><span class="badge ${badgeClass}">${h.status}</span></td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Error loading history", e);
    }
}

async function loadLogs() {
    try {
        const res = await fetch("/api/logs");
        const data = await res.json();
        const box = document.getElementById("terminal-logs");
        box.innerText = data.logs.join("\n") || "No logs yet.";
        box.scrollTop = box.scrollHeight;
    } catch (e) {
        console.error("Error loading logs", e);
    }
}

// --- 8. Settings Management ---
async function loadSettings() {
    try {
        const res = await fetch("/api/settings");
        const s = await res.json();

        document.getElementById("setting-min-confidence").value = s.min_confidence ?? 90;
        document.getElementById("setting-review-threshold").value = s.review_threshold ?? 70;
        document.getElementById("setting-max-size").value = s.max_file_size_mb ?? 500;
        document.getElementById("setting-extensions").value = s.allowed_extensions ?? "pdf,epub,mobi,djvu";
        document.getElementById("setting-search-limit").value = s.search_limit_per_chat ?? 100;

        document.getElementById("setting-auto-send").checked = s.auto_send_high_confidence ?? true;
        document.getElementById("setting-ask-uncertain").checked = s.ask_uncertain ?? true;
        document.getElementById("setting-skip-duplicates").checked = s.skip_duplicates ?? true;
        document.getElementById("setting-delete-downloads").checked = s.delete_downloads_after_send ?? true;
        document.getElementById("setting-continue-errors").checked = s.continue_after_errors ?? true;

        document.getElementById("setting-weight-title").value = s.weight_title ?? 60;
        document.getElementById("setting-weight-author").value = s.weight_author ?? 25;
        document.getElementById("setting-weight-edition").value = s.weight_edition ?? 10;
        document.getElementById("setting-weight-relevance").value = s.weight_relevance ?? 5;
    } catch (e) {
        console.error("Error loading settings", e);
    }
}

async function saveSettings() {
    const settings = {
        min_confidence: parseFloat(document.getElementById("setting-min-confidence").value),
        review_threshold: parseFloat(document.getElementById("setting-review-threshold").value),
        max_file_size_mb: parseFloat(document.getElementById("setting-max-size").value),
        allowed_extensions: document.getElementById("setting-extensions").value.trim(),
        search_limit_per_chat: parseInt(document.getElementById("setting-search-limit").value),
        auto_send_high_confidence: document.getElementById("setting-auto-send").checked,
        ask_uncertain: document.getElementById("setting-ask-uncertain").checked,
        skip_duplicates: document.getElementById("setting-skip-duplicates").checked,
        delete_downloads_after_send: document.getElementById("setting-delete-downloads").checked,
        continue_after_errors: document.getElementById("setting-continue-errors").checked,
        weight_title: parseFloat(document.getElementById("setting-weight-title").value),
        weight_author: parseFloat(document.getElementById("setting-weight-author").value),
        weight_edition: parseFloat(document.getElementById("setting-weight-edition").value),
        weight_relevance: parseFloat(document.getElementById("setting-weight-relevance").value)
    };

    try {
        const res = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ settings })
        });
        const data = await res.json();
        if (data.success) {
            alert("Settings saved successfully!");
        }
    } catch (e) {
        alert("Error saving settings: " + e);
    }
}

function escapeHtml(text) {
    if (!text) return "";
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// --- 9. Orthodox Harvester ---
let orthodoxPollInterval = null;

async function startOrthodoxHarvester() {
    try {
        const res = await fetch("/api/orthodox/start", { method: "POST" });
        const data = await res.json();
        if (data.success) {
            loadOrthodoxStatus();
        } else {
            alert(data.message || "Failed to start harvester");
        }
    } catch (e) {
        console.error("Error starting orthodox harvester", e);
    }
}

async function stopOrthodoxHarvester() {
    try {
        const res = await fetch("/api/orthodox/stop", { method: "POST" });
        const data = await res.json();
        loadOrthodoxStatus();
    } catch (e) {
        console.error("Error stopping orthodox harvester", e);
    }
}

async function loadOrthodoxStatus() {
    try {
        const res = await fetch("/api/orthodox/status");
        const data = await res.json();
        
        const isRunning = data.is_running;
        const stats = data.stats || {};

        const btnStart = document.getElementById("btn-start-orthodox");
        const btnStop = document.getElementById("btn-stop-orthodox");
        const statusBadge = document.getElementById("orthodox-status-badge");
        const badgeCount = document.getElementById("badge-orthodox-forwarded");

        if (btnStart) btnStart.disabled = isRunning;
        if (btnStop) btnStop.disabled = !isRunning;

        if (statusBadge) {
            if (isRunning) {
                statusBadge.className = "badge badge-sent";
                statusBadge.innerText = "⚡ Running (Scanning & Forwarding)";
            } else {
                statusBadge.className = "badge badge-pending";
                statusBadge.innerText = "Idle (Paused)";
            }
        }

        if (badgeCount) badgeCount.innerText = stats.forwarded || 0;

        const statAnalyzed = document.getElementById("orthodox-stat-analyzed");
        const statForwarded = document.getElementById("orthodox-stat-forwarded");
        const statRejected = document.getElementById("orthodox-stat-rejected");
        const statDuplicates = document.getElementById("orthodox-stat-duplicates");
        const currentSource = document.getElementById("orthodox-current-source");
        const lastSent = document.getElementById("orthodox-last-sent");

        if (statAnalyzed) statAnalyzed.innerText = stats.analyzed || 0;
        if (statForwarded) statForwarded.innerText = stats.forwarded || 0;
        if (statRejected) statRejected.innerText = stats.rejected || 0;
        if (statDuplicates) statDuplicates.innerText = stats.duplicates || 0;
        if (currentSource) currentSource.innerText = stats.current_channel || "-";
        if (lastSent) lastSent.innerText = stats.last_forwarded || "-";

    } catch (e) {
        console.error("Error loading orthodox status", e);
    }
}

// Global Poller
setInterval(() => {
    if (currentTab === "tab-orthodox") {
        loadOrthodoxStatus();
    }
}, 2000);

