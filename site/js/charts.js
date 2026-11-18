/**
 * Awesome Visualizer - Custom Chart Engine
 *
 * Zero-dependency, SVG-based chart library. Renders directly into
 * container elements. All colors use --av-* CSS custom properties.
 *
 * Exports a global `AVCharts` object with factory methods:
 *   - donut(container, data, opts)
 *   - bar(container, data, opts)
 *   - bubble(container, data, opts)
 *   - horizontalBar(container, data, opts)
 */
(function () {
    "use strict";

    var NS = "http://www.w3.org/2000/svg";

    // Palette for chart segments (references CSS custom properties via inline style)
    var PALETTE = [
        "var(--av-primary)",
        "var(--av-success)",
        "var(--av-info)",
        "var(--av-warning)",
        "var(--av-danger)",
        "#6e4a7e",
        "#00ADD8",
        "#f1e05a",
        "#3572A5",
        "#dea584",
        "#F05138",
        "#b07219",
        "#4F5D95",
        "#178600",
        "#A97BFF",
        "#89e051",
        "#c22d40"
    ];

    // --------------------------------------------------------------- Helpers

    function svgEl(tag, attrs) {
        var el = document.createElementNS(NS, tag);
        if (attrs) {
            for (var key in attrs) {
                if (attrs.hasOwnProperty(key)) {
                    el.setAttribute(key, attrs[key]);
                }
            }
        }
        return el;
    }

    function createSvg(width, height, vb) {
        return svgEl("svg", {
            width: "100%",
            height: "100%",
            viewBox: vb || ("0 0 " + width + " " + height),
            "aria-hidden": "true"
        });
    }

    function polarToCartesian(cx, cy, r, angleDeg) {
        var rad = (angleDeg - 90) * Math.PI / 180;
        return {
            x: cx + r * Math.cos(rad),
            y: cy + r * Math.sin(rad)
        };
    }

    function describeArc(cx, cy, r, startAngle, endAngle) {
        var start = polarToCartesian(cx, cy, r, endAngle);
        var end = polarToCartesian(cx, cy, r, startAngle);
        var large = endAngle - startAngle > 180 ? 1 : 0;
        return [
            "M", start.x, start.y,
            "A", r, r, 0, large, 0, end.x, end.y
        ].join(" ");
    }

    function escText(s) {
        var d = document.createElement("div");
        d.textContent = s;
        return d.innerHTML;
    }

    // ----------------------------------------------------------- Tooltip

    var tooltipEl = null;

    function getTooltip() {
        if (!tooltipEl) {
            tooltipEl = document.getElementById("chart-tooltip");
            if (!tooltipEl) {
                tooltipEl = document.createElement("div");
                tooltipEl.id = "chart-tooltip";
                tooltipEl.className = "av-tooltip";
                tooltipEl.setAttribute("role", "tooltip");
                tooltipEl.hidden = true;
                document.body.appendChild(tooltipEl);
            }
        }
        return tooltipEl;
    }

    function showTooltip(html, e) {
        var tip = getTooltip();
        tip.innerHTML = html;
        tip.hidden = false;
        positionTooltip(e);
    }

    function positionTooltip(e) {
        var tip = getTooltip();
        var pad = 12;
        var x = e.clientX + pad;
        var y = e.clientY + pad;
        var w = tip.offsetWidth;
        var h = tip.offsetHeight;
        if (x + w > window.innerWidth - pad) x = e.clientX - w - pad;
        if (y + h > window.innerHeight - pad) y = e.clientY - h - pad;
        if (x < pad) x = pad;
        if (y < pad) y = pad;
        tip.style.left = x + "px";
        tip.style.top = y + "px";
    }

    // Throttled version for mousemove - max one reflow per animation frame
    var _rafId = 0;
    function throttledPositionTooltip(e) {
        if (_rafId) return;
        _rafId = requestAnimationFrame(function () {
            _rafId = 0;
            positionTooltip(e);
        });
    }

    function hideTooltip() {
        var tip = getTooltip();
        tip.hidden = true;
    }

    // ----------------------------------------------------------- Donut chart

    function donut(container, data, opts) {
        opts = opts || {};
        var size = opts.size || 200;
        var thickness = opts.thickness || 28;
        var cx = size / 2;
        var cy = size / 2;
        var r = (size - thickness) / 2;
        var total = 0;

        for (var i = 0; i < data.length; i++) total += data[i].count || 0;
        if (total === 0) return;

        container.textContent = "";

        var wrap = document.createElement("div");
        wrap.className = "av-chart-donut";

        var svg = createSvg(size, size);
        svg.style.display = "block";

        var angle = 0;
        var GAP = 1.5;

        for (var j = 0; j < data.length; j++) {
            var slice = data[j];
            var pct = (slice.count / total) * 360;
            if (pct < 0.5) continue;

            var startAngle = angle + GAP / 2;
            var endAngle = angle + pct - GAP / 2;

            if (endAngle - startAngle > 0.5) {
                var path = svgEl("path", {
                    d: describeArc(cx, cy, r, startAngle, endAngle),
                    fill: "none",
                    stroke: slice.color || PALETTE[j % PALETTE.length],
                    "stroke-width": thickness,
                    "stroke-linecap": "round",
                    "class": "av-chart-arc",
                    "data-chart-index": String(j)
                });

                // Interactive tooltip and hover dimming
                (function (arcPath, arcSlice, arcSvg) {
                    arcPath.addEventListener("mouseenter", function (e) {
                        var arcs = arcSvg.querySelectorAll(".av-chart-arc");
                        for (var a = 0; a < arcs.length; a++) {
                            arcs[a].setAttribute("opacity", arcs[a] === arcPath ? "1" : "0.3");
                        }
                        var pctVal = arcSlice.pct || Math.round(arcSlice.count / total * 100);
                        showTooltip(
                            '<strong>' + escText(arcSlice.name) + '</strong><br>' +
                            arcSlice.count + ' repos (' + pctVal + '%)', e
                        );
                    });
                    arcPath.addEventListener("mousemove", function (e) { throttledPositionTooltip(e); });
                    arcPath.addEventListener("mouseleave", function () {
                        var arcs = arcSvg.querySelectorAll(".av-chart-arc");
                        for (var a = 0; a < arcs.length; a++) {
                            arcs[a].removeAttribute("opacity");
                        }
                        hideTooltip();
                    });
                    if (opts.onClick) {
                        arcPath.style.cursor = "pointer";
                        arcPath.addEventListener("click", function () { opts.onClick(arcSlice); });
                    }
                })(path, slice, svg);

                svg.appendChild(path);
            }
            angle += pct;
        }

        // Center label
        var centerText = svgEl("text", {
            x: cx,
            y: cy - 6,
            "text-anchor": "middle",
            "font-size": "24",
            "font-weight": "700",
            fill: "var(--av-text)",
            "class": "av-chart-center-number"
        });
        centerText.textContent = total >= 1000 ? Math.round(total / 1000) + "k" : total;
        svg.appendChild(centerText);

        var subText = svgEl("text", {
            x: cx,
            y: cy + 14,
            "text-anchor": "middle",
            "font-size": "11",
            fill: "var(--av-text-tertiary)",
            "class": "av-chart-center-label"
        });
        subText.textContent = opts.centerLabel || "total";
        svg.appendChild(subText);

        wrap.appendChild(svg);

        // Legend
        if (opts.legend !== false) {
            var legend = document.createElement("ul");
            legend.className = "av-chart-legend";
            for (var k = 0; k < data.length; k++) {
                var item = data[k];
                var li = document.createElement("li");
                li.className = "av-chart-legend-item";
                li.setAttribute("data-chart-index", String(k));
                li.innerHTML =
                    '<span class="av-chart-legend-dot" style="--dot-color:' + (item.color || PALETTE[k % PALETTE.length]) + '"></span>' +
                    '<span class="av-chart-legend-label">' + escText(item.name) + '</span>' +
                    '<span class="av-chart-legend-value">' + (item.pct || Math.round(item.count / total * 100)) + '%</span>';

                // Cross-highlight arcs from legend
                (function (legendLi, idx, svgRef) {
                    legendLi.addEventListener("mouseenter", function () {
                        var arcs = svgRef.querySelectorAll(".av-chart-arc");
                        for (var a = 0; a < arcs.length; a++) {
                            arcs[a].setAttribute("opacity", arcs[a].getAttribute("data-chart-index") === String(idx) ? "1" : "0.3");
                        }
                    });
                    legendLi.addEventListener("mouseleave", function () {
                        var arcs = svgRef.querySelectorAll(".av-chart-arc");
                        for (var a = 0; a < arcs.length; a++) {
                            arcs[a].removeAttribute("opacity");
                        }
                    });
                    if (opts.onClick) {
                        legendLi.style.cursor = "pointer";
                        legendLi.addEventListener("click", function () { opts.onClick(item); });
                    }
                })(li, k, svg);

                legend.appendChild(li);
            }
            wrap.appendChild(legend);
        }

        container.appendChild(wrap);
    }

    // ------------------------------------------------------------ Bar chart

    function bar(container, data, opts) {
        opts = opts || {};
        var barHeight = opts.barHeight || 28;
        var gap = opts.gap || 6;
        var labelWidth = opts.labelWidth || 60;
        var valueWidth = 50;
        var chartWidth = 400;
        var totalHeight = data.length * (barHeight + gap);

        container.textContent = "";

        var wrap = document.createElement("div");
        wrap.className = "av-chart-bars";

        var maxVal = 0;
        for (var i = 0; i < data.length; i++) {
            if (data[i].count > maxVal) maxVal = data[i].count;
        }
        if (maxVal === 0) return;

        for (var j = 0; j < data.length; j++) {
            var d = data[j];
            var pct = (d.count / maxVal) * 100;
            var color = d.color || healthBucketColor(d.label) || PALETTE[j % PALETTE.length];

            var row = document.createElement("div");
            row.className = "av-chart-bar-row";

            row.innerHTML =
                '<span class="av-chart-bar-label">' + escText(d.label) + '</span>' +
                '<div class="av-chart-bar-track">' +
                    '<div class="av-chart-bar-fill" style="--bar-pct:' + pct + '%;--bar-color:' + color + '"></div>' +
                '</div>' +
                '<span class="av-chart-bar-value">' + formatCount(d.count) + '</span>';

            // Interactive tooltip
            (function (barRow, barData) {
                var suffix = opts.suffix || "repos";
                barRow.addEventListener("mouseenter", function (e) {
                    barRow.classList.add("is-active");
                    showTooltip('<strong>' + escText(barData.label) + '</strong><br>' + formatCount(barData.count) + ' ' + suffix, e);
                });
                barRow.addEventListener("mousemove", function (e) { throttledPositionTooltip(e); });
                barRow.addEventListener("mouseleave", function () {
                    barRow.classList.remove("is-active");
                    hideTooltip();
                });
                if (opts.onClick) {
                    barRow.style.cursor = "pointer";
                    barRow.addEventListener("click", function () { opts.onClick(barData); });
                }
            })(row, d);

            wrap.appendChild(row);
        }

        container.appendChild(wrap);
    }

    function healthBucketColor(label) {
        if (!label) return null;
        if (label.indexOf("80") !== -1 || label === "80-100") return "var(--av-success)";
        if (label.indexOf("60") !== -1 || label === "60-79") return "var(--av-info)";
        if (label.indexOf("40") !== -1 || label === "40-59") return "var(--av-warning)";
        if (label.indexOf("20") !== -1 || label === "20-39") return "var(--av-danger)";
        if (label.indexOf("0-") !== -1 || label === "0-19") return "var(--av-danger)";
        return null;
    }

    // --------------------------------------------------------- Bubble chart

    // Tier shape config: official=circle, unofficial=square, noncanonical=diamond
    var TIER_SHAPES = {
        official:     { shape: "circle",  label: "Official" },
        unofficial:   { shape: "square",  label: "Unofficial" },
        noncanonical: { shape: "diamond", label: "Non-canonical" }
    };
    var TIER_ORDER = ["official", "unofficial", "noncanonical"];

    function createBubbleShape(shape, x, y, r, color) {
        var el;
        if (shape === "square") {
            el = svgEl("rect", {
                x: x - r, y: y - r,
                width: r * 2, height: r * 2,
                rx: "2", ry: "2",
                fill: color, opacity: "0.7",
                stroke: color, "stroke-width": "1.5",
                filter: "url(#av-bubble-shadow)"
            });
        } else if (shape === "diamond") {
            var pts = [
                x + "," + (y - r * 1.15),
                (x + r * 1.15) + "," + y,
                x + "," + (y + r * 1.15),
                (x - r * 1.15) + "," + y
            ].join(" ");
            el = svgEl("polygon", {
                points: pts,
                fill: color, opacity: "0.7",
                stroke: color, "stroke-width": "1.5",
                filter: "url(#av-bubble-shadow)"
            });
        } else {
            el = svgEl("circle", {
                cx: x, cy: y, r: r,
                fill: color, opacity: "0.7",
                stroke: color, "stroke-width": "1.5",
                filter: "url(#av-bubble-shadow)"
            });
        }
        return el;
    }

    function bubble(container, data, opts) {
        opts = opts || {};
        var width = opts.width || 600;
        var height = opts.height || 400;
        var maxBubbles = opts.max || 50;
        var tierField = opts.tierField || "tier";
        var MIN_ZOOM = 1;
        var MAX_ZOOM = 3;

        container.textContent = "";

        var items = data.slice(0, maxBubbles);
        if (!items.length) return;

        // Track which tiers are present in the data
        var presentTiers = {};
        for (var pi = 0; pi < items.length; pi++) {
            presentTiers[items[pi][tierField] || "official"] = true;
        }

        // Find ranges for scaling
        var maxCount = 0;
        var maxHealth = 0;
        var maxStars = 0;
        for (var i = 0; i < items.length; i++) {
            if (items[i].count > maxCount) maxCount = items[i].count;
            if (items[i].health > maxHealth) maxHealth = items[i].health;
            if (items[i].stars > maxStars) maxStars = items[i].stars;
        }

        var wrap = document.createElement("div");
        wrap.className = "av-chart-bubble";
        wrap.setAttribute("tabindex", "0");

        // Tier filter checkboxes
        var tierVisibility = {};
        var tierBar = document.createElement("div");
        tierBar.className = "av-chart-bubble-tiers";
        for (var ti = 0; ti < TIER_ORDER.length; ti++) {
            var tKey = TIER_ORDER[ti];
            if (!presentTiers[tKey]) continue;
            tierVisibility[tKey] = true;
            var tLabel = document.createElement("label");
            tLabel.className = "av-chart-bubble-tier-label";
            var tCb = document.createElement("input");
            tCb.type = "checkbox";
            tCb.checked = true;
            tCb.setAttribute("data-tier", tKey);
            tCb.className = "av-chart-bubble-tier-cb";
            var tShape = document.createElement("span");
            tShape.className = "av-chart-bubble-tier-icon av-chart-bubble-tier-icon--" + TIER_SHAPES[tKey].shape;
            var tText = document.createElement("span");
            tText.textContent = TIER_SHAPES[tKey].label;
            tLabel.appendChild(tCb);
            tLabel.appendChild(tShape);
            tLabel.appendChild(tText);
            tierBar.appendChild(tLabel);
        }
        wrap.appendChild(tierBar);

        var svg = createSvg(width, height);
        svg.setAttribute("class", "av-chart-bubble-svg");

        // Shadow filter
        var defs = svgEl("defs", {});
        var filter = svgEl("filter", { id: "av-bubble-shadow", x: "-30%", y: "-30%", width: "160%", height: "160%" });
        var shadow = svgEl("feDropShadow", { dx: "0", dy: "2", stdDeviation: "3", "flood-color": "rgba(0,0,0,0.45)", "flood-opacity": "1" });
        filter.appendChild(shadow);
        defs.appendChild(filter);
        svg.appendChild(defs);

        var padding = 50;
        var plotW = width - padding * 2;
        var plotH = height - padding * 2;

        // Content group for zoom/pan transforms
        var contentG = svgEl("g", { "class": "av-chart-bubble-content" });

        // Grid lines
        var gridTicks = 5;
        for (var gi = 0; gi <= gridTicks; gi++) {
            var gx = padding + (gi / gridTicks) * plotW;
            var gy = padding + (gi / gridTicks) * plotH;
            // Vertical grid line
            var vLine = svgEl("line", {
                x1: gx, y1: padding, x2: gx, y2: padding + plotH,
                stroke: "var(--av-border)", "stroke-width": "0.5", "stroke-dasharray": "4 4"
            });
            contentG.appendChild(vLine);
            // Horizontal grid line
            var hLine = svgEl("line", {
                x1: padding, y1: gy, x2: padding + plotW, y2: gy,
                stroke: "var(--av-border)", "stroke-width": "0.5", "stroke-dasharray": "4 4"
            });
            contentG.appendChild(hLine);
        }

        // Axis tick labels
        for (var tki = 0; tki <= gridTicks; tki++) {
            var starVal = maxStars > 0 ? Math.round((tki / gridTicks) * maxStars) : 0;
            var healthVal = maxHealth > 0 ? Math.round(((gridTicks - tki) / gridTicks) * maxHealth) : 0;
            // X-axis ticks
            var xTick = svgEl("text", {
                x: padding + (tki / gridTicks) * plotW,
                y: padding + plotH + 16,
                "text-anchor": "middle",
                "font-size": "7",
                fill: "var(--av-text-tertiary)"
            });
            xTick.textContent = formatCount(starVal);
            contentG.appendChild(xTick);
            // Y-axis ticks
            var yTick = svgEl("text", {
                x: padding - 8,
                y: padding + (tki / gridTicks) * plotH + 3,
                "text-anchor": "end",
                "font-size": "7",
                fill: "var(--av-text-tertiary)"
            });
            yTick.textContent = healthVal;
            contentG.appendChild(yTick);
        }

        // Axes labels
        var xLabel = svgEl("text", {
            x: width / 2,
            y: height - 4,
            "text-anchor": "middle",
            "font-size": "8",
            fill: "var(--av-text-tertiary)"
        });
        xLabel.textContent = "Avg Stars";
        contentG.appendChild(xLabel);

        var yLabel = svgEl("text", {
            x: 10,
            y: height / 2,
            "text-anchor": "middle",
            "font-size": "8",
            fill: "var(--av-text-tertiary)",
            transform: "rotate(-90 10 " + (height / 2) + ")"
        });
        yLabel.textContent = "Avg Health";
        contentG.appendChild(yLabel);

        // Plot bubbles - grouped by tier for easier toggling
        var minR = 6;
        var maxR = 30;
        var tierGroups = {};

        for (var j = 0; j < items.length; j++) {
            var b = items[j];
            var bTier = b[tierField] || "official";
            var shape = (TIER_SHAPES[bTier] || TIER_SHAPES.official).shape;
            var x = padding + (maxStars > 0 ? (b.stars / maxStars) * plotW : plotW / 2);
            var y = padding + plotH - (maxHealth > 0 ? (b.health / maxHealth) * plotH : plotH / 2);
            var r = minR + (maxCount > 0 ? (b.count / maxCount) * (maxR - minR) : minR);
            var color = healthColorForScore(b.health);

            if (!tierGroups[bTier]) {
                tierGroups[bTier] = svgEl("g", {
                    "class": "av-chart-bubble-tier-group",
                    "data-tier": bTier
                });
            }

            var g = svgEl("g", { "class": "av-chart-bubble-node" });

            var shapeEl = createBubbleShape(shape, x, y, r, color);
            g.appendChild(shapeEl);

            // Interactive tooltip and hover
            (function (bubbleG, bShape, bubbleData, bTierName) {
                bubbleG.addEventListener("mouseenter", function (e) {
                    bShape.setAttribute("opacity", "1");
                    bShape.setAttribute("stroke-width", "3");
                    showTooltip(
                        '<strong>' + escText(bubbleData.name) + '</strong><br>' +
                        '<span class="av-tooltip-tier">' + escText((TIER_SHAPES[bTierName] || TIER_SHAPES.official).label) + '</span><br>' +
                        bubbleData.count + ' repos<br>' +
                        'Health: ' + bubbleData.health + '<br>' +
                        'Avg stars: ' + formatCount(bubbleData.stars), e
                    );
                });
                bubbleG.addEventListener("mousemove", function (e) { throttledPositionTooltip(e); });
                bubbleG.addEventListener("mouseleave", function () {
                    bShape.setAttribute("opacity", "0.7");
                    bShape.setAttribute("stroke-width", "1.5");
                    hideTooltip();
                });
                if (opts.onClick) {
                    bubbleG.style.cursor = "pointer";
                    bubbleG.addEventListener("click", function () { opts.onClick(bubbleData); });
                }
            })(g, shapeEl, b, bTier);

            // Label - font size proportional to radius
            var fontSize = Math.max(6, Math.min(r * 0.55, 12));
            var maxChars = Math.max(4, Math.round(r * 0.8));
            var label = svgEl("text", {
                x: x,
                y: y + fontSize * 0.35,
                "text-anchor": "middle",
                "font-size": String(fontSize),
                fill: "var(--av-text)",
                "class": "av-chart-bubble-label"
            });
            label.textContent = truncate(b.name, maxChars);

            if (opts.onClick) {
                label.style.cursor = "pointer";
                (function (lbl, bubbleData) {
                    lbl.addEventListener("click", function () { opts.onClick(bubbleData); });
                })(label, b);
            }

            g.appendChild(label);
            tierGroups[bTier].appendChild(g);
        }

        // Append tier groups in order
        for (var tg = 0; tg < TIER_ORDER.length; tg++) {
            if (tierGroups[TIER_ORDER[tg]]) {
                contentG.appendChild(tierGroups[TIER_ORDER[tg]]);
            }
        }

        svg.appendChild(contentG);

        // Health color legend
        var legendG = svgEl("g", { "class": "av-chart-bubble-legend" });
        var legendItems = [
            { label: "80-100", color: "var(--av-success)" },
            { label: "60-79", color: "var(--av-info)" },
            { label: "40-59", color: "var(--av-warning)" },
            { label: "0-39", color: "var(--av-danger)" }
        ];
        var lgX = width - 72;
        var lgY = 8;
        var lgSpacing = 13;
        for (var li = 0; li < legendItems.length; li++) {
            var lgItem = legendItems[li];
            var lgCircle = svgEl("circle", {
                cx: lgX, cy: lgY + li * lgSpacing, r: "4",
                fill: lgItem.color, opacity: "0.8"
            });
            legendG.appendChild(lgCircle);
            var lgText = svgEl("text", {
                x: lgX + 8, y: lgY + li * lgSpacing + 3,
                "font-size": "7", fill: "var(--av-text-secondary)"
            });
            lgText.textContent = lgItem.label;
            legendG.appendChild(lgText);
        }

        // Shape legend under health legend
        var shpY = lgY + legendItems.length * lgSpacing + 8;
        var shpItems = [
            { shape: "circle",  label: "Official" },
            { shape: "square",  label: "Unofficial" },
            { shape: "diamond", label: "Non-canonical" }
        ];
        for (var si = 0; si < shpItems.length; si++) {
            if (!presentTiers[TIER_ORDER[si]]) continue;
            var sx = lgX;
            var sy = shpY + si * lgSpacing;
            if (shpItems[si].shape === "circle") {
                legendG.appendChild(svgEl("circle", {
                    cx: sx, cy: sy, r: "4",
                    fill: "var(--av-text-secondary)", opacity: "0.7"
                }));
            } else if (shpItems[si].shape === "square") {
                legendG.appendChild(svgEl("rect", {
                    x: sx - 4, y: sy - 4, width: "8", height: "8", rx: "1",
                    fill: "var(--av-text-secondary)", opacity: "0.7"
                }));
            } else {
                legendG.appendChild(svgEl("polygon", {
                    points: sx + "," + (sy - 5) + " " + (sx + 5) + "," + sy + " " + sx + "," + (sy + 5) + " " + (sx - 5) + "," + sy,
                    fill: "var(--av-text-secondary)", opacity: "0.7"
                }));
            }
            var shpText = svgEl("text", {
                x: sx + 8, y: sy + 3,
                "font-size": "7", fill: "var(--av-text-secondary)"
            });
            shpText.textContent = shpItems[si].label;
            legendG.appendChild(shpText);
        }

        svg.appendChild(legendG);

        // Bubble size legend
        var sizeY = shpY + shpItems.length * lgSpacing + 2;
        var sizeLabel = svgEl("text", {
            x: lgX - 4, y: sizeY,
            "font-size": "7", fill: "var(--av-text-tertiary)"
        });
        sizeLabel.textContent = "Size = repo count";
        svg.appendChild(sizeLabel);

        wrap.appendChild(svg);

        // --- Tier checkbox toggle ---
        tierBar.addEventListener("change", function (e) {
            var cb = e.target;
            if (!cb.getAttribute("data-tier")) return;
            var tier = cb.getAttribute("data-tier");
            tierVisibility[tier] = cb.checked;
            var grp = contentG.querySelector('[data-tier="' + tier + '"]');
            if (grp) grp.setAttribute("display", cb.checked ? "" : "none");
        });

        // --- Zoom & pan ---
        var zoomState = { scale: 1, tx: 0, ty: 0, dragging: false, startX: 0, startY: 0, startTx: 0, startTy: 0 };

        // Zoom level indicator
        var zoomIndicator = document.createElement("span");
        zoomIndicator.className = "av-chart-bubble-zoom-level";
        zoomIndicator.textContent = "1.0x";
        zoomIndicator.hidden = true;

        function applyTransform() {
            contentG.setAttribute("transform",
                "translate(" + zoomState.tx + "," + zoomState.ty + ") " +
                "scale(" + zoomState.scale + ")");
        }

        function updateZoomUI() {
            var isDefault = (zoomState.scale === 1 && zoomState.tx === 0 && zoomState.ty === 0);
            resetBtn.hidden = isDefault;
            zoomIndicator.hidden = isDefault;
            zoomIndicator.textContent = zoomState.scale.toFixed(1) + "x";
        }

        function zoomToPoint(svgX, svgY, factor) {
            var oldScale = zoomState.scale;
            var newScale = Math.max(MIN_ZOOM, Math.min(oldScale * factor, MAX_ZOOM));
            zoomState.tx = svgX - (svgX - zoomState.tx) * (newScale / oldScale);
            zoomState.ty = svgY - (svgY - zoomState.ty) * (newScale / oldScale);
            zoomState.scale = newScale;
            applyTransform();
            updateZoomUI();
        }

        function screenToSvg(clientX, clientY) {
            var rect = svg.getBoundingClientRect();
            return {
                x: (clientX - rect.left) * (width / rect.width),
                y: (clientY - rect.top) * (height / rect.height)
            };
        }

        // Wheel zoom
        svg.addEventListener("wheel", function (e) {
            e.preventDefault();
            var pt = screenToSvg(e.clientX, e.clientY);
            var factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
            zoomToPoint(pt.x, pt.y, factor);
        });

        // Double-click to zoom in
        svg.addEventListener("dblclick", function (e) {
            e.preventDefault();
            var pt = screenToSvg(e.clientX, e.clientY);
            zoomToPoint(pt.x, pt.y, 1.5);
        });

        // Drag to pan
        svg.addEventListener("mousedown", function (e) {
            if (e.button !== 0) return;
            zoomState.dragging = true;
            zoomState.startX = e.clientX;
            zoomState.startY = e.clientY;
            zoomState.startTx = zoomState.tx;
            zoomState.startTy = zoomState.ty;
            svg.style.cursor = "grabbing";
            e.preventDefault();
        });

        function onMouseMove(e) {
            if (!zoomState.dragging) return;
            var rect = svg.getBoundingClientRect();
            var dx = (e.clientX - zoomState.startX) * (width / rect.width);
            var dy = (e.clientY - zoomState.startY) * (height / rect.height);
            zoomState.tx = zoomState.startTx + dx;
            zoomState.ty = zoomState.startTy + dy;
            applyTransform();
        }

        function onMouseUp() {
            if (!zoomState.dragging) return;
            zoomState.dragging = false;
            svg.style.cursor = "";
        }

        document.addEventListener("mousemove", onMouseMove);
        document.addEventListener("mouseup", onMouseUp);

        // Touch support for pinch-zoom and pan
        var lastTouchDist = 0;
        var lastTouchCenter = null;

        svg.addEventListener("touchstart", function (e) {
            if (e.touches.length === 1) {
                zoomState.dragging = true;
                zoomState.startX = e.touches[0].clientX;
                zoomState.startY = e.touches[0].clientY;
                zoomState.startTx = zoomState.tx;
                zoomState.startTy = zoomState.ty;
            } else if (e.touches.length === 2) {
                zoomState.dragging = false;
                var dx = e.touches[1].clientX - e.touches[0].clientX;
                var dy = e.touches[1].clientY - e.touches[0].clientY;
                lastTouchDist = Math.sqrt(dx * dx + dy * dy);
                lastTouchCenter = {
                    x: (e.touches[0].clientX + e.touches[1].clientX) / 2,
                    y: (e.touches[0].clientY + e.touches[1].clientY) / 2
                };
            }
            e.preventDefault();
        }, { passive: false });

        svg.addEventListener("touchmove", function (e) {
            if (e.touches.length === 1 && zoomState.dragging) {
                var rect = svg.getBoundingClientRect();
                var dx = (e.touches[0].clientX - zoomState.startX) * (width / rect.width);
                var dy = (e.touches[0].clientY - zoomState.startY) * (height / rect.height);
                zoomState.tx = zoomState.startTx + dx;
                zoomState.ty = zoomState.startTy + dy;
                applyTransform();
            } else if (e.touches.length === 2 && lastTouchDist > 0) {
                var tdx = e.touches[1].clientX - e.touches[0].clientX;
                var tdy = e.touches[1].clientY - e.touches[0].clientY;
                var dist = Math.sqrt(tdx * tdx + tdy * tdy);
                var factor = dist / lastTouchDist;
                var newScale = Math.max(MIN_ZOOM, Math.min(zoomState.scale * factor, MAX_ZOOM));

                var rect2 = svg.getBoundingClientRect();
                var cx = ((e.touches[0].clientX + e.touches[1].clientX) / 2 - rect2.left) * (width / rect2.width);
                var cy = ((e.touches[0].clientY + e.touches[1].clientY) / 2 - rect2.top) * (height / rect2.height);
                zoomState.tx = cx - (cx - zoomState.tx) * (newScale / zoomState.scale);
                zoomState.ty = cy - (cy - zoomState.ty) * (newScale / zoomState.scale);
                zoomState.scale = newScale;
                lastTouchDist = dist;
                applyTransform();
                updateZoomUI();
            }
            e.preventDefault();
        }, { passive: false });

        svg.addEventListener("touchend", function () {
            zoomState.dragging = false;
            lastTouchDist = 0;
            lastTouchCenter = null;
        });

        // Reset zoom button
        var resetBtn = document.createElement("button");
        resetBtn.type = "button";
        resetBtn.className = "av-chart-bubble-reset";
        resetBtn.setAttribute("aria-label", "Reset zoom");
        resetBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M1.5 1v4.5h4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M2.2 10.5a6 6 0 1 0 .9-5.5L1.5 5.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
        resetBtn.hidden = true;

        resetBtn.addEventListener("click", function () {
            zoomState.scale = 1;
            zoomState.tx = 0;
            zoomState.ty = 0;
            applyTransform();
            updateZoomUI();
        });

        wrap.appendChild(resetBtn);
        wrap.appendChild(zoomIndicator);

        // Keyboard shortcuts (+/- zoom, 0 reset)
        wrap.addEventListener("keydown", function (e) {
            var key = e.key;
            if (key === "+" || key === "=") {
                e.preventDefault();
                zoomToPoint(width / 2, height / 2, 1.25);
            } else if (key === "-" || key === "_") {
                e.preventDefault();
                zoomToPoint(width / 2, height / 2, 1 / 1.25);
            } else if (key === "0") {
                e.preventDefault();
                zoomState.scale = 1;
                zoomState.tx = 0;
                zoomState.ty = 0;
                applyTransform();
                updateZoomUI();
            }
        });

        // Zoom hint
        var hint = document.createElement("div");
        hint.className = "av-chart-bubble-hint";
        hint.textContent = "Scroll to zoom, drag to pan, double-click to zoom in, +/- keys";
        wrap.appendChild(hint);

        container.appendChild(wrap);
    }

    // -------------------------------------------------- Horizontal bar chart

    function horizontalBar(container, data, opts) {
        opts = opts || {};
        container.textContent = "";

        var wrap = document.createElement("div");
        wrap.className = "av-chart-hbar";

        var maxVal = 0;
        for (var i = 0; i < data.length; i++) {
            var val = data[i].health || data[i].count || 0;
            if (val > maxVal) maxVal = val;
        }
        if (maxVal === 0) return;

        for (var j = 0; j < data.length; j++) {
            var d = data[j];
            val = d.health || d.count || 0;
            var pct = (val / maxVal) * 100;
            var color = d.color || healthColorForScore(d.health || 0) || PALETTE[j % PALETTE.length];

            var row = document.createElement("div");
            row.className = "av-chart-hbar-row";

            row.innerHTML =
                '<span class="av-chart-hbar-label">' + escText(d.name) + '</span>' +
                '<div class="av-chart-hbar-track">' +
                    '<div class="av-chart-hbar-fill" style="--bar-pct:' + pct + '%;--bar-color:' + color + '"></div>' +
                '</div>' +
                '<span class="av-chart-hbar-value">' + val + '</span>';

            // Interactive tooltip
            (function (barRow, barData, barVal) {
                barRow.addEventListener("mouseenter", function (e) {
                    barRow.classList.add("is-active");
                    showTooltip('<strong>' + escText(barData.name) + '</strong><br>Health: ' + barVal, e);
                });
                barRow.addEventListener("mousemove", function (e) { throttledPositionTooltip(e); });
                barRow.addEventListener("mouseleave", function () {
                    barRow.classList.remove("is-active");
                    hideTooltip();
                });
                if (opts.onClick) {
                    barRow.style.cursor = "pointer";
                    barRow.addEventListener("click", function () { opts.onClick(barData); });
                }
            })(row, d, val);

            wrap.appendChild(row);
        }

        container.appendChild(wrap);
    }

    // --------------------------------------------------- Stacked area chart

    function stackedArea(container, data, opts) {
        opts = opts || {};
        var width = opts.width || 600;
        var height = opts.height || 300;
        var padding = { top: 20, right: 20, bottom: 40, left: 50 };

        container.textContent = "";
        if (!data.years || !data.years.length || !data.languages || !data.languages.length) {
            var empty = document.createElement("p");
            empty.className = "av-chart-empty";
            empty.textContent = "Not enough data yet";
            container.appendChild(empty);
            return;
        }

        var years = data.years;
        var langs = data.languages;
        var series = data.series;

        // Compute stacked totals per year
        var stacked = [];
        for (var yi = 0; yi < years.length; yi++) {
            var bottom = 0;
            var slices = [];
            for (var li = 0; li < langs.length; li++) {
                var val = series[langs[li]][yi] || 0;
                slices.push({ lang: langs[li], y0: bottom, y1: bottom + val });
                bottom += val;
            }
            stacked.push({ year: years[yi], slices: slices, total: bottom });
        }

        var maxTotal = 0;
        for (var si = 0; si < stacked.length; si++) {
            if (stacked[si].total > maxTotal) maxTotal = stacked[si].total;
        }
        if (maxTotal === 0) return;

        var wrap = document.createElement("div");
        wrap.className = "av-chart-stacked-area";

        var plotW = width - padding.left - padding.right;
        var plotH = height - padding.top - padding.bottom;
        var svg = createSvg(width, height);

        // X and Y scale helpers
        var xStep = years.length > 1 ? plotW / (years.length - 1) : plotW;
        function xPos(i) { return padding.left + i * xStep; }
        function yPos(v) { return padding.top + plotH - (v / maxTotal) * plotH; }

        // Grid lines
        var gridTicks = 4;
        for (var gi = 0; gi <= gridTicks; gi++) {
            var gy = padding.top + (gi / gridTicks) * plotH;
            var gl = svgEl("line", {
                x1: padding.left, y1: gy, x2: padding.left + plotW, y2: gy,
                stroke: "var(--av-border)", "stroke-width": "0.5", "stroke-dasharray": "4 4"
            });
            svg.appendChild(gl);
            var tickVal = Math.round(maxTotal * (1 - gi / gridTicks));
            var tickLabel = svgEl("text", {
                x: padding.left - 8, y: gy + 3,
                "text-anchor": "end", "font-size": "9", fill: "var(--av-text-tertiary)"
            });
            tickLabel.textContent = formatCount(tickVal);
            svg.appendChild(tickLabel);
        }

        // Draw stacked areas (back to front)
        for (var ai = langs.length - 1; ai >= 0; ai--) {
            var pts = [];
            for (var pi = 0; pi < stacked.length; pi++) {
                pts.push(xPos(pi) + "," + yPos(stacked[pi].slices[ai].y1));
            }
            for (var qi = stacked.length - 1; qi >= 0; qi--) {
                pts.push(xPos(qi) + "," + yPos(stacked[qi].slices[ai].y0));
            }
            var polygon = svgEl("polygon", {
                points: pts.join(" "),
                fill: PALETTE[ai % PALETTE.length],
                opacity: "0.75",
                "class": "av-chart-area-band",
                "data-chart-index": String(ai)
            });

            (function (poly, lang, idx, svgRef) {
                poly.addEventListener("mouseenter", function (e) {
                    var bands = svgRef.querySelectorAll(".av-chart-area-band");
                    for (var b = 0; b < bands.length; b++) {
                        bands[b].setAttribute("opacity", bands[b] === poly ? "0.9" : "0.25");
                    }
                    showTooltip('<strong>' + escText(lang) + '</strong>', e);
                });
                poly.addEventListener("mousemove", function (e) { throttledPositionTooltip(e); });
                poly.addEventListener("mouseleave", function () {
                    var bands = svgRef.querySelectorAll(".av-chart-area-band");
                    for (var b = 0; b < bands.length; b++) {
                        bands[b].setAttribute("opacity", "0.75");
                    }
                    hideTooltip();
                });
            })(polygon, langs[ai], ai, svg);

            svg.appendChild(polygon);
        }

        // X-axis labels
        var labelInterval = Math.max(1, Math.ceil(years.length / 12));
        for (var xi = 0; xi < years.length; xi += labelInterval) {
            var xTick = svgEl("text", {
                x: xPos(xi), y: height - padding.bottom + 16,
                "text-anchor": "middle", "font-size": "9", fill: "var(--av-text-tertiary)"
            });
            xTick.textContent = years[xi];
            svg.appendChild(xTick);
        }

        wrap.appendChild(svg);

        // Legend
        var legend = document.createElement("ul");
        legend.className = "av-chart-legend av-chart-legend--inline";
        for (var lk = 0; lk < langs.length; lk++) {
            var lgLi = document.createElement("li");
            lgLi.className = "av-chart-legend-item";
            lgLi.innerHTML =
                '<span class="av-chart-legend-dot" style="--dot-color:' + PALETTE[lk % PALETTE.length] + '"></span>' +
                '<span class="av-chart-legend-label">' + escText(langs[lk]) + '</span>';

            (function (legendLi, idx, svgRef) {
                legendLi.addEventListener("mouseenter", function () {
                    var bands = svgRef.querySelectorAll(".av-chart-area-band");
                    for (var b = 0; b < bands.length; b++) {
                        bands[b].setAttribute("opacity", bands[b].getAttribute("data-chart-index") === String(idx) ? "0.9" : "0.25");
                    }
                });
                legendLi.addEventListener("mouseleave", function () {
                    var bands = svgRef.querySelectorAll(".av-chart-area-band");
                    for (var b = 0; b < bands.length; b++) {
                        bands[b].setAttribute("opacity", "0.75");
                    }
                });
            })(lgLi, lk, svg);

            legend.appendChild(lgLi);
        }
        wrap.appendChild(legend);

        container.appendChild(wrap);
    }

    // ----------------------------------------------------------- Utilities

    function healthColorForScore(score) {
        if (score >= 80) return "var(--av-success)";
        if (score >= 60) return "var(--av-info)";
        if (score >= 40) return "var(--av-warning)";
        return "var(--av-danger)";
    }

    function formatCount(n) {
        if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
        if (n >= 1000) return (n / 1000).toFixed(1) + "k";
        return String(n);
    }

    function truncate(str, len) {
        if (!str) return "";
        return str.length > len ? str.substring(0, len - 1) + "\u2026" : str;
    }

    // ---------------------------------------------------------- Export

    window.AVCharts = {
        donut: donut,
        bar: bar,
        bubble: bubble,
        horizontalBar: horizontalBar,
        stackedArea: stackedArea
    };

})();
