(function () {
    "use strict";

    // ------------------------------------------------------------------ Config
    var ITEMS_PER_PAGE = 48;
    var DEBOUNCE_MS = 200;

    // ------------------------------------------------------------------ State
    var state = {
        repos: [],
        filtered: [],
        query: "",
        category: "all",
        language: "all",
        minHealth: 0,
        sortKey: "stars",
        sortDir: "desc",
        view: "grid",
        page: 1
    };

    // ------------------------------------------------------- Language colors
    var LANG_COLORS = {
        "JavaScript": "#f1e05a",
        "Python": "#3572A5",
        "TypeScript": "#2b7489",
        "Java": "#b07219",
        "C++": "#f34b7d",
        "C": "#555555",
        "Go": "#00ADD8",
        "Rust": "#dea584",
        "Ruby": "#701516",
        "PHP": "#4F5D95",
        "C#": "#178600",
        "Swift": "#F05138",
        "Kotlin": "#A97BFF",
        "Shell": "#89e051",
        "Dart": "#00B4AB",
        "Lua": "#000080",
        "Haskell": "#5e5086",
        "Scala": "#c22d40",
        "Elixir": "#6e4a7e",
        "Clojure": "#db5855",
        "Erlang": "#B83998",
        "R": "#198CE7",
        "Vim Script": "#199f4b",
        "Makefile": "#427819",
        "HTML": "#e34c26",
        "CSS": "#563d7c",
        "Jupyter Notebook": "#DA5B0B",
        "TeX": "#3D6117",
        "Objective-C": "#438eff",
        "Perl": "#0298c3",
        "PowerShell": "#012456",
        "OCaml": "#3be133",
        "Julia": "#a270ba",
        "F#": "#b845fc",
        "Nim": "#ffc200",
        "Zig": "#ec915c",
        "Crystal": "#000100",
        "V": "#4f87c4",
        "Nix": "#7e7eff"
    };

    // ---------------------------------------------------------------- DOM refs
    var els = {};

    function cacheDom() {
        var refs = document.querySelectorAll("[data-ref]");
        for (var i = 0; i < refs.length; i++) {
            els[refs[i].getAttribute("data-ref")] = refs[i];
        }
        els.searchInput = document.getElementById("search-input");
        els.filterCategory = document.getElementById("filter-category");
        els.filterLanguage = document.getElementById("filter-language");
        els.filterHealth = document.getElementById("filter-health");
        els.sortSelect = document.getElementById("sort-select");
    }

    // ------------------------------------------------------------------- Init
    function init() {
        cacheDom();
        bindEvents();
        loadData();
    }

    // -------------------------------------------------------------- Data load
    function loadData() {
        els["repo-grid"].innerHTML = '<div class="av-loading">Loading repository data...</div>';

        fetch("data/repos.json")
            .then(function (r) {
                if (!r.ok) throw new Error("Failed to load data");
                return r.json();
            })
            .then(function (data) {
                state.repos = data.repos || [];
                populateFilters(data);
                updateGlobalStats(data);
                restoreFromHash();
                applyAndRender();
            })
            .catch(function () {
                els["repo-grid"].innerHTML = '<div class="av-empty"><div class="av-empty-title">Could not load data</div><p>Run the data pipeline or check data/repos.json</p></div>';
            });
    }

    // --------------------------------------------------- Populate filter menus
    function populateFilters(data) {
        var cats = data.categories || [];
        for (var i = 0; i < cats.length; i++) {
            var opt = document.createElement("option");
            opt.value = cats[i].id;
            opt.textContent = cats[i].name + " (" + cats[i].count + ")";
            els.filterCategory.appendChild(opt);
        }

        var langs = data.languages || [];
        for (var j = 0; j < langs.length; j++) {
            var lo = document.createElement("option");
            lo.value = langs[j].name;
            lo.textContent = langs[j].name + " (" + langs[j].count + ")";
            els.filterLanguage.appendChild(lo);
        }
    }

    // ----------------------------------------------------------- Global stats
    function updateGlobalStats(data) {
        var meta = data.meta || {};
        els["stat-total"].textContent = formatNum(meta.total_repos || state.repos.length);
        els["stat-categories"].textContent = (data.categories || []).length;

        var totalHealth = 0;
        var activeCount = 0;
        for (var i = 0; i < state.repos.length; i++) {
            totalHealth += state.repos[i].health || 0;
            if (state.repos[i].commits_90d > 0) activeCount++;
        }
        var avgHealth = state.repos.length ? Math.round(totalHealth / state.repos.length) : 0;
        els["stat-avg-health"].textContent = avgHealth;
        els["stat-active"].textContent = formatNum(activeCount);

        if (meta.last_updated) {
            els["last-updated"].textContent = "Updated " + relativeTime(meta.last_updated);
        }
    }

    // -------------------------------------------------------------- Search
    // Supports: * (wildcard), | (or), & or space (and), case-insensitive
    var searchTokens = null;

    function buildSearchIndex() {
        searchTokens = new Array(state.repos.length);
        for (var i = 0; i < state.repos.length; i++) {
            var r = state.repos[i];
            searchTokens[i] = (
                (r.full_name || "") + " " +
                (r.name || "") + " " +
                (r.description || "") + " " +
                (r.topics || []).join(" ") + " " +
                (r.language || "") + " " +
                (r.owner || "") + " " +
                (r.category || "")
            ).toLowerCase();
        }
    }

    function search(query) {
        if (!searchTokens) buildSearchIndex();
        if (!query) return state.repos.slice();

        // & is explicit AND (same as space)
        var normalized = query.replace(/&/g, " ");
        // Split on | for OR groups
        var orGroups = normalized.split("|");
        var results = [];

        for (var i = 0; i < state.repos.length; i++) {
            var haystack = searchTokens[i];
            var matched = false;

            for (var g = 0; g < orGroups.length; g++) {
                var terms = orGroups[g].trim().toLowerCase().split(/\s+/).filter(Boolean);
                if (terms.length === 0) continue;
                var allMatch = true;

                for (var t = 0; t < terms.length; t++) {
                    // Escape regex specials except *, convert * to .*
                    var pattern = terms[t]
                        .replace(/[.+?^${}()[\]\\]/g, "\\$&")
                        .replace(/\*/g, ".*");
                    try {
                        if (!new RegExp(pattern).test(haystack)) {
                            allMatch = false;
                            break;
                        }
                    } catch (e) {
                        if (haystack.indexOf(terms[t]) === -1) {
                            allMatch = false;
                            break;
                        }
                    }
                }

                if (allMatch) {
                    matched = true;
                    break;
                }
            }

            if (matched) results.push(state.repos[i]);
        }
        return results;
    }

    // ------------------------------------------------------------- Filtering
    function applyFilters(repos) {
        var out = [];
        for (var i = 0; i < repos.length; i++) {
            var r = repos[i];
            if (state.category !== "all" && r.category !== state.category) continue;
            if (state.language !== "all" && r.language !== state.language) continue;
            if ((r.health || 0) < state.minHealth) continue;
            out.push(r);
        }
        return out;
    }

    // -------------------------------------------------------------- Sorting
    function sortRepos(repos) {
        var key = state.sortKey;
        var dir = state.sortDir === "desc" ? -1 : 1;

        return repos.slice().sort(function (a, b) {
            var va = a[key];
            var vb = b[key];
            if (va == null) va = "";
            if (vb == null) vb = "";
            if (typeof va === "string" && typeof vb === "string") {
                return dir * va.localeCompare(vb);
            }
            return dir * ((va || 0) - (vb || 0));
        });
    }

    // ---------------------------------------------------- Apply and render
    function applyAndRender() {
        var results = search(state.query);
        results = applyFilters(results);
        results = sortRepos(results);
        state.filtered = results;
        state.page = 1;
        render();
        saveToHash();
    }

    function render() {
        renderResultsInfo();
        if (state.view === "grid") {
            renderGrid();
            els["repo-grid"].hidden = false;
            els["repo-table-wrap"].hidden = true;
        } else {
            renderTable();
            els["repo-grid"].hidden = true;
            els["repo-table-wrap"].hidden = false;
        }
        renderPagination();
        updateViewButtons();
    }

    // ------------------------------------------------------------- Grid view
    function renderGrid() {
        var start = (state.page - 1) * ITEMS_PER_PAGE;
        var items = state.filtered.slice(start, start + ITEMS_PER_PAGE);
        var frag = document.createDocumentFragment();

        for (var i = 0; i < items.length; i++) {
            frag.appendChild(createCard(items[i]));
        }

        els["repo-grid"].textContent = "";

        if (items.length === 0) {
            els["repo-grid"].innerHTML = '<div class="av-empty"><div class="av-empty-title">No repositories found</div><p>Try adjusting your search or filters</p></div>';
            return;
        }

        els["repo-grid"].appendChild(frag);
    }

    function createCard(repo) {
        var card = document.createElement("article");
        card.className = "av-card";
        card.setAttribute("role", "listitem");

        var hColor = healthColor(repo.health);
        var langColor = LANG_COLORS[repo.language] || "";

        card.innerHTML =
            '<header class="av-card-header">' +
                (langColor ? '<span class="av-lang-dot" style="--lang-color:' + langColor + '"></span>' : '') +
                '<a href="' + escAttr(repo.url) + '" class="av-card-title" target="_blank" rel="noopener">' + esc(repo.name) + '</a>' +
                '<span class="av-card-owner">' + esc(repo.owner) + '</span>' +
            '</header>' +
            '<p class="av-card-desc">' + esc(repo.description) + '</p>' +
            '<footer class="av-card-footer">' +
                '<div class="av-card-metrics">' +
                    metric("icon-star", formatNum(repo.stars)) +
                    metric("icon-fork", formatNum(repo.forks)) +
                    metric("icon-issue", formatNum(repo.open_issues)) +
                    metric("icon-commit", repo.commits_90d + "/90d") +
                '</div>' +
                '<div class="av-health">' +
                    '<div class="av-health-track">' +
                        '<div class="av-health-bar" style="--health-pct:' + repo.health + '%;--health-color:' + hColor + '"></div>' +
                    '</div>' +
                    '<span class="av-health-score" style="--health-color:' + hColor + '">' + repo.health + '</span>' +
                '</div>' +
                '<div class="av-card-meta">' +
                    '<span class="av-card-time">' + relativeTime(repo.last_push) + '</span>' +
                    '<span class="av-badge">' + esc(categoryName(repo.category)) + '</span>' +
                    (repo.is_archived ? '<span class="av-badge av-badge--archived">Archived</span>' : '') +
                '</div>' +
            '</footer>';

        return card;
    }

    function metric(iconId, text) {
        return '<span class="av-metric"><svg class="av-icon--sm" aria-hidden="true"><use href="#' + iconId + '"/></svg> ' + esc(String(text)) + '</span>';
    }

    // ----------------------------------------------------------- Table view
    function renderTable() {
        var start = (state.page - 1) * ITEMS_PER_PAGE;
        var items = state.filtered.slice(start, start + ITEMS_PER_PAGE);
        var frag = document.createDocumentFragment();

        for (var i = 0; i < items.length; i++) {
            frag.appendChild(createTableRow(items[i]));
        }

        els["repo-table-body"].textContent = "";
        els["repo-table-body"].appendChild(frag);
    }

    function createTableRow(repo) {
        var tr = document.createElement("tr");
        var hColor = healthColor(repo.health);
        var langColor = LANG_COLORS[repo.language] || "";

        tr.innerHTML =
            '<td class="av-table-name">' +
                (langColor ? '<span class="av-lang-dot" style="--lang-color:' + langColor + '"></span>' : '') +
                '<a href="' + escAttr(repo.url) + '" target="_blank" rel="noopener">' + esc(repo.full_name) + '</a>' +
            '</td>' +
            '<td class="av-table-desc" title="' + escAttr(repo.description) + '">' + esc(repo.description) + '</td>' +
            '<td>' + formatNum(repo.stars) + '</td>' +
            '<td>' + formatNum(repo.forks) + '</td>' +
            '<td>' + formatNum(repo.open_issues) + '</td>' +
            '<td>' + esc(repo.language || "-") + '</td>' +
            '<td>' + esc(repo.license || "-") + '</td>' +
            '<td>' + repo.commits_90d + '</td>' +
            '<td>' + relativeTime(repo.last_push) + '</td>' +
            '<td><span class="av-health-score" style="--health-color:' + hColor + '">' + repo.health + '</span></td>';

        return tr;
    }

    // ---------------------------------------------------------- Results info
    function renderResultsInfo() {
        var total = state.filtered.length;
        var start = (state.page - 1) * ITEMS_PER_PAGE + 1;
        var end = Math.min(state.page * ITEMS_PER_PAGE, total);

        if (total === 0) {
            els["results-info"].textContent = "No repositories match your criteria";
        } else {
            els["results-info"].textContent = "Showing " + start + "-" + end + " of " + formatNum(total) + " repositories";
        }
    }

    // ----------------------------------------------------------- Pagination
    function renderPagination() {
        var totalPages = Math.ceil(state.filtered.length / ITEMS_PER_PAGE);
        var container = els.pagination;
        container.textContent = "";

        if (totalPages <= 1) return;

        // Previous
        container.appendChild(pageBtn("<", state.page - 1, state.page <= 1));

        // Page numbers with ellipsis
        var pages = paginationRange(state.page, totalPages);
        for (var i = 0; i < pages.length; i++) {
            if (pages[i] === "...") {
                var sp = document.createElement("span");
                sp.className = "av-pagination-ellipsis";
                sp.textContent = "...";
                container.appendChild(sp);
            } else {
                container.appendChild(pageBtn(String(pages[i]), pages[i], false, pages[i] === state.page));
            }
        }

        // Next
        container.appendChild(pageBtn(">", state.page + 1, state.page >= totalPages));
    }

    function pageBtn(label, page, disabled, active) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "av-pagination-btn" + (active ? " is-active" : "");
        btn.textContent = label;
        btn.disabled = !!disabled;
        if (!disabled && !active) {
            btn.setAttribute("data-page", page);
        }
        return btn;
    }

    function paginationRange(current, total) {
        if (total <= 7) {
            var arr = [];
            for (var i = 1; i <= total; i++) arr.push(i);
            return arr;
        }
        var pages = [1];
        var start = Math.max(2, current - 1);
        var end = Math.min(total - 1, current + 1);

        if (start > 2) pages.push("...");
        for (var j = start; j <= end; j++) pages.push(j);
        if (end < total - 1) pages.push("...");
        pages.push(total);
        return pages;
    }

    // -------------------------------------------------------- View buttons
    function updateViewButtons() {
        var gridBtn = document.querySelector('[data-action="view-grid"]');
        var tableBtn = document.querySelector('[data-action="view-table"]');
        if (gridBtn) gridBtn.setAttribute("aria-pressed", state.view === "grid" ? "true" : "false");
        if (tableBtn) tableBtn.setAttribute("aria-pressed", state.view === "table" ? "true" : "false");
    }

    // --------------------------------------------------------- Event binding
    function bindEvents() {
        // Search with debounce
        var debounceTimer = null;
        els.searchInput.addEventListener("input", function () {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(function () {
                state.query = els.searchInput.value.trim();
                applyAndRender();
            }, DEBOUNCE_MS);
        });

        // Filters
        els.filterCategory.addEventListener("change", function () {
            state.category = this.value;
            applyAndRender();
        });

        els.filterLanguage.addEventListener("change", function () {
            state.language = this.value;
            applyAndRender();
        });

        els.filterHealth.addEventListener("change", function () {
            state.minHealth = parseInt(this.value, 10) || 0;
            applyAndRender();
        });

        // Sort
        els.sortSelect.addEventListener("change", function () {
            var val = this.value;
            var lastDash = val.lastIndexOf("-");
            state.sortKey = val.substring(0, lastDash);
            state.sortDir = val.substring(lastDash + 1) || "desc";
            applyAndRender();
        });

        // View toggle
        document.addEventListener("click", function (e) {
            var btn = e.target.closest("[data-action]");
            if (!btn) return;

            var action = btn.getAttribute("data-action");

            if (action === "view-grid") {
                state.view = "grid";
                render();
                saveToHash();
            } else if (action === "view-table") {
                state.view = "table";
                render();
                saveToHash();
            }
        });

        // Pagination
        els.pagination.addEventListener("click", function (e) {
            var btn = e.target.closest("[data-page]");
            if (!btn || btn.disabled) return;
            state.page = parseInt(btn.getAttribute("data-page"), 10);
            render();
            saveToHash();
            window.scrollTo({ top: els["repo-grid"].offsetTop - 80, behavior: "smooth" });
        });

        // Hash changes (back/forward)
        window.addEventListener("hashchange", function () {
            restoreFromHash();
            applyAndRender();
        });
    }

    // -------------------------------------------------------------- URL state
    function saveToHash() {
        var params = [];
        if (state.query) params.push("q=" + encodeURIComponent(state.query));
        if (state.category !== "all") params.push("cat=" + encodeURIComponent(state.category));
        if (state.language !== "all") params.push("lang=" + encodeURIComponent(state.language));
        if (state.minHealth > 0) params.push("health=" + state.minHealth);
        if (state.sortKey !== "stars" || state.sortDir !== "desc") params.push("sort=" + state.sortKey + "-" + state.sortDir);
        if (state.view !== "grid") params.push("view=" + state.view);
        if (state.page > 1) params.push("page=" + state.page);

        var hash = params.length ? "#" + params.join("&") : "";
        if (window.location.hash !== hash) {
            history.replaceState(null, "", hash || window.location.pathname);
        }
    }

    function restoreFromHash() {
        var hash = window.location.hash.slice(1);
        if (!hash) return;

        var params = {};
        hash.split("&").forEach(function (pair) {
            var kv = pair.split("=");
            if (kv.length === 2) params[kv[0]] = decodeURIComponent(kv[1]);
        });

        if (params.q !== undefined) {
            state.query = params.q;
            els.searchInput.value = params.q;
        }
        if (params.cat) {
            state.category = params.cat;
            els.filterCategory.value = params.cat;
        }
        if (params.lang) {
            state.language = params.lang;
            els.filterLanguage.value = params.lang;
        }
        if (params.health) {
            state.minHealth = parseInt(params.health, 10) || 0;
            els.filterHealth.value = String(state.minHealth);
        }
        if (params.sort) {
            var lastDash = params.sort.lastIndexOf("-");
            state.sortKey = params.sort.substring(0, lastDash);
            state.sortDir = params.sort.substring(lastDash + 1) || "desc";
            els.sortSelect.value = params.sort;
        }
        if (params.view) {
            state.view = params.view;
        }
        if (params.page) {
            state.page = parseInt(params.page, 10) || 1;
        }
    }

    // ------------------------------------------------------------ Utilities
    function esc(str) {
        if (!str) return "";
        var d = document.createElement("div");
        d.textContent = str;
        return d.innerHTML;
    }

    function escAttr(str) {
        return esc(str).replace(/"/g, "&quot;");
    }

    function formatNum(n) {
        if (n == null) return "0";
        if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
        if (n >= 1000) return (n / 1000).toFixed(1) + "k";
        return String(n);
    }

    function relativeTime(dateStr) {
        if (!dateStr) return "unknown";
        try {
            var date = new Date(dateStr);
            var now = Date.now();
            var diff = now - date.getTime();
            var secs = Math.floor(diff / 1000);
            if (secs < 60) return "just now";
            var mins = Math.floor(secs / 60);
            if (mins < 60) return mins + "m ago";
            var hours = Math.floor(mins / 60);
            if (hours < 24) return hours + "h ago";
            var days = Math.floor(hours / 24);
            if (days < 30) return days + "d ago";
            var months = Math.floor(days / 30);
            if (months < 12) return months + "mo ago";
            var years = Math.floor(months / 12);
            return years + "y ago";
        } catch (e) {
            return "unknown";
        }
    }

    function healthColor(score) {
        if (score >= 80) return "var(--av-success)";
        if (score >= 60) return "var(--av-info)";
        if (score >= 40) return "var(--av-warning)";
        return "var(--av-danger)";
    }

    var categoryMap = {};
    function categoryName(id) {
        if (!id) return "";
        if (categoryMap[id]) return categoryMap[id];
        // Build map from filter options on first call
        var opts = els.filterCategory.options;
        for (var i = 1; i < opts.length; i++) {
            var text = opts[i].textContent.replace(/\s*\(\d+\)$/, "");
            categoryMap[opts[i].value] = text;
        }
        return categoryMap[id] || id.replace(/-/g, " ");
    }

    // ----------------------------------------------------------------- Start
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
