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
        // Force layout so we can read dimensions
        var w = tip.offsetWidth;
        var h = tip.offsetHeight;
        if (x + w > window.innerWidth - pad) x = e.clientX - w - pad;
        if (y + h > window.innerHeight - pad) y = e.clientY - h - pad;
        if (x < pad) x = pad;
        if (y < pad) y = pad;
        tip.style.left = x + "px";
        tip.style.top = y + "px";
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
                    arcPath.addEventListener("mousemove", function (e) { positionTooltip(e); });
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
                barRow.addEventListener("mouseenter", function (e) {
                    barRow.classList.add("is-active");
                    showTooltip('<strong>' + escText(barData.label) + '</strong><br>' + formatCount(barData.count) + ' repos', e);
                });
                barRow.addEventListener("mousemove", function (e) { positionTooltip(e); });
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

    function bubble(container, data, opts) {
        opts = opts || {};
        var width = opts.width || 600;
        var height = opts.height || 400;
        var maxBubbles = opts.max || 50;

        container.textContent = "";

        var items = data.slice(0, maxBubbles);
        if (!items.length) return;

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

        // Axes labels
        var xLabel = svgEl("text", {
            x: width / 2,
            y: height - 8,
            "text-anchor": "middle",
            "font-size": "11",
            fill: "var(--av-text-tertiary)"
        });
        xLabel.textContent = "Avg Stars";
        svg.appendChild(xLabel);

        var yLabel = svgEl("text", {
            x: 12,
            y: height / 2,
            "text-anchor": "middle",
            "font-size": "11",
            fill: "var(--av-text-tertiary)",
            transform: "rotate(-90 12 " + (height / 2) + ")"
        });
        yLabel.textContent = "Avg Health";
        svg.appendChild(yLabel);

        // Plot bubbles
        var minR = 6;
        var maxR = 30;

        for (var j = 0; j < items.length; j++) {
            var b = items[j];
            var x = padding + (maxStars > 0 ? (b.stars / maxStars) * plotW : plotW / 2);
            var y = padding + plotH - (maxHealth > 0 ? (b.health / maxHealth) * plotH : plotH / 2);
            var r = minR + (maxCount > 0 ? (b.count / maxCount) * (maxR - minR) : minR);
            var color = healthColorForScore(b.health);

            var g = svgEl("g", { "class": "av-chart-bubble-node" });

            var circle = svgEl("circle", {
                cx: x,
                cy: y,
                r: r,
                fill: color,
                opacity: "0.7",
                stroke: color,
                "stroke-width": "1.5",
                filter: "url(#av-bubble-shadow)"
            });

            g.appendChild(circle);

            // Interactive tooltip and hover
            (function (bubbleG, bubbleCircle, bubbleData) {
                bubbleG.addEventListener("mouseenter", function (e) {
                    bubbleCircle.setAttribute("opacity", "1");
                    bubbleCircle.setAttribute("stroke-width", "3");
                    showTooltip(
                        '<strong>' + escText(bubbleData.name) + '</strong><br>' +
                        bubbleData.count + ' repos<br>' +
                        'Health: ' + bubbleData.health + '<br>' +
                        'Avg stars: ' + formatCount(bubbleData.stars), e
                    );
                });
                bubbleG.addEventListener("mousemove", function (e) { positionTooltip(e); });
                bubbleG.addEventListener("mouseleave", function () {
                    bubbleCircle.setAttribute("opacity", "0.7");
                    bubbleCircle.setAttribute("stroke-width", "1.5");
                    hideTooltip();
                });
                if (opts.onClick) {
                    bubbleG.style.cursor = "pointer";
                    bubbleG.addEventListener("click", function () { opts.onClick(bubbleData); });
                }
            })(g, circle, b);

            // Label for all bubbles -- font size proportional to radius
            var fontSize = Math.max(7, Math.min(r * 0.6, 14));
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

            svg.appendChild(g);
        }

        wrap.appendChild(svg);
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
            var val = d.health || d.count || 0;
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
                barRow.addEventListener("mousemove", function (e) { positionTooltip(e); });
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
        horizontalBar: horizontalBar
    };

})();
