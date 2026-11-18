(function () {
    "use strict";

    // ------------------------------------------------------------------ Config
    var ITEMS_PER_PAGE = 48;
    var DEBOUNCE_MS = 200;

    // ------------------------------------------------------------------ State
    var state = {
        screen: "overview",
        repos: [],
        filtered: [],
        query: "",
        category: "all",
        subcategory: "all",
        language: "all",
        minHealth: 0,
        sortKey: "stars",
        sortDir: "desc",
        view: "grid",
        page: 1
    };

    var allData = null;
    var searchMeta = null;
    var vizData = null;

    // Lazy loading state per tier
    var TIER_FILES = {
        official:     { repos: "data/repos-official.json",     resources: "data/resources-official.json" },
        unofficial:   { repos: "data/repos-unofficial.json",   resources: "data/resources-unofficial.json" },
        noncanonical: { repos: "data/repos-noncanonical.json", resources: "data/resources-noncanonical.json" }
    };
    var tierLoaded   = { official: false, unofficial: false, noncanonical: false };
    var tierLoading  = { official: null,  unofficial: null,  noncanonical: null };
    var resLoaded    = { official: false, unofficial: false, noncanonical: false };
    var resLoading   = { official: null,  unofficial: null,  noncanonical: null };

    // Category-id to tier key lookup (built from index.json)
    var catTierMap = {};

    // --------------------------------------------------------- Table columns
    var TABLE_COLUMNS = [
        { id: "name", label: "Repository", sortKey: "name" },
        { id: "description", label: "Description", sortKey: null },
        { id: "subcategory", label: "Subcategory", sortKey: "subcategory" },
        { id: "language", label: "Language", sortKey: "language" },
        { id: "stars", label: "Stars", sortKey: "stars" },
        { id: "health", label: "Health", sortKey: "health" },
        { id: "last_push", label: "Last Push", sortKey: "last_push" },
        { id: "commits_90d", label: "Commits (90d)", sortKey: "commits_90d" },
        { id: "issues", label: "Issues", sortKey: "open_issues" },
        { id: "forks", label: "Forks", sortKey: "forks" },
        { id: "license", label: "License", sortKey: "license" }
    ];

    var columnOrder = TABLE_COLUMNS.map(function (c) { return c.id; });
    var hiddenColumns = {};

    function getColumnById(id) {
        for (var i = 0; i < TABLE_COLUMNS.length; i++) {
            if (TABLE_COLUMNS[i].id === id) return TABLE_COLUMNS[i];
        }
        return null;
    }

    function saveColumnPrefs() {
        try {
            localStorage.setItem("av-col-order", JSON.stringify(columnOrder));
            localStorage.setItem("av-col-hidden", JSON.stringify(Object.keys(hiddenColumns)));
        } catch (e) { /* storage unavailable */ }
    }

    function loadColumnPrefs() {
        try {
            var order = JSON.parse(localStorage.getItem("av-col-order"));
            if (order && Array.isArray(order)) {
                var valid = order.length === TABLE_COLUMNS.length && order.every(function (id) {
                    return TABLE_COLUMNS.some(function (c) { return c.id === id; });
                });
                if (valid) columnOrder = order;
            }
            var hidden = JSON.parse(localStorage.getItem("av-col-hidden"));
            if (hidden && Array.isArray(hidden)) {
                hiddenColumns = {};
                for (var i = 0; i < hidden.length; i++) hiddenColumns[hidden[i]] = true;
            }
        } catch (e) { /* storage unavailable */ }
    }

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
        els.suggestions = document.getElementById("search-suggestions");
        els.filterSubcategory = document.getElementById("filter-subcategory");
        els.filterLanguage = document.getElementById("filter-language");
        els.filterHealth = document.getElementById("filter-health");
        els.sortSelect = document.getElementById("sort-select");
        els.overviewSearchInput = document.getElementById("overview-search-input");
        els.resourceFilterSubcategory = document.getElementById("resource-filter-subcategory");
    }

    // ------------------------------------------------------------------- Init
    function init() {
        cacheDom();
        loadColumnPrefs();
        hiddenColumns = {}; // Column toggle UI removed; always show all columns
        bindEvents();
        loadData();
    }

    // -------------------------------------------------------------- Data load
    function loadData() {
        els["overview-grid"].innerHTML = '<div class="av-loading">Loading...</div>';

        fetch("data/index.json")
            .then(function (r) {
                if (!r.ok) throw new Error("Failed to load data");
                return r.json();
            })
            .then(function (data) {
                allData = data;
                allData.repos = [];
                allData.resources = [];
                buildCategoryMap(data.categories || []);
                buildCategoryMap(data.unofficial_categories || []);
                buildCategoryMap(data.non_canonical_categories || []);
                // Build catTierMap so we can resolve a category's tier
                (data.categories || []).forEach(function (c) { catTierMap[c.id] = "official"; });
                (data.unofficial_categories || []).forEach(function (c) { catTierMap[c.id] = "unofficial"; });
                (data.non_canonical_categories || []).forEach(function (c) { catTierMap[c.id] = "noncanonical"; });
                updateGlobalStats(data);
                restoreFromHash();
                if (state.screen === "detail" && state.category !== "all") {
                    showDetail(state.category, true);
                } else {
                    showOverview();
                }
                loadSearchMeta();
                loadVizData();
                // Prefetch official tier repos in background (default open segment)
                ensureTierRepos("official").then(function () { updateLiveStats(); });
            })
            .catch(function () {
                els["overview-grid"].innerHTML = '<div class="av-empty"><div class="av-empty-title">Could not load data</div><p>Run the data pipeline or check data/index.json</p></div>';
            });
    }

    // ------------------------------------------------ Lazy tier repo loading
    function ensureTierRepos(tier) {
        if (tierLoaded[tier]) return Promise.resolve();
        if (tierLoading[tier]) return tierLoading[tier];
        tierLoading[tier] = fetch(TIER_FILES[tier].repos)
            .then(function (r) {
                if (!r.ok) throw new Error("Failed to load " + tier + " repos");
                return r.json();
            })
            .then(function (repos) {
                for (var i = 0; i < repos.length; i++) {
                    state.repos.push(repos[i]);
                }
                tierLoaded[tier] = true;
                tierLoading[tier] = null;
                searchTokens = null; // invalidate search index
            })
            .catch(function () {
                tierLoading[tier] = null;
            });
        return tierLoading[tier];
    }

    function ensureTierResources(tier) {
        if (resLoaded[tier]) return Promise.resolve();
        if (resLoading[tier]) return resLoading[tier];
        resLoading[tier] = fetch(TIER_FILES[tier].resources)
            .then(function (r) {
                if (!r.ok) throw new Error("Failed to load " + tier + " resources");
                return r.json();
            })
            .then(function (resources) {
                allData.resources = allData.resources.concat(resources);
                resLoaded[tier] = true;
                resLoading[tier] = null;
            })
            .catch(function () {
                resLoading[tier] = null;
            });
        return resLoading[tier];
    }

    function ensureAllTiers() {
        return Promise.all([
            ensureTierRepos("official"),
            ensureTierRepos("unofficial"),
            ensureTierRepos("noncanonical")
        ]);
    }

    function ensureAllResources() {
        return Promise.all([
            ensureTierResources("official"),
            ensureTierResources("unofficial"),
            ensureTierResources("noncanonical")
        ]);
    }

    // --------------------------------------------------------- Search meta
    function loadSearchMeta() {
        fetch("data/search-meta.json")
            .then(function (r) {
                if (!r.ok) return null;
                return r.json();
            })
            .then(function (data) {
                if (data) searchMeta = data;
            })
            .catch(function () { /* optional enhancement, fail silently */ });
    }

    // ---------------------------------------------------------- Viz data
    var percentileThresholds = {};

    function loadVizData() {
        fetch("data/viz-data.json")
            .then(function (r) {
                if (!r.ok) return null;
                return r.json();
            })
            .then(function (data) {
                if (data) {
                    vizData = data;
                    // Load bucket definitions from backend if available
                    if (data.bucket_definitions) {
                        if (data.bucket_definitions.health) bucketDefs.health = data.bucket_definitions.health;
                        if (data.bucket_definitions.stars) {
                            bucketDefs.stars = data.bucket_definitions.stars.map(function (b) {
                                return { label: b.label, min: b.min, max: b.max === null ? Infinity : b.max };
                            });
                        }
                    }
                    if (data.percentile_thresholds) percentileThresholds = data.percentile_thresholds;
                    // Render only if the viz section is currently visible
                    var vizSection = els["viz-section"];
                    if (vizSection && !vizSection.hidden && state.screen === "overview") {
                        renderViz();
                    }
                }
            })
            .catch(function () { /* viz is optional, fail silently */ });
    }

    function getPercentile(metric, value) {
        var thresholds = percentileThresholds[metric];
        if (!thresholds || thresholds.length === 0) return 0;
        var pct = 0;
        for (var i = 0; i < thresholds.length; i++) {
            if (value >= thresholds[i].value) pct = thresholds[i].pct;
        }
        return pct;
    }

    function renderViz() {
        if (!vizData || typeof AVCharts === "undefined") return;

        // Language donut
        var langContainer = els["viz-lang-donut"];
        if (langContainer && vizData.language_distribution) {
            var langColors = {};
            for (var key in LANG_COLORS) {
                if (LANG_COLORS.hasOwnProperty(key)) langColors[key] = LANG_COLORS[key];
            }
            var langData = vizData.language_distribution.map(function (d) {
                return { name: d.name, count: d.count, pct: d.pct, color: langColors[d.name] || null };
            });
            AVCharts.donut(langContainer, langData, { centerLabel: "repos" });
        }

        // Health histogram
        var healthContainer = els["viz-health-hist"];
        if (healthContainer && vizData.health_histogram) {
            AVCharts.bar(healthContainer, vizData.health_histogram);
        }

        // Star buckets
        var starContainer = els["viz-star-buckets"];
        if (starContainer && vizData.star_buckets) {
            AVCharts.bar(starContainer, vizData.star_buckets);
        }

        // Health by language
        var healthLangContainer = els["viz-health-lang"];
        if (healthLangContainer && vizData.health_by_language) {
            AVCharts.horizontalBar(healthLangContainer, vizData.health_by_language);
        }

        // Category bubble chart
        var bubbleContainer = els["viz-category-bubbles"];
        if (bubbleContainer && vizData.category_bubbles) {
            AVCharts.bubble(bubbleContainer, vizData.category_bubbles, {
                onClick: function (d) {
                    if (d.id) window.open(window.location.pathname + "#cat=" + encodeURIComponent(d.id), "_blank");
                }
            });
        }

        // License distribution donut
        var licenseContainer = els["viz-license-donut"];
        if (licenseContainer && vizData.license_distribution) {
            AVCharts.donut(licenseContainer, vizData.license_distribution, { centerLabel: "repos" });
        }

        // Creation year timeline
        var creationContainer = els["viz-creation-year"];
        if (creationContainer && vizData.creation_year_histogram) {
            AVCharts.bar(creationContainer, vizData.creation_year_histogram);
        }

        // Activity distribution (commits in 90 days)
        var activityContainer = els["viz-activity-dist"];
        if (activityContainer && vizData.activity_distribution) {
            AVCharts.bar(activityContainer, vizData.activity_distribution, { suffix: "repos" });
        }

        // Fork/star ratio
        var forkStarContainer = els["viz-fork-star"];
        if (forkStarContainer && vizData.fork_star_ratio) {
            AVCharts.bar(forkStarContainer, vizData.fork_star_ratio);
        }

        // Tier comparison table
        var tierCompContainer = els["viz-tier-comparison"];
        if (tierCompContainer && vizData.tier_comparison && vizData.tier_comparison.length) {
            renderTierComparison(tierCompContainer, vizData.tier_comparison);
        }

        // Language trend over time
        var trendContainer = els["viz-language-trend"];
        if (trendContainer && vizData.language_trend) {
            AVCharts.stackedArea(trendContainer, vizData.language_trend);
        }
    }

    function renderTierComparison(container, tiers) {
        container.textContent = "";

        // Metric columns: [label, key, formatter, higherIsBetter]
        var metrics = [
            ["Repos",            "count",           formatNum,  true],
            ["Categories",       "categories",      formatNum,  true],
            ["Languages",        "languages",       formatNum,  true],
            ["Avg Health",       "avg_health",      String,     true],
            ["Median Health",    "median_health",   String,     true],
            ["Avg Stars",        "avg_stars",       formatNum,  true],
            ["Median Stars",     "median_stars",    formatNum,  true],
            ["Avg Forks",        "avg_forks",       formatNum,  true],
            ["Avg Open Issues",  "avg_open_issues", String,     false],
            ["Commits / 90d",    "avg_commits_90d", String,     true],
            ["Dormant",          "dormant_pct",     function (v) { return v + "%"; }, false],
            ["Archived",         "archived_pct",    function (v) { return v + "%"; }, false]
        ];

        var tierLabels = { "official": "Official", "unofficial": "Unofficial", "non-canonical": "Non-canonical" };

        var table = document.createElement("table");
        table.className = "av-tier-table av-tier-table--transposed";
        table.setAttribute("aria-label", "Tier comparison");

        // Header: Tier | metric1 | metric2 | ...
        var thead = document.createElement("thead");
        var headRow = document.createElement("tr");
        var thTier = document.createElement("th");
        thTier.scope = "col";
        thTier.textContent = "Tier";
        headRow.appendChild(thTier);
        for (var mi = 0; mi < metrics.length; mi++) {
            var th = document.createElement("th");
            th.scope = "col";
            th.textContent = metrics[mi][0];
            headRow.appendChild(th);
        }
        thead.appendChild(headRow);
        table.appendChild(thead);

        // Body: one row per tier
        var tbody = document.createElement("tbody");
        for (var ti = 0; ti < tiers.length; ti++) {
            var tr = document.createElement("tr");
            var tdLabel = document.createElement("td");
            tdLabel.className = "av-tier-table-metric";
            tdLabel.textContent = tierLabels[tiers[ti].tier] || tiers[ti].tier;
            tr.appendChild(tdLabel);

            for (var ci = 0; ci < metrics.length; ci++) {
                var m = metrics[ci];
                var key = m[1];
                var fmt = m[2];
                var higherBetter = m[3];
                var td = document.createElement("td");
                var val = tiers[ti][key] != null ? tiers[ti][key] : 0;
                td.textContent = fmt(val);

                // Find best value across tiers for this metric
                var vals = [];
                for (var vi = 0; vi < tiers.length; vi++) {
                    vals.push(tiers[vi][key] != null ? tiers[vi][key] : 0);
                }
                var bestVal = higherBetter ? Math.max.apply(null, vals) : Math.min.apply(null, vals);
                if (val === bestVal && tiers.length > 1) {
                    td.className = "av-tier-table-best";
                }
                tr.appendChild(td);
            }
            tbody.appendChild(tr);
        }
        table.appendChild(tbody);
        container.appendChild(table);
    }



    // Default bucket definitions (overridden by viz-data.json if available)
    var bucketDefs = {
        health: [
            { label: "0-19", min: 0, max: 19 },
            { label: "20-39", min: 20, max: 39 },
            { label: "40-59", min: 40, max: 59 },
            { label: "60-79", min: 60, max: 79 },
            { label: "80-100", min: 80, max: 100 }
        ],
        stars: [
            { label: "0-100", min: 0, max: 100 },
            { label: "101-500", min: 101, max: 500 },
            { label: "501-1k", min: 501, max: 1000 },
            { label: "1k-5k", min: 1001, max: 5000 },
            { label: "5k-10k", min: 5001, max: 10000 },
            { label: "10k-50k", min: 10001, max: 50000 },
            { label: "50k+", min: 50001, max: Infinity }
        ]
    };

    function renderDetailViz(catId) {
        if (typeof AVCharts === "undefined") return;

        var catRepos = state.repos.filter(function (r) { return r.category === catId; });
        if (!catRepos.length) return;

        // Language distribution
        var langContainer = els["detail-viz-lang-donut"];
        if (langContainer) {
            var langCounts = {};
            for (var i = 0; i < catRepos.length; i++) {
                var lang = catRepos[i].language;
                if (lang) langCounts[lang] = (langCounts[lang] || 0) + 1;
            }
            var total = 0;
            for (var lk in langCounts) { if (langCounts.hasOwnProperty(lk)) total += langCounts[lk]; }
            var sorted = Object.keys(langCounts).sort(function (a, b) { return langCounts[b] - langCounts[a]; });
            var topN = sorted.slice(0, 10);
            var otherCount = 0;
            for (var oi = 10; oi < sorted.length; oi++) otherCount += langCounts[sorted[oi]];

            var langData = topN.map(function (name) {
                return { name: name, count: langCounts[name], pct: total ? Math.round(langCounts[name] / total * 1000) / 10 : 0, color: LANG_COLORS[name] || null };
            });
            if (otherCount > 0) {
                langData.push({ name: "Other", count: otherCount, pct: total ? Math.round(otherCount / total * 1000) / 10 : 0, color: null });
            }
            langContainer.textContent = "";
            AVCharts.donut(langContainer, langData, { centerLabel: "repos" });
        }

        // Health histogram (uses shared bucket definitions)
        var healthContainer = els["detail-viz-health-hist"];
        if (healthContainer) {
            var healthBuckets = bucketDefs.health.map(function (b) {
                return { label: b.label, min: b.min, max: b.max, count: 0 };
            });
            for (var hi = 0; hi < catRepos.length; hi++) {
                var h = catRepos[hi].health || 0;
                for (var hb = 0; hb < healthBuckets.length; hb++) {
                    if (h >= healthBuckets[hb].min && h <= healthBuckets[hb].max) {
                        healthBuckets[hb].count++;
                        break;
                    }
                }
            }
            var histData = healthBuckets.map(function (b) { return { label: b.label, count: b.count }; });
            healthContainer.textContent = "";
            AVCharts.bar(healthContainer, histData);
        }

        // Star buckets (uses shared bucket definitions)
        var starContainer = els["detail-viz-star-buckets"];
        if (starContainer) {
            var starBuckets = bucketDefs.stars.map(function (b) {
                return { label: b.label, min: b.min, max: b.max === null ? Infinity : b.max, count: 0 };
            });
            for (var si = 0; si < catRepos.length; si++) {
                var stars = catRepos[si].stars || 0;
                for (var sb = 0; sb < starBuckets.length; sb++) {
                    if (stars >= starBuckets[sb].min && stars <= starBuckets[sb].max) {
                        starBuckets[sb].count++;
                        break;
                    }
                }
            }
            var starData = starBuckets.map(function (b) { return { label: b.label, count: b.count }; });
            starContainer.textContent = "";
            AVCharts.bar(starContainer, starData);
        }
    }

    // --------------------------------------------------- Populate filter menus
    var allSubcategories = [];

    function populateFilters(catId) {
        allSubcategories = (allData && allData.subcategories) || [];
        populateSubcategories();

        // Populate languages scoped to this category
        var sel = els.filterLanguage;
        while (sel.options.length > 1) sel.remove(1);
        var langCounts = {};
        for (var i = 0; i < state.repos.length; i++) {
            var r = state.repos[i];
            if (r.category !== catId) continue;
            var lang = r.language;
            if (lang) langCounts[lang] = (langCounts[lang] || 0) + 1;
        }
        var langs = Object.keys(langCounts).sort(function (a, b) {
            return langCounts[b] - langCounts[a];
        });
        for (var j = 0; j < langs.length; j++) {
            var lo = document.createElement("option");
            lo.value = langs[j];
            lo.textContent = langs[j] + " (" + langCounts[langs[j]] + ")";
            sel.appendChild(lo);
        }
    }

    function populateSubcategories() {
        var sel = els.filterSubcategory;
        var prevVal = state.subcategory;
        while (sel.options.length > 1) sel.remove(1);

        var filtered = allSubcategories;
        if (state.category !== "all") {
            filtered = allSubcategories.filter(function (s) {
                return s.category === state.category;
            });
        }

        for (var i = 0; i < filtered.length; i++) {
            var opt = document.createElement("option");
            opt.value = filtered[i].id;
            opt.textContent = filtered[i].name + " (" + filtered[i].count + ")";
            sel.appendChild(opt);
        }

        // Restore previous selection if still valid
        sel.value = prevVal;
        if (sel.value !== prevVal) {
            state.subcategory = "all";
            sel.value = "all";
        }
    }

    // ------------------------------------------------ Overview filter state
    // ------------------------------------------------ Segment definitions
    var SEGMENTS = {
        official:     { dataKey: "categories",                gridRef: "overview-grid",     sectionRef: "segment-official" },
        unofficial:   { dataKey: "unofficial_categories",     gridRef: "unofficial-grid",   sectionRef: "segment-unofficial" },
        noncanonical: { dataKey: "non_canonical_categories",  gridRef: "noncanonical-grid", sectionRef: "segment-noncanonical" }
    };

    var segmentFilters = {
        official:     { language: "all", minHealth: 0 },
        unofficial:   { language: "all", minHealth: 0 },
        noncanonical: { language: "all", minHealth: 0 }
    };

    // Unified overview filter state
    var overviewFilter = { language: "all", minHealth: 0 };

    function populateOverviewLanguages() {
        var sel = els["overview-filter-language"];
        if (!sel) return;
        while (sel.options.length > 1) sel.remove(1);

        var langCounts = {};
        var keys = ["official", "unofficial", "noncanonical"];
        for (var k = 0; k < keys.length; k++) {
            var cats = (allData && allData[SEGMENTS[keys[k]].dataKey]) || [];
            for (var c = 0; c < cats.length; c++) {
                var topLangs = cats[c].top_languages || [];
                for (var l = 0; l < topLangs.length; l++) {
                    langCounts[topLangs[l].name] = (langCounts[topLangs[l].name] || 0) + topLangs[l].count;
                }
            }
        }
        var langs = Object.keys(langCounts).sort(function (a, b) {
            return langCounts[b] - langCounts[a];
        });
        for (var j = 0; j < langs.length; j++) {
            var opt = document.createElement("option");
            opt.value = langs[j];
            opt.textContent = langs[j] + " (" + langCounts[langs[j]] + ")";
            sel.appendChild(opt);
        }
    }

    function renderSegment(segKey) {
        var seg = SEGMENTS[segKey];
        var cats = (allData && allData[seg.dataKey]) || [];
        var grid = els[seg.gridRef];
        if (!grid) return;
        grid.textContent = "";

        // Hide entire toggle + section when segment has no data at all
        var toggleBtn = document.querySelector("[aria-controls='" + seg.sectionRef + "']");
        if (!cats.length) {
            if (toggleBtn) toggleBtn.hidden = true;
            if (els[seg.sectionRef]) els[seg.sectionRef].hidden = true;
            return;
        }
        if (toggleBtn) toggleBtn.hidden = false;

        var f = overviewFilter;
        var filtered = cats;
        if (f.language !== "all") {
            filtered = filtered.filter(function (cat) {
                var topLangs = cat.top_languages || [];
                return topLangs.some(function (l) { return l.name === f.language; });
            });
        }
        if (f.minHealth > 0) {
            filtered = filtered.filter(function (cat) {
                return (cat.avg_health || 0) >= f.minHealth;
            });
        }

        if (!filtered.length) {
            grid.innerHTML = '<div class="av-empty"><div class="av-empty-title">No categories match your filters</div><p>Try adjusting your filter criteria</p></div>';
            return;
        }
        var frag = document.createDocumentFragment();
        for (var i = 0; i < filtered.length; i++) {
            frag.appendChild(createCategoryCard(filtered[i]));
        }
        grid.appendChild(frag);
    }

    function updateSegmentCounts() {
        var keys = ["official", "unofficial", "noncanonical"];
        for (var k = 0; k < keys.length; k++) {
            var seg = SEGMENTS[keys[k]];
            var cats = (allData && allData[seg.dataKey]) || [];
            var countEl = els[keys[k] + "-count"];
            if (countEl) countEl.textContent = cats.length ? cats.length + " lists" : "";
        }
    }

    // ----------------------------------------------------------- Global stats
    function updateGlobalStats(data) {
        var meta = data.meta || {};
        var tc = meta.tier_counts || {};
        els["stat-total"].textContent = formatNum(meta.total_repos || 0);
        els["stat-categories"].textContent =
            (data.categories || []).length +
            (data.unofficial_categories || []).length +
            (data.non_canonical_categories || []).length;
        els["stat-resources"].textContent = formatNum(meta.total_resources || 0);

        // avg health and active count are deferred until repos load
        els["stat-avg-health"].textContent = "-";
        els["stat-active"].textContent = "-";

        if (meta.last_updated) {
            els["last-updated"].textContent = "Updated " + relativeTime(meta.last_updated);
        }

        // Tier counts stored for segment headers
        var tiers = [
            { label: "Official",       cats: (data.categories || []).length,               repos: tc.official || 0 },
            { label: "Unofficial",     cats: (data.unofficial_categories || []).length,     repos: tc.unofficial || 0 },
            { label: "Non-canonical",  cats: (data.non_canonical_categories || []).length,  repos: tc.noncanonical || 0 }
        ];
    }

    function updateLiveStats() {
        var totalHealth = 0;
        var activeCount = 0;
        for (var i = 0; i < state.repos.length; i++) {
            totalHealth += state.repos[i].health || 0;
            if (state.repos[i].commits_90d > 0) activeCount++;
        }
        var avgHealth = state.repos.length ? Math.round(totalHealth / state.repos.length) : 0;
        els["stat-avg-health"].textContent = avgHealth;
        els["stat-active"].textContent = formatNum(activeCount);
    }

    // ------------------------------------------------------- Category map
    var categoryMap = {};

    function buildCategoryMap(cats) {
        for (var i = 0; i < cats.length; i++) {
            categoryMap[cats[i].id] = cats[i];
        }
    }

    function categoryName(id) {
        if (!id) return "";
        var cat = categoryMap[id];
        return cat ? cat.name : id.replace(/-/g, " ");
    }

    // ====================================================== Overview screen
    function showOverview() {
        state.screen = "overview";
        state.category = "all";
        els["overview-screen"].hidden = false;
        els["detail-screen"].hidden = true;
        els.overviewSearchInput.value = "";
        clearOverviewSearch();
        // Reset overview filter
        overviewFilter = { language: "all", minHealth: 0 };
        if (els["overview-filter-language"]) els["overview-filter-language"].value = "all";
        if (els["overview-filter-health"]) els["overview-filter-health"].value = "0";
        populateOverviewLanguages();
        renderOverview();
        saveToHash();
    }

    function renderOverview() {
        renderSegment("official");
        renderSegment("unofficial");
        renderSegment("noncanonical");
        updateSegmentCounts();
    }

    function createCategoryCard(cat) {
        var card = document.createElement("article");
        card.className = "av-catcard";
        card.setAttribute("role", "listitem");
        card.setAttribute("data-action", "open-category");
        card.setAttribute("data-category-id", cat.id);
        card.tabIndex = 0;

        var hColor = healthColor(cat.avg_health || 0);

        var topLangs = (cat.top_languages || []).slice(0, 4);
        var langHtml = "";
        for (var i = 0; i < topLangs.length; i++) {
            var lc = LANG_COLORS[topLangs[i].name] || "";
            langHtml += '<span class="av-catcard-lang">' +
                (lc ? '<span class="av-lang-dot" style="--lang-color:' + lc + '"></span>' : '') +
                esc(topLangs[i].name) + '</span>';
        }

        var resCount = cat.resource_count || 0;
        var resHtml = resCount > 0 ?
            '<span class="av-catcard-count av-catcard-count--res">' +
                '<svg class="av-icon--sm" aria-hidden="true"><use href="#icon-link"/></svg> ' +
                resCount + ' resources</span>' : '';

        card.innerHTML =
            '<header class="av-catcard-header">' +
                '<h3 class="av-catcard-title">' + esc(cat.name) + '</h3>' +
                '<span class="av-catcard-count">' + cat.count + ' repos</span>' +
                resHtml +
            '</header>' +
            (cat.source_repo ? '<p class="av-catcard-source">' + esc(cat.source_repo) + '</p>' : '') +
            '<div class="av-catcard-stats">' +
                '<div class="av-catcard-stat">' +
                    '<span class="av-health-score" style="--health-color:' + hColor + '">' + (cat.avg_health || 0) + '</span>' +
                    '<span class="av-catcard-stat-label">health</span>' +
                '</div>' +
                '<div class="av-catcard-stat">' +
                    '<span class="av-catcard-stat-val">' + (cat.subcategory_count || 0) + '</span>' +
                    '<span class="av-catcard-stat-label">subcategories</span>' +
                '</div>' +
            '</div>' +
            (langHtml ? '<div class="av-catcard-langs">' + langHtml + '</div>' : '');

        return card;
    }

    // ======================================================= Detail screen
    function showDetail(catId, skipHash) {
        state.screen = "detail";
        state.category = catId;
        els["overview-screen"].hidden = true;
        els["detail-screen"].hidden = false;

        var cat = categoryMap[catId] || {};
        els["detail-title"].textContent = cat.name || catId;
        if (cat.source_repo) {
            els["detail-source"].href = cat.source_repo ? "https://github.com/" + cat.source_repo : "#";
            els["detail-source-name"].textContent = cat.source_repo;
            els["detail-source"].hidden = false;
        } else {
            els["detail-source"].hidden = true;
        }

        if (!skipHash) saveToHash();

        // Determine which tier this category belongs to and lazy-load
        var tier = catTierMap[catId] || "official";
        var reposReady = tierLoaded[tier];
        var resourcesReady = resLoaded[tier];

        if (reposReady && resourcesReady) {
            renderDetail(catId);
        } else {
            // Show loading state in the detail grid
            var detailGrid = els["detail-grid"];
            if (detailGrid) detailGrid.innerHTML = '<div class="av-loading">Loading repos...</div>';

            Promise.all([ensureTierRepos(tier), ensureTierResources(tier)]).then(function () {
                // Only render if we're still looking at this category
                if (state.category === catId) renderDetail(catId);
            });
        }
    }

    function renderDetail(catId) {
        // Detail stats
        var catRepos = [];
        var detailLangs = {};
        var healthSum = 0;
        var subIds = {};
        for (var i = 0; i < state.repos.length; i++) {
            var r = state.repos[i];
            if (r.category !== catId) continue;
            catRepos.push(r);
            healthSum += r.health || 0;
            if (r.language) detailLangs[r.language] = true;
            subIds[r.subcategory_id || "general"] = true;
        }
        els["detail-stat-repos"].textContent = catRepos.length;
        els["detail-stat-health"].textContent = catRepos.length ? Math.round(healthSum / catRepos.length) : 0;
        els["detail-stat-subcats"].textContent = Object.keys(subIds).length;
        els["detail-stat-langs"].textContent = Object.keys(detailLangs).length;

        // Count resources for this category
        var catResources = getCategoryResources(catId);
        els["detail-stat-resources"].textContent = catResources.length;

        // Populate filters scoped to this category
        populateFilters(catId);

        // Reset detail-specific state
        state.subcategory = "all";
        state.language = "all";
        state.minHealth = 0;
        state.query = "";
        state.sortKey = "stars";
        state.sortDir = "desc";
        state.view = "table";
        state.page = 1;
        els.searchInput.value = "";
        els.filterSubcategory.value = "all";
        els.filterLanguage.value = "all";
        els.filterHealth.value = "0";
        els.sortSelect.value = "stars-desc";

        searchTokens = null;
        applyAndRender();
        renderResources(catId);

        // Reset detail viz toggle to expanded and render charts
        var detailVizBtn = document.querySelector('[data-action="toggle-detail-viz"]');
        var detailVizSection = document.getElementById("detail-viz-section");
        if (detailVizBtn && detailVizSection) {
            detailVizSection.hidden = false;
            detailVizBtn.setAttribute("aria-expanded", "true");
            detailVizBtn.classList.add("av-viz-toggle--open");
            var chevron = detailVizBtn.querySelector(".av-viz-toggle-chevron");
            if (chevron) chevron.classList.add("av-viz-toggle-chevron--open");
        }
        renderDetailViz(catId);
    }

    // -------------------------------------------------------------- Search
    // Supports: * (wildcard), | (or), & or space (and), case-insensitive
    var searchTokens = null;

    // Scoped search: separate title vs description tokens
    var searchScope = { title: true, desc: true };
    var scopedTokens = null;

    function buildSearchIndex() {
        searchTokens = new Array(state.repos.length);
        scopedTokens = new Array(state.repos.length);
        for (var i = 0; i < state.repos.length; i++) {
            var r = state.repos[i];
            searchTokens[i] = (
                (r.full_name || "") + " " +
                (r.name || "") + " " +
                (r.description || "") + " " +
                (r.topics || []).join(" ") + " " +
                (r.language || "") + " " +
                (r.owner || "") + " " +
                (r.category || "") + " " +
                (r.subcategory || "") + " " +
                (r.kw || "")
            ).toLowerCase();
            scopedTokens[i] = {
                title: ((r.full_name || "") + " " + (r.name || "") + " " + (r.owner || "")).toLowerCase(),
                desc: ((r.description || "") + " " + (r.topics || []).join(" ") + " " + (r.kw || "")).toLowerCase(),
                meta: ((r.language || "") + " " + (r.category || "") + " " + (r.subcategory || "")).toLowerCase()
            };
        }
    }

    function getScopedHaystack(idx) {
        var t = scopedTokens[idx];
        var parts = t.meta;
        if (searchScope.title) parts = t.title + " " + parts;
        if (searchScope.desc) parts = t.desc + " " + parts;
        return parts;
    }

    function search(query, scoped) {
        if (!searchTokens) buildSearchIndex();
        if (!query) return state.repos.slice();

        var MAX_RESULTS = 1000;
        var useScoped = scoped && !(searchScope.title && searchScope.desc);

        // & is explicit AND (same as space)
        var normalized = query.replace(/&/g, " ");
        // Split on | for OR groups
        var orGroups = normalized.split("|");

        // Pre-compile regex patterns per OR group (O2 fix)
        var compiledGroups = [];
        for (var g = 0; g < orGroups.length; g++) {
            var terms = orGroups[g].trim().toLowerCase().split(/\s+/).filter(Boolean);
            if (terms.length === 0) continue;
            var patterns = [];
            for (var t = 0; t < terms.length; t++) {
                var pattern = terms[t]
                    .replace(/[.+?^${}()[\]\\]/g, "\\$&")
                    .replace(/\*/g, ".*");
                try {
                    patterns.push({ re: new RegExp(pattern), raw: terms[t] });
                } catch (e) {
                    patterns.push({ re: null, raw: terms[t] });
                }
            }
            compiledGroups.push(patterns);
        }
        if (compiledGroups.length === 0) return state.repos.slice();

        var scored = [];

        for (var i = 0; i < state.repos.length; i++) {
            var haystack = useScoped ? getScopedHaystack(i) : searchTokens[i];
            var matched = false;
            var matchScore = 0;

            for (var cg = 0; cg < compiledGroups.length; cg++) {
                var group = compiledGroups[cg];
                var allMatch = true;
                var groupScore = 0;

                for (var p = 0; p < group.length; p++) {
                    var entry = group[p];
                    if (entry.re) {
                        if (!entry.re.test(haystack)) { allMatch = false; break; }
                    } else {
                        if (haystack.indexOf(entry.raw) === -1) { allMatch = false; break; }
                    }
                    groupScore += computeTermScore(state.repos[i], entry.raw);
                }

                if (allMatch) {
                    matched = true;
                    matchScore = Math.max(matchScore, groupScore);
                }
            }

            if (matched) {
                scored.push({ repo: state.repos[i], score: matchScore });
                // Early-exit: stop collecting after MAX_RESULTS (O1 fix)
                if (scored.length >= MAX_RESULTS) break;
            }
        }

        // Sort by relevance score descending, then by stars as tiebreaker
        scored.sort(function (a, b) {
            var diff = b.score - a.score;
            return diff !== 0 ? diff : (b.repo.stars || 0) - (a.repo.stars || 0);
        });

        var results = new Array(scored.length);
        for (var j = 0; j < scored.length; j++) results[j] = scored[j].repo;
        return results;
    }

    function computeTermScore(repo, term) {
        var score = 0;
        var name = (repo.name || "").toLowerCase();
        var owner = (repo.owner || "").toLowerCase();
        // Exact name match is highest relevance
        if (name === term) score += 50;
        else if (name.indexOf(term) === 0) score += 30;
        else if (name.indexOf(term) !== -1) score += 15;
        // Owner match
        if (owner === term) score += 20;
        else if (owner.indexOf(term) !== -1) score += 5;
        // Topic match
        var topics = repo.topics || [];
        for (var i = 0; i < topics.length; i++) {
            if (topics[i].toLowerCase() === term) { score += 15; break; }
        }
        // Language match
        if ((repo.language || "").toLowerCase() === term) score += 10;
        // Keyword match (from enriched data)
        if (repo.kw && repo.kw.toLowerCase().indexOf(term) !== -1) score += 5;
        return score;
    }

    // ------------------------------------------------------------- Filtering
    function applyFilters(repos) {
        var out = [];
        for (var i = 0; i < repos.length; i++) {
            var r = repos[i];
            if (state.category !== "all" && r.category !== state.category) continue;
            if (state.subcategory !== "all" && (r.subcategory_id || "") !== state.subcategory) continue;
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

    function createCard(repo, showCategory) {
        var card = document.createElement("article");
        card.className = "av-card";
        card.setAttribute("role", "listitem");

        var hColor = healthColor(repo.health);
        var langColor = LANG_COLORS[repo.language] || "";

        var catBadge = "";
        if (showCategory && repo.category) {
            catBadge = '<span class="av-card-category">' + esc(categoryName(repo.category)) + '</span>';
        }

        var topicHtml = "";
        var topics = repo.topics || [];
        if (topics.length > 0) {
            topicHtml = '<div class="av-card-topics">';
            for (var ti = 0; ti < topics.length; ti++) {
                topicHtml += '<button type="button" class="av-topic-pill" data-action="filter-topic" data-topic="' + escAttr(topics[ti]) + '">' + esc(topics[ti]) + '</button>';
            }
            topicHtml += '</div>';
        }

        var starPct = getPercentile("stars", repo.stars);
        var pctBadge = "";
        if (starPct >= 90) pctBadge = '<span class="av-pct-badge" title="Top ' + (100 - starPct) + '% by stars">p' + starPct + '</span>';

        card.innerHTML =
            '<header class="av-card-header">' +
                (langColor ? '<span class="av-lang-dot" style="--lang-color:' + langColor + '"></span>' : '') +
                '<a href="https://github.com/' + escAttr(repo.full_name) + '" class="av-card-title" target="_blank" rel="noopener">' + esc(repo.name) + '</a>' +
                '<span class="av-card-owner">' + esc(repo.owner) + '</span>' +
                pctBadge +
            '</header>' +
            '<p class="av-card-desc">' + esc(repo.description) + '</p>' +
            topicHtml +
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
                    catBadge +
                    (repo.subcategory && repo.subcategory !== 'General' ? '<span class="av-badge av-badge--sub">' + esc(repo.subcategory) + '</span>' : '') +
                    (repo.is_archived ? '<span class="av-badge av-badge--archived">Archived</span>' : '') +
                '</div>' +
            '</footer>';

        return card;
    }

    function metric(iconId, text) {
        return '<span class="av-metric"><svg class="av-icon--sm" aria-hidden="true"><use href="#' + iconId + '"/></svg> ' + esc(String(text)) + '</span>';
    }

    // ----------------------------------------------------------- Table view

    function renderTableHead() {
        var headRow = els["repo-table-head"];
        headRow.textContent = "";

        for (var i = 0; i < columnOrder.length; i++) {
            var colId = columnOrder[i];
            if (hiddenColumns[colId]) continue;

            var col = getColumnById(colId);
            if (!col) continue;

            var th = document.createElement("th");
            th.scope = "col";
            th.setAttribute("data-col-id", col.id);
            th.draggable = true;

            if (col.sortKey) {
                th.classList.add("av-table-th--sortable");
                th.setAttribute("data-sort-key", col.sortKey);

                var isSorted = state.sortKey === col.sortKey;
                if (isSorted) th.classList.add("av-table-th--sorted");

                var inner = document.createElement("span");
                inner.className = "av-table-th-inner";

                var label = document.createElement("span");
                label.className = "av-table-th-label";
                label.textContent = col.label;
                inner.appendChild(label);

                var chevron = document.createElement("span");
                chevron.className = "av-table-sort-chevron";
                if (isSorted) {
                    chevron.classList.add(state.sortDir === "asc" ? "av-table-sort-chevron--asc" : "av-table-sort-chevron--desc");
                }
                inner.appendChild(chevron);

                th.appendChild(inner);
            } else {
                var lbl = document.createElement("span");
                lbl.className = "av-table-th-label";
                lbl.textContent = col.label;
                th.appendChild(lbl);
            }

            headRow.appendChild(th);
        }
    }

    function renderTable() {
        renderTableHead();

        var start = (state.page - 1) * ITEMS_PER_PAGE;
        var items = state.filtered.slice(start, start + ITEMS_PER_PAGE);
        var frag = document.createDocumentFragment();

        for (var i = 0; i < items.length; i++) {
            frag.appendChild(createTableRow(items[i]));
        }

        els["repo-table-body"].textContent = "";
        els["repo-table-body"].appendChild(frag);
    }

    function getCellHtml(colId, repo) {
        var hColor = healthColor(repo.health);
        var langColor = LANG_COLORS[repo.language] || "";

        switch (colId) {
            case "name":
                return '<td class="av-table-name">' +
                    (langColor ? '<span class="av-lang-dot" style="--lang-color:' + langColor + '"></span>' : '') +
                    '<a href="https://github.com/' + escAttr(repo.full_name) + '" target="_blank" rel="noopener">' + esc(repo.full_name) + '</a></td>';
            case "description":
                return '<td class="av-table-desc" title="' + escAttr(repo.description) + '">' + esc(repo.description) + '</td>';
            case "subcategory":
                return '<td>' + esc(repo.subcategory || "-") + '</td>';
            case "stars":
                return '<td>' + formatNum(repo.stars) + '</td>';
            case "forks":
                return '<td>' + formatNum(repo.forks) + '</td>';
            case "issues":
                return '<td>' + formatNum(repo.open_issues) + '</td>';
            case "language":
                return '<td>' + esc(repo.language || "-") + '</td>';
            case "license":
                return '<td>' + esc(repo.license || "-") + '</td>';
            case "commits_90d":
                return '<td>' + repo.commits_90d + '</td>';
            case "last_push":
                return '<td>' + relativeTime(repo.last_push) + '</td>';
            case "health":
                return '<td><span class="av-health-score" style="--health-color:' + hColor + '">' + repo.health + '</span></td>';
            default:
                return '<td></td>';
        }
    }

    function createTableRow(repo) {
        var tr = document.createElement("tr");
        var html = "";

        for (var i = 0; i < columnOrder.length; i++) {
            if (!hiddenColumns[columnOrder[i]]) {
                html += getCellHtml(columnOrder[i], repo);
            }
        }

        tr.innerHTML = html;
        return tr;
    }

    // --------------------------------------------------- Column dropdown

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
    var activeSuggestion = -1;

    function bindEvents() {
        // Search with debounce + autocomplete
        var debounceTimer = null;
        var suggestTimer = null;

        els.searchInput.addEventListener("input", function () {
            clearTimeout(debounceTimer);
            clearTimeout(suggestTimer);
            var val = els.searchInput.value.trim();
            debounceTimer = setTimeout(function () {
                state.query = val;
                applyAndRender();
            }, DEBOUNCE_MS);
            suggestTimer = setTimeout(function () {
                showSuggestions(val);
            }, 100);
        });

        els.searchInput.addEventListener("keydown", function (e) {
            if (!els.suggestions || els.suggestions.hidden) return;
            var items = els.suggestions.querySelectorAll("[role='option']");
            if (e.key === "ArrowDown") {
                e.preventDefault();
                activeSuggestion = Math.min(activeSuggestion + 1, items.length - 1);
                updateActiveSuggestion(items);
            } else if (e.key === "ArrowUp") {
                e.preventDefault();
                activeSuggestion = Math.max(activeSuggestion - 1, -1);
                updateActiveSuggestion(items);
            } else if (e.key === "Enter" && activeSuggestion >= 0 && items[activeSuggestion]) {
                e.preventDefault();
                applySuggestion(items[activeSuggestion].textContent.split(" (")[0]);
            } else if (e.key === "Escape") {
                hideSuggestions();
            }
        });

        els.searchInput.addEventListener("focus", function () {
            if (els.searchInput.value.trim().length >= 2) {
                showSuggestions(els.searchInput.value.trim());
            }
        });

        document.addEventListener("click", function (e) {
            if (!els.suggestions.contains(e.target) && e.target !== els.searchInput) {
                hideSuggestions();
            }
        });

        els.suggestions.addEventListener("mousedown", function (e) {
            var opt = e.target.closest("[role='option']");
            if (opt) {
                e.preventDefault();
                applySuggestion(opt.textContent.split(" (")[0]);
            }
        });

        // Filters
        els.filterSubcategory.addEventListener("change", function () {
            state.subcategory = this.value;
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

        // View toggle, back button, category card clicks
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
            } else if (action === "open-category") {
                var catId = btn.getAttribute("data-category-id");
                if (catId) showDetail(catId);
            } else if (action === "back-overview") {
                showOverview();
            } else if (action === "filter-topic") {
                var topic = btn.getAttribute("data-topic");
                if (topic) {
                    els.search.value = topic;
                    applyAndRender();
                }
            } else if (action === "toggle-overview-viz" || action === "toggle-detail-viz") {
                var targetId = btn.getAttribute("aria-controls");
                var section = document.getElementById(targetId);
                if (!section) return;
                var isExpanded = btn.getAttribute("aria-expanded") === "true";
                section.hidden = isExpanded;
                btn.setAttribute("aria-expanded", isExpanded ? "false" : "true");
                var chevron = btn.querySelector(".av-viz-toggle-chevron");
                if (chevron) chevron.classList.toggle("av-viz-toggle-chevron--open", !isExpanded);
                btn.classList.toggle("av-viz-toggle--open", !isExpanded);
                // Render charts when expanding (may need container dimensions)
                if (!isExpanded) {
                    if (action === "toggle-overview-viz" && vizData) renderViz();
                    if (action === "toggle-detail-viz") renderDetailViz(state.category);
                }
            } else if (action === "toggle-segment") {
                // While overview search is active, segments are locked
                if (overviewSearchActive) return;
                var segId = btn.getAttribute("aria-controls");
                var segSection = document.getElementById(segId);
                if (!segSection) return;
                var segExpanded = btn.getAttribute("aria-expanded") === "true";
                segSection.hidden = segExpanded;
                btn.setAttribute("aria-expanded", segExpanded ? "false" : "true");
                var segChevron = btn.querySelector(".av-segment-chevron");
                if (segChevron) segChevron.classList.toggle("av-segment-chevron--open", !segExpanded);
                btn.classList.toggle("av-segment-toggle--open", !segExpanded);

                // Prefetch tier repos when expanding a segment (for fast detail navigation)
                if (!segExpanded) {
                    var segTier = segId.replace("segment-", "");
                    if (TIER_FILES[segTier] && !tierLoaded[segTier]) {
                        btn.classList.add("is-loading");
                        ensureTierRepos(segTier).then(function () {
                            btn.classList.remove("is-loading");
                            updateLiveStats();
                        }).catch(function () {
                            btn.classList.remove("is-loading");
                        });
                    }
                }
            } else if (action === "toggle-search-help") {
                var helpPanel = document.getElementById("search-help-panel");
                if (helpPanel) {
                    var helpExpanded = btn.getAttribute("aria-expanded") === "true";
                    helpPanel.hidden = helpExpanded;
                    btn.setAttribute("aria-expanded", helpExpanded ? "false" : "true");
                }
            } else if (action === "reset-filters") {
                state.subcategory = "all";
                state.language = "all";
                state.minHealth = 0;
                state.query = "";
                state.page = 1;
                els.searchInput.value = "";
                els.filterSubcategory.value = "all";
                els.filterLanguage.value = "all";
                els.filterHealth.value = "0";
                applyAndRender();
            } else if (action === "reset-overview-filters") {
                overviewFilter = { language: "all", minHealth: 0 };
                if (els["overview-filter-language"]) els["overview-filter-language"].value = "all";
                if (els["overview-filter-health"]) els["overview-filter-health"].value = "0";
                els.overviewSearchInput.value = "";
                clearOverviewSearch();
            }
        });

        // Overview unified filter bar
        var ovLangSel = els["overview-filter-language"];
        var ovHealthSel = els["overview-filter-health"];
        function applyOverviewFilter() {
            overviewFilter.language = ovLangSel ? ovLangSel.value : "all";
            overviewFilter.minHealth = ovHealthSel ? parseInt(ovHealthSel.value, 10) || 0 : 0;
            if (overviewSearchActive) {
                var val = els.overviewSearchInput.value.trim();
                if (val.length > 0) {
                    performOverviewSearch(val);
                    return;
                }
            }
            renderOverview();
        }
        if (ovLangSel) ovLangSel.addEventListener("change", applyOverviewFilter);
        if (ovHealthSel) ovHealthSel.addEventListener("change", applyOverviewFilter);

        // Resource subcategory filter
        if (els.resourceFilterSubcategory) {
            els.resourceFilterSubcategory.addEventListener("change", function () {
                var sub = this.value;
                var catId = state.category;
                var resources = getCategoryResources(catId);
                if (sub !== "all") {
                    resources = resources.filter(function (r) { return r.subcategory === sub; });
                }
                currentResources = resources;
                renderResourceGrid(sortResources(resources, resourceSortKey, resourceSortDir));
                var countEl = els["resources-count"];
                if (countEl) countEl.textContent = resources.length + " links";
            });
        }

        // Resource table header: sort by click
        if (els["resources-thead"]) {
            els["resources-thead"].addEventListener("click", function (e) {
                var th = e.target.closest("[data-resource-sort]");
                if (!th) return;
                var key = th.getAttribute("data-resource-sort");
                if (resourceSortKey === key) {
                    resourceSortDir = resourceSortDir === "asc" ? "desc" : "asc";
                } else {
                    resourceSortKey = key;
                    resourceSortDir = "asc";
                }
                renderResourceHead();
                renderResourceGrid(sortResources(currentResources, resourceSortKey, resourceSortDir));
            });
        }

        // Table header: sort by click
        els["repo-table-head"].addEventListener("click", function (e) {
            var th = e.target.closest("th[data-sort-key]");
            if (!th) return;
            var key = th.getAttribute("data-sort-key");
            if (state.sortKey === key) {
                state.sortDir = state.sortDir === "desc" ? "asc" : "desc";
            } else {
                state.sortKey = key;
                state.sortDir = "desc";
            }
            // Sync sort dropdown
            var selectValue = state.sortKey + "-" + state.sortDir;
            if (els.sortSelect.querySelector('option[value="' + selectValue + '"]')) {
                els.sortSelect.value = selectValue;
            }
            applyAndRender();
        });

        // Table header: column drag-and-drop
        (function () {
            var headRow = els["repo-table-head"];
            var dragSourceId = null;

            headRow.addEventListener("dragstart", function (e) {
                var th = e.target.closest("th[data-col-id]");
                if (!th) return;
                dragSourceId = th.getAttribute("data-col-id");
                th.classList.add("is-dragging");
                e.dataTransfer.effectAllowed = "move";
                e.dataTransfer.setData("text/plain", dragSourceId);
            });

            headRow.addEventListener("dragover", function (e) {
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
                var th = e.target.closest("th[data-col-id]");
                if (!th) return;
                var allTh = headRow.querySelectorAll("th");
                for (var i = 0; i < allTh.length; i++) allTh[i].classList.remove("is-drop-target");
                th.classList.add("is-drop-target");
            });

            headRow.addEventListener("dragleave", function (e) {
                var th = e.target.closest("th[data-col-id]");
                if (th) th.classList.remove("is-drop-target");
            });

            headRow.addEventListener("drop", function (e) {
                e.preventDefault();
                var th = e.target.closest("th[data-col-id]");
                if (!th || !dragSourceId) return;
                var targetId = th.getAttribute("data-col-id");
                if (targetId === dragSourceId) return;

                var fromIdx = columnOrder.indexOf(dragSourceId);
                var toIdx = columnOrder.indexOf(targetId);
                if (fromIdx === -1 || toIdx === -1) return;
                columnOrder.splice(fromIdx, 1);
                columnOrder.splice(toIdx, 0, dragSourceId);

                saveColumnPrefs();
                renderTableHead();
                renderTable();
            });

            headRow.addEventListener("dragend", function () {
                dragSourceId = null;
                var allTh = headRow.querySelectorAll("th");
                for (var i = 0; i < allTh.length; i++) {
                    allTh[i].classList.remove("is-dragging", "is-drop-target");
                }
            });
        })();

        // Overview search
        var overviewDebounce = null;
        var scopeTitleCb = document.getElementById("search-scope-title");
        var scopeDescCb = document.getElementById("search-scope-desc");

        function readSearchScope() {
            searchScope.title = scopeTitleCb.checked;
            searchScope.desc = scopeDescCb.checked;
            // At least one must be checked
            if (!searchScope.title && !searchScope.desc) {
                searchScope.title = true;
                searchScope.desc = true;
                scopeTitleCb.checked = true;
                scopeDescCb.checked = true;
            }
        }

        function retriggerOverviewSearch() {
            readSearchScope();
            var val = els.overviewSearchInput.value.trim();
            if (val.length > 0) {
                var allLoaded = tierLoaded.official && tierLoaded.unofficial && tierLoaded.noncanonical;
                if (allLoaded) performOverviewSearch(val);
            }
        }

        scopeTitleCb.addEventListener("change", retriggerOverviewSearch);
        scopeDescCb.addEventListener("change", retriggerOverviewSearch);

        els.overviewSearchInput.addEventListener("input", function () {
            clearTimeout(overviewDebounce);
            var val = els.overviewSearchInput.value.trim();
            readSearchScope();
            overviewDebounce = setTimeout(function () {
                if (val.length === 0) {
                    clearOverviewSearch();
                } else {
                    // Ensure all tier repos + resources are loaded before searching
                    var allLoaded = tierLoaded.official && tierLoaded.unofficial && tierLoaded.noncanonical;
                    if (allLoaded) {
                        performOverviewSearch(val);
                    } else {
                        var info = els["overview-search-info"];
                        info.textContent = "Loading data for search...";
                        info.hidden = false;
                        Promise.all([ensureAllTiers(), ensureAllResources()]).then(function () {
                            // Re-check the input value hasn't changed
                            var current = els.overviewSearchInput.value.trim();
                            if (current.length > 0) performOverviewSearch(current);
                        });
                    }
                }
            }, DEBOUNCE_MS);
        });

        // Keyboard support for category cards
        document.addEventListener("keydown", function (e) {
            if (e.key === "Enter" || e.key === " ") {
                var card = e.target.closest("[data-action='open-category']");
                if (card) {
                    e.preventDefault();
                    var catId = card.getAttribute("data-category-id");
                    if (catId) showDetail(catId);
                }
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
            if (!allData) return;
            var prevScreen = state.screen;
            var prevCat = state.category;
            restoreFromHash();
            if (state.screen === "detail" && state.category !== "all") {
                if (prevScreen !== "detail" || prevCat !== state.category) {
                    showDetail(state.category, true);
                } else {
                    applyAndRender();
                }
            } else {
                showOverview();
            }
        });

        // Navbar hide on scroll down, show on scroll up
        (function () {
            var navbar = document.querySelector(".av-navbar");
            if (!navbar) return;
            var lastY = window.scrollY;
            var threshold = 50;
            window.addEventListener("scroll", function () {
                var y = window.scrollY;
                if (y > lastY && y > threshold) {
                    navbar.classList.add("av-navbar--hidden");
                } else if (y < lastY) {
                    navbar.classList.remove("av-navbar--hidden");
                }
                lastY = y;
            }, { passive: true });
        })();
    }

    // -------------------------------------------------------- Autocomplete
    function showSuggestions(query) {
        if (!searchMeta || !query || query.length < 2) {
            hideSuggestions();
            return;
        }
        var q = query.toLowerCase();
        // Get the last token being typed (after space or |)
        var parts = q.split(/[\s|&]+/);
        var partial = parts[parts.length - 1];
        if (!partial || partial.length < 2) {
            hideSuggestions();
            return;
        }

        var matches = [];
        var suggestions = searchMeta.suggestions || [];
        for (var i = 0; i < suggestions.length; i++) {
            var s = suggestions[i];
            if (s.t.indexOf(partial) === 0 && s.t !== partial) {
                matches.push(s);
                if (matches.length >= 8) break;
            }
        }
        // Also include substring matches if we have room
        if (matches.length < 8) {
            for (var j = 0; j < suggestions.length; j++) {
                var s2 = suggestions[j];
                if (s2.t.indexOf(partial) > 0 && matches.indexOf(s2) === -1) {
                    matches.push(s2);
                    if (matches.length >= 8) break;
                }
            }
        }

        if (matches.length === 0) {
            hideSuggestions();
            return;
        }

        var frag = document.createDocumentFragment();
        for (var k = 0; k < matches.length; k++) {
            var li = document.createElement("li");
            li.className = "av-suggestion-item";
            li.setAttribute("role", "option");
            li.setAttribute("id", "suggest-" + k);
            li.textContent = matches[k].t + " (" + matches[k].c + ")";
            frag.appendChild(li);
        }
        els.suggestions.textContent = "";
        els.suggestions.appendChild(frag);
        els.suggestions.hidden = false;
        els.searchInput.setAttribute("aria-expanded", "true");
        activeSuggestion = -1;
    }

    function hideSuggestions() {
        if (els.suggestions) {
            els.suggestions.hidden = true;
            els.suggestions.textContent = "";
        }
        if (els.searchInput) {
            els.searchInput.setAttribute("aria-expanded", "false");
            els.searchInput.removeAttribute("aria-activedescendant");
        }
    }

    function updateActiveSuggestion(items) {
        for (var i = 0; i < items.length; i++) {
            items[i].classList.toggle("is-active", i === activeSuggestion);
        }
        if (activeSuggestion >= 0 && items[activeSuggestion]) {
            els.searchInput.setAttribute("aria-activedescendant", items[activeSuggestion].id);
        } else {
            els.searchInput.removeAttribute("aria-activedescendant");
        }
    }

    function applySuggestion(term) {
        // Replace the last partial token with the selected suggestion
        var val = els.searchInput.value;
        var parts = val.split(/(\s+|\|)/);
        parts[parts.length - 1] = term;
        els.searchInput.value = parts.join("");
        state.query = els.searchInput.value.trim();
        hideSuggestions();
        applyAndRender();
        els.searchInput.focus();
    }

    // -------------------------------------------------------- Overview search
    function searchResources(query) {
        var resources = (allData && allData.resources) || [];
        if (!query || !resources.length) return [];
        var q = query.toLowerCase();
        var orGroups = q.replace(/&/g, " ").split("|");
        var matched = [];

        for (var i = 0; i < resources.length; i++) {
            var res = resources[i];
            var haystack = ((res.title || "") + " " + (res.description || "") + " " +
                (res.category || "") + " " + (res.subcategory || "") + " " +
                (res.kw || "")).toLowerCase();

            for (var g = 0; g < orGroups.length; g++) {
                var terms = orGroups[g].trim().split(/\s+/).filter(Boolean);
                if (!terms.length) continue;
                var allMatch = true;
                for (var t = 0; t < terms.length; t++) {
                    var pattern = terms[t]
                        .replace(/[.+?^${}()[\]\\]/g, "\\$&")
                        .replace(/\*/g, ".*");
                    try {
                        if (!new RegExp(pattern).test(haystack)) { allMatch = false; break; }
                    } catch (e) {
                        if (haystack.indexOf(terms[t]) === -1) { allMatch = false; break; }
                    }
                }
                if (allMatch) { matched.push(res); break; }
            }
        }
        return matched;
    }

    var overviewSearchActive = false;

    function searchCategories(query) {
        if (!allData || !query) return [];
        var q = query.toLowerCase();
        var orGroups = q.replace(/&/g, " ").split("|");
        var matched = [];

        var allCats = (allData.categories || [])
            .concat(allData.unofficial_categories || [])
            .concat(allData.non_canonical_categories || []);

        for (var i = 0; i < allCats.length; i++) {
            var cat = allCats[i];
            var haystack = ((cat.name || "") + " " + (cat.source_repo || "") + " " + (cat.id || "")).toLowerCase();

            for (var g = 0; g < orGroups.length; g++) {
                var terms = orGroups[g].trim().split(/\s+/).filter(Boolean);
                if (!terms.length) continue;
                var allMatch = true;
                for (var t = 0; t < terms.length; t++) {
                    var pattern = terms[t]
                        .replace(/[.+?^${}()[\]\\]/g, "\\$&")
                        .replace(/\*/g, ".*");
                    try {
                        if (!new RegExp(pattern).test(haystack)) { allMatch = false; break; }
                    } catch (e) {
                        if (haystack.indexOf(terms[t]) === -1) { allMatch = false; break; }
                    }
                }
                if (allMatch) { matched.push(cat); break; }
            }
        }
        return matched;
    }

    function performOverviewSearch(query) {
        if (!searchTokens) buildSearchIndex();

        var rawResults = search(query, true).slice(0, 200);
        var resResults = searchResources(query).slice(0, 20);

        // Search categories (lists) by name and source_repo
        var listResults = searchCategories(query);

        // Apply language/health filters to repo results only (not resources or lists)
        var f = overviewFilter;
        var results = [];
        for (var fi = 0; fi < rawResults.length; fi++) {
            var repo = rawResults[fi];
            if (f.language !== "all" && repo.language !== f.language) continue;
            if (f.minHealth > 0 && (repo.health || 0) < f.minHealth) continue;
            results.push(repo);
        }

        // Apply language/health filters to list results too
        var filteredLists = [];
        for (var li = 0; li < listResults.length; li++) {
            var cat = listResults[li];
            if (f.language !== "all") {
                var hasLang = (cat.top_languages || []).some(function (l) { return l.name === f.language; });
                if (!hasLang) continue;
            }
            if (f.minHealth > 0 && (cat.avg_health || 0) < f.minHealth) continue;
            filteredLists.push(cat);
        }

        var info = els["overview-search-info"];

        // Group list results by tier
        var tierListResults = { official: [], unofficial: [], noncanonical: [] };
        for (var tl = 0; tl < filteredLists.length; tl++) {
            var listTier = catTierMap[filteredLists[tl].id] || "official";
            tierListResults[listTier].push(filteredLists[tl]);
        }

        // Group repo results by tier
        var tierResults = { official: [], unofficial: [], noncanonical: [] };
        for (var i = 0; i < results.length; i++) {
            var tier = catTierMap[results[i].category] || "official";
            tierResults[tier].push(results[i]);
        }

        // Group resource results by tier
        var tierResResults = { official: [], unofficial: [], noncanonical: [] };
        for (var ri = 0; ri < resResults.length; ri++) {
            var resTier = catTierMap[resResults[ri].category] || "official";
            tierResResults[resTier].push(resResults[ri]);
        }

        overviewSearchActive = true;

        // Language/health filters apply to repo results, not resources
        var segKeys = ["official", "unofficial", "noncanonical"];
        for (var s = 0; s < segKeys.length; s++) {
            var segKey = segKeys[s];
            var seg = SEGMENTS[segKey];
            var grid = els[seg.gridRef];
            var toggleBtn = document.querySelector("[aria-controls='" + seg.sectionRef + "']");
            var section = els[seg.sectionRef];
            var lists = tierListResults[segKey];
            var repos = tierResults[segKey];
            var resources = tierResResults[segKey];
            var hasResults = lists.length > 0 || repos.length > 0 || resources.length > 0;

            if (!toggleBtn || !section || !grid) continue;

            if (hasResults) {
                // Show and expand this segment
                toggleBtn.hidden = false;
                section.hidden = false;
                toggleBtn.setAttribute("aria-expanded", "true");
                toggleBtn.classList.add("av-segment-toggle--open");
                var chevron = toggleBtn.querySelector(".av-segment-chevron");
                if (chevron) chevron.classList.add("av-segment-chevron--open");

                // Update count in toggle
                var countEl = els[segKey + "-count"];
                var countParts = [];
                if (lists.length) countParts.push(lists.length + " lists");
                if (repos.length) countParts.push(repos.length + " repos");
                if (resources.length) countParts.push(resources.length + " resources");
                if (countEl) countEl.textContent = countParts.join(", ");

                // Build the grid with section labels
                grid.textContent = "";
                var frag = document.createDocumentFragment();

                if (lists.length > 0) {
                    var listHeading = document.createElement("div");
                    listHeading.className = "av-search-section-label av-search-section-label--first";
                    listHeading.innerHTML = '<svg class="av-icon--sm" aria-hidden="true"><use href="#icon-repo"/></svg> Lists (' + lists.length + ')';
                    frag.appendChild(listHeading);
                    for (var cl = 0; cl < lists.length; cl++) {
                        frag.appendChild(createCategoryCard(lists[cl]));
                    }
                }

                if (repos.length > 0) {
                    var repoHeading = document.createElement("div");
                    repoHeading.className = "av-search-section-label" + (lists.length === 0 ? " av-search-section-label--first" : "");
                    repoHeading.innerHTML = '<svg class="av-icon--sm" aria-hidden="true"><use href="#icon-star"/></svg> Repositories (' + repos.length + ')';
                    frag.appendChild(repoHeading);
                    for (var r = 0; r < repos.length; r++) {
                        frag.appendChild(createCard(repos[r], true));
                    }
                }

                if (resources.length > 0) {
                    var resHeading = document.createElement("div");
                    resHeading.className = "av-search-section-label";
                    resHeading.innerHTML = '<svg class="av-icon--sm" aria-hidden="true"><use href="#icon-link"/></svg> Resource Links (' + resources.length + ')';
                    frag.appendChild(resHeading);
                    for (var j = 0; j < resources.length; j++) {
                        frag.appendChild(createSearchResourceItem(resources[j]));
                    }
                }
                grid.appendChild(frag);
            } else {
                // Hide segment if no results
                toggleBtn.hidden = true;
                section.hidden = true;
            }
        }

        var totalCount = filteredLists.length + results.length + resResults.length;
        if (totalCount === 0) {
            // Show a "no results" message in the first segment
            var firstSeg = SEGMENTS.official;
            var firstGrid = els[firstSeg.gridRef];
            var firstToggle = document.querySelector("[aria-controls='" + firstSeg.sectionRef + "']");
            var firstSection = els[firstSeg.sectionRef];
            if (firstToggle) firstToggle.hidden = false;
            if (firstSection) firstSection.hidden = false;
            if (firstToggle) {
                firstToggle.setAttribute("aria-expanded", "true");
                firstToggle.classList.add("av-segment-toggle--open");
            }
            if (firstGrid) firstGrid.innerHTML = '<div class="av-empty"><div class="av-empty-title">No results found</div><p>Try a different search term</p></div>';
        }

        var infoParts = [];
        if (filteredLists.length) infoParts.push(filteredLists.length + " lists");
        if (results.length) infoParts.push(results.length + " repos");
        if (resResults.length) infoParts.push(resResults.length + " resources");
        info.textContent = totalCount + " matching results" + (infoParts.length > 1 ? " (" + infoParts.join(", ") + ")" : "");
        info.hidden = false;
    }

    function createSearchResourceItem(res) {
        var item = document.createElement("article");
        item.className = "av-card av-card--resource";
        item.setAttribute("role", "listitem");
        var domain = extractDomain(res.url);
        var desc = cleanResourceDesc(res.description);
        item.innerHTML =
            '<div class="av-card-header">' +
                '<h3 class="av-card-title"><a href="' + escAttr(res.url) + '" target="_blank" rel="noopener noreferrer">' + esc(res.title) + '</a></h3>' +
            '</div>' +
            (desc ? '<p class="av-card-desc">' + esc(desc) + '</p>' : '') +
            '<div class="av-card-footer">' +
                '<code class="av-card-domain">' + esc(domain) + '</code>' +
                (res.subcategory ? ' <span class="av-badge av-badge--sub">' + esc(res.subcategory) + '</span>' : '') +
            '</div>';
        return item;
    }

    function clearOverviewSearch() {
        overviewSearchActive = false;
        els["overview-search-info"].hidden = true;
        // Re-render all segments with category cards and restore toggle state
        renderOverview();
    }

    // ----------------------------------------------------------- Resources
    var NOISE_TITLE_RE = /^\[?(All Versions|Preprint|Paper|Project|Website|Code|Homepage|Slides|Video|Demo|Blog|Talk|Poster|Dataset|Models?)\]?$/i;
    var NOISE_RESOURCE_DOMAIN_RE = /scholar\.google\.|img\.shields\.io|awesome\.re/i;

    function getCategoryResources(catId) {
        var resources = (allData && allData.resources) || [];
        return resources.filter(function (r) {
            if (r.category !== catId) return false;
            if (NOISE_TITLE_RE.test(r.title)) return false;
            if (r.title.charAt(0) === "[") return false;
            if (NOISE_RESOURCE_DOMAIN_RE.test(r.url)) return false;
            return true;
        });
    }

    // Resource table column definitions
    var resourceColumns = [
        { id: "title", label: "Title", sortKey: "title" },
        { id: "description", label: "Description", sortKey: null },
        { id: "domain", label: "Domain", sortKey: "domain" },
        { id: "subcategory", label: "Subcategory", sortKey: "subcategory" },
    ];
    var resourceSortKey = "title";
    var resourceSortDir = "asc";

    var NOISE_LINK_RE = /\[(All Versions|Preprint|Paper|Project|Website|Code|Homepage|Slides|Video|Demo|Blog|Talk|Poster|Dataset|Models?)\]\([^)]*\)/gi;

    function cleanResourceDesc(desc) {
        if (!desc) return "";
        // Remove noise markdown links entirely before converting links to text
        desc = desc.replace(NOISE_LINK_RE, "");
        // Convert remaining markdown links to plain text
        desc = desc.replace(/\[([^\]]*)\]\([^)]*\)/g, "$1");
        // Strip bold/italic markers
        desc = desc.replace(/\*{1,3}([^*]+)\*{1,3}/g, "$1");
        // Strip underline/strikethrough
        desc = desc.replace(/_{1,2}([^_]+)_{1,2}/g, "$1");
        desc = desc.replace(/~~([^~]+)~~/g, "$1");
        // Remove plain bracket noise phrases like [All Versions] or [Paper]
        desc = desc.replace(/\[(?:All Versions|Preprint|Paper|Project|Website|Code|Homepage|Slides|Video|Demo|Blog|Talk|Poster|Dataset|Models?|Nature News|web)\]\.?/gi, "");
        // Collapse orphaned punctuation and extra whitespace
        desc = desc.replace(/(?:[.,:;]\s*){2,}/g, ". ");
        desc = desc.replace(/\s{2,}/g, " ");
        return desc.replace(/^[\s.\-]+|[\s.\-]+$/g, "");
    }
    var currentResources = [];

    function extractDomain(url) {
        try {
            var a = document.createElement("a");
            a.href = url;
            return a.hostname.replace(/^www\./, "");
        } catch (e) {
            return "";
        }
    }

    function sortResources(resources, key, dir) {
        var sorted = resources.slice();
        sorted.sort(function (a, b) {
            var va, vb;
            if (key === "domain") {
                va = extractDomain(a.url).toLowerCase();
                vb = extractDomain(b.url).toLowerCase();
            } else if (key === "subcategory") {
                va = (a.subcategory || "").toLowerCase();
                vb = (b.subcategory || "").toLowerCase();
            } else {
                va = (a.title || "").toLowerCase();
                vb = (b.title || "").toLowerCase();
            }
            if (va < vb) return dir === "asc" ? -1 : 1;
            if (va > vb) return dir === "asc" ? 1 : -1;
            return 0;
        });
        return sorted;
    }

    function renderResourceHead() {
        var headRow = els["resources-thead"];
        if (!headRow) return;
        headRow.textContent = "";

        for (var i = 0; i < resourceColumns.length; i++) {
            var col = resourceColumns[i];
            var th = document.createElement("th");
            th.scope = "col";

            if (col.sortKey) {
                th.classList.add("av-table-th--sortable");
                th.setAttribute("data-resource-sort", col.sortKey);

                var isSorted = resourceSortKey === col.sortKey;
                if (isSorted) th.classList.add("av-table-th--sorted");

                var inner = document.createElement("span");
                inner.className = "av-table-th-inner";

                var label = document.createElement("span");
                label.className = "av-table-th-label";
                label.textContent = col.label;
                inner.appendChild(label);

                var chevron = document.createElement("span");
                chevron.className = "av-table-sort-chevron";
                if (isSorted) {
                    chevron.classList.add(resourceSortDir === "asc" ? "av-table-sort-chevron--asc" : "av-table-sort-chevron--desc");
                }
                inner.appendChild(chevron);

                th.appendChild(inner);
            } else {
                th.textContent = col.label;
            }

            headRow.appendChild(th);
        }
    }

    function renderResources(catId) {
        var section = els["resources-section"];
        var grid = els["resources-grid"];
        var countEl = els["resources-count"];
        if (!section || !grid) return;

        currentResources = getCategoryResources(catId);
        resourceSortKey = "title";
        resourceSortDir = "asc";

        if (!currentResources.length) {
            section.hidden = true;
            return;
        }

        section.hidden = false;
        countEl.textContent = currentResources.length + " links";

        // Populate subcategory filter for resources
        var filterSel = els.resourceFilterSubcategory;
        if (filterSel) {
            while (filterSel.options.length > 1) filterSel.remove(1);
            var subCounts = {};
            for (var s = 0; s < currentResources.length; s++) {
                var sub = currentResources[s].subcategory || "General";
                subCounts[sub] = (subCounts[sub] || 0) + 1;
            }
            var subs = Object.keys(subCounts).sort();
            for (var si = 0; si < subs.length; si++) {
                var opt = document.createElement("option");
                opt.value = subs[si];
                opt.textContent = subs[si] + " (" + subCounts[subs[si]] + ")";
                filterSel.appendChild(opt);
            }
            filterSel.value = "all";
        }

        renderResourceHead();
        renderResourceGrid(sortResources(currentResources, resourceSortKey, resourceSortDir));
    }

    function renderResourceGrid(resources) {
        var tbody = els["resources-tbody"];
        if (!tbody) return;
        tbody.textContent = "";

        var frag = document.createDocumentFragment();
        for (var i = 0; i < resources.length; i++) {
            frag.appendChild(createResourceRow(resources[i]));
        }
        tbody.appendChild(frag);
    }

    function createResourceRow(res) {
        var tr = document.createElement("tr");
        var domain = extractDomain(res.url);
        var sub = res.subcategory && res.subcategory !== "General" ? res.subcategory : "";
        var desc = cleanResourceDesc(res.description);

        tr.innerHTML =
            '<td class="av-resource-table-title">' +
                '<a href="' + escAttr(res.url) + '" target="_blank" rel="noopener noreferrer">' + esc(res.title) + '</a>' +
            '</td>' +
            '<td class="av-resource-table-desc">' + esc(desc) + '</td>' +
            '<td class="av-resource-table-domain"><code>' + esc(domain) + '</code></td>' +
            '<td>' + (sub ? '<span class="av-badge av-badge--sub">' + esc(sub) + '</span>' : '') + '</td>';

        return tr;
    }

    // -------------------------------------------------------------- URL state
    function saveToHash() {
        var params = [];
        if (state.screen === "detail" && state.category !== "all") {
            params.push("cat=" + encodeURIComponent(state.category));
            if (state.query) params.push("q=" + encodeURIComponent(state.query));
            if (state.subcategory !== "all") params.push("sub=" + encodeURIComponent(state.subcategory));
            if (state.language !== "all") params.push("lang=" + encodeURIComponent(state.language));
            if (state.minHealth > 0) params.push("health=" + state.minHealth);
            if (state.sortKey !== "stars" || state.sortDir !== "desc") params.push("sort=" + state.sortKey + "-" + state.sortDir);
            if (state.view !== "grid") params.push("view=" + state.view);
            if (state.page > 1) params.push("page=" + state.page);
        }

        var hash = params.length ? "#" + params.join("&") : "";
        if (window.location.hash !== hash) {
            history.pushState(null, "", hash || window.location.pathname);
        }
    }

    function restoreFromHash() {
        var hash = window.location.hash.slice(1);
        if (!hash) {
            state.screen = "overview";
            state.category = "all";
            return;
        }

        var params = {};
        hash.split("&").forEach(function (pair) {
            var kv = pair.split("=");
            if (kv.length === 2) params[kv[0]] = decodeURIComponent(kv[1]);
        });

        if (params.cat) {
            state.screen = "detail";
            state.category = params.cat;
        } else {
            state.screen = "overview";
            state.category = "all";
        }
        if (params.q !== undefined) state.query = params.q;
        if (params.sub) state.subcategory = params.sub;
        if (params.lang) state.language = params.lang;
        if (params.health) state.minHealth = parseInt(params.health, 10) || 0;
        if (params.sort) {
            var lastDash = params.sort.lastIndexOf("-");
            state.sortKey = params.sort.substring(0, lastDash);
            state.sortDir = params.sort.substring(lastDash + 1) || "desc";
        }
        if (params.view) state.view = params.view;
        if (params.page) state.page = parseInt(params.page, 10) || 1;
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

    // ----------------------------------------------------------------- Start
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
