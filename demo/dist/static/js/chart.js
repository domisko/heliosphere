// A small dependency-free time-series line chart: gridlines with "nice"
// rounded Y ticks, a few X-axis time labels, and a hover crosshair+tooltip.
// Values arrive right-aligned into a fixed-length rolling buffer, same as
// the sparkline this replaces, so new points push in from the right.
(function () {
    const SVG_NS = "http://www.w3.org/2000/svg";
    const VIEW_W = 320;
    const VIEW_H = 110;
    const PAD = { left: 42, right: 8, top: 8, bottom: 18 };
    const PLOT_W = VIEW_W - PAD.left - PAD.right;
    const PLOT_H = VIEW_H - PAD.top - PAD.bottom;

    // parseUtc: EnrichedTelemetry.timestamp is naive UTC (e.g.
    // "2026-09-14T13:22:00", no offset). `new Date(...)` on a string with no
    // timezone is parsed as LOCAL time per the ECMAScript spec, which silently
    // shifts every timestamp by the viewer's UTC offset. Appending "Z" forces
    // the correct UTC interpretation.
    function parseUtc(value) {
        if (value instanceof Date) return value;
        return new Date(value.endsWith("Z") ? value : `${value}Z`);
    }

    function el(tag, attrs) {
        const node = document.createElementNS(SVG_NS, tag);
        for (const [key, val] of Object.entries(attrs)) node.setAttribute(key, val);
        return node;
    }

    function niceNumber(range, round) {
        if (range === 0) return 1;
        const exponent = Math.floor(Math.log10(range));
        const fraction = range / 10 ** exponent;
        let niceFraction;
        if (round) {
            if (fraction < 1.5) niceFraction = 1;
            else if (fraction < 3) niceFraction = 2;
            else if (fraction < 7) niceFraction = 5;
            else niceFraction = 10;
        } else if (fraction <= 1) niceFraction = 1;
        else if (fraction <= 2) niceFraction = 2;
        else if (fraction <= 5) niceFraction = 5;
        else niceFraction = 10;
        return niceFraction * 10 ** exponent;
    }

    function niceTicks(min, max, tickCount) {
        if (min === max) {
            min -= 1;
            max += 1;
        }
        const range = niceNumber(max - min, false);
        const step = niceNumber(range / (tickCount - 1), true);
        const niceMin = Math.floor(min / step) * step;
        const niceMax = Math.ceil(max / step) * step;
        const ticks = [];
        for (let v = niceMin; v <= niceMax + step * 0.5; v += step) ticks.push(v);
        return { ticks, min: niceMin, max: niceMax };
    }

    function formatTick(value) {
        if (Math.abs(value) >= 1000) return (value / 1000).toFixed(value % 1000 === 0 ? 0 : 1) + "k";
        if (Number.isInteger(value)) return String(value);
        return value.toFixed(1);
    }

    function formatTime(date) {
        return date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" }) + "Z";
    }

    window.TimeSeriesChart = class {
        constructor(wrapEl, { color, unit = "", maxPoints = 120, digits = 1 } = {}) {
            this.wrap = wrapEl;
            this.svg = wrapEl.querySelector("svg");
            this.tooltip = wrapEl.querySelector(".chart-tooltip");
            this.color = color;
            this.unit = unit;
            this.maxPoints = maxPoints;
            this.digits = digits;
            this.points = []; // [{t: Date, v: number}]

            this.svg.setAttribute("viewBox", `0 0 ${VIEW_W} ${VIEW_H}`);
            this.svg.innerHTML = "";

            this.gridGroup = el("g", {});
            this.areaPath = el("path", { fill: color, "fill-opacity": "0.12", stroke: "none" });
            this.linePath = el("path", { fill: "none", stroke: color, "stroke-width": "2", "stroke-linejoin": "round", "stroke-linecap": "round" });
            this.xLabelGroup = el("g", {});
            this.emptyText = el("text", {
                x: VIEW_W / 2, y: VIEW_H / 2, "text-anchor": "middle",
                fill: "var(--text-dim)", "font-size": "11",
            });
            this.emptyText.textContent = "Collecting data…";

            this.crosshair = el("line", { stroke: "var(--slate)", "stroke-width": "1", visibility: "hidden" });
            this.hoverDot = el("circle", { r: "4", fill: color, stroke: "var(--panel)", "stroke-width": "2", visibility: "hidden" });
            this.hitArea = el("rect", {
                x: PAD.left, y: PAD.top, width: PLOT_W, height: PLOT_H,
                fill: "transparent",
            });

            this.svg.append(
                this.gridGroup, this.areaPath, this.linePath, this.xLabelGroup,
                this.emptyText, this.crosshair, this.hoverDot, this.hitArea,
            );

            const onMove = (evt) => this._onHover(evt);
            this.hitArea.addEventListener("pointermove", onMove);
            this.hitArea.addEventListener("pointerdown", onMove);
            this.hitArea.addEventListener("pointerleave", () => this._hideHover());
        }

        seed(records) {
            // records: [{t: string|Date, v: number}]
            this.points = records
                .filter((r) => typeof r.v === "number" && !Number.isNaN(r.v))
                .slice(-this.maxPoints)
                .map((r) => ({ t: parseUtc(r.t), v: r.v }));
            this._render();
        }

        push(t, v) {
            if (typeof v !== "number" || Number.isNaN(v)) return;
            this.points.push({ t: parseUtc(t), v });
            if (this.points.length > this.maxPoints) this.points.shift();
            this._render();
        }

        _xForRank(rank) {
            return PAD.left + (rank / (this.maxPoints - 1)) * PLOT_W;
        }

        _offset() {
            return this.maxPoints - this.points.length;
        }

        _render() {
            const hasData = this.points.length >= 2;
            this.emptyText.style.display = hasData ? "none" : "block";
            this.gridGroup.style.display = hasData ? "block" : "none";
            this.areaPath.style.display = hasData ? "block" : "none";
            this.linePath.style.display = hasData ? "block" : "none";
            this.xLabelGroup.style.display = hasData ? "block" : "none";
            if (!hasData) return;

            const values = this.points.map((p) => p.v);
            const { ticks, min, max } = niceTicks(Math.min(...values), Math.max(...values), 3);
            const yFor = (v) => PAD.top + PLOT_H - ((v - min) / (max - min)) * PLOT_H;

            this.gridGroup.innerHTML = "";
            for (const tick of ticks) {
                const y = yFor(tick);
                if (y < PAD.top - 0.5 || y > PAD.top + PLOT_H + 0.5) continue;
                this.gridGroup.append(
                    el("line", {
                        x1: PAD.left, x2: VIEW_W - PAD.right, y1: y, y2: y,
                        stroke: "var(--border)", "stroke-width": "1",
                    }),
                    el("text", {
                        x: PAD.left - 6, y: y + 3, "text-anchor": "end",
                        fill: "var(--text-dim)", "font-size": "9",
                    }),
                );
                this.gridGroup.lastChild.textContent = formatTick(tick);
            }

            const offset = this._offset();
            const coords = this.points.map((p, i) => [this._xForRank(offset + i), yFor(p.v)]);

            this.linePath.setAttribute("d", coords.map((c, i) => `${i === 0 ? "M" : "L"}${c[0].toFixed(1)},${c[1].toFixed(1)}`).join(" "));

            const baseline = PAD.top + PLOT_H;
            const areaD =
                `M${coords[0][0].toFixed(1)},${baseline}` +
                coords.map((c) => ` L${c[0].toFixed(1)},${c[1].toFixed(1)}`).join("") +
                ` L${coords[coords.length - 1][0].toFixed(1)},${baseline} Z`;
            this.areaPath.setAttribute("d", areaD);

            this.xLabelGroup.innerHTML = "";
            const labelRanks = [0, Math.floor((this.points.length - 1) / 2), this.points.length - 1];
            const anchors = ["start", "middle", "end"];
            labelRanks.forEach((rank, i) => {
                if (i > 0 && rank === labelRanks[i - 1]) return;
                const x = this._xForRank(offset + rank);
                const label = el("text", {
                    x, y: VIEW_H - 4, "text-anchor": anchors[i],
                    fill: "var(--text-dim)", "font-size": "9",
                });
                label.textContent = formatTime(this.points[rank].t);
                this.xLabelGroup.append(label);
            });

            this._yFor = yFor;
            this._coords = coords;
        }

        _onHover(evt) {
            if (this.points.length < 2) return;
            const rect = this.svg.getBoundingClientRect();
            const svgX = ((evt.clientX - rect.left) / rect.width) * VIEW_W;
            const offset = this._offset();
            let rank = Math.round(((svgX - PAD.left) / PLOT_W) * (this.maxPoints - 1) - offset);
            rank = Math.max(0, Math.min(this.points.length - 1, rank));

            const point = this.points[rank];
            const [x, y] = this._coords[rank];

            this.crosshair.setAttribute("x1", x);
            this.crosshair.setAttribute("x2", x);
            this.crosshair.setAttribute("y1", PAD.top);
            this.crosshair.setAttribute("y2", PAD.top + PLOT_H);
            this.crosshair.setAttribute("visibility", "visible");
            this.hoverDot.setAttribute("cx", x);
            this.hoverDot.setAttribute("cy", y);
            this.hoverDot.setAttribute("visibility", "visible");

            if (this.tooltip) {
                this.tooltip.innerHTML = "";
                const value = document.createElement("strong");
                value.style.color = this.color;
                value.textContent = `${point.v.toFixed(this.digits)}${this.unit ? " " + this.unit : ""}`;
                const time = document.createElement("span");
                time.textContent = formatTime(point.t);
                this.tooltip.append(value, time);
                this.tooltip.hidden = false;

                const wrapRect = this.wrap.getBoundingClientRect();
                const leftPx = (x / VIEW_W) * wrapRect.width;
                const topPx = (y / VIEW_H) * wrapRect.height;
                this.tooltip.style.left = `${Math.max(4, Math.min(wrapRect.width - 4, leftPx))}px`;
                this.tooltip.style.top = `${topPx}px`;
            }
        }

        _hideHover() {
            this.crosshair.setAttribute("visibility", "hidden");
            this.hoverDot.setAttribute("visibility", "hidden");
            if (this.tooltip) this.tooltip.hidden = true;
        }
    };

    window.parseUtcTimestamp = parseUtc;
})();
