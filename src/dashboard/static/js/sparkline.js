// Minimal auto-scaling SVG sparkline with a fixed-length rolling buffer.
(function () {
    const SVG_NS = "http://www.w3.org/2000/svg";

    window.Sparkline = class {
        constructor(svg, { maxPoints = 60, color = "#22d3ee" } = {}) {
            this.svg = svg;
            this.maxPoints = maxPoints;
            this.values = [];
            this.width = 300;
            this.height = 80;
            svg.setAttribute("viewBox", `0 0 ${this.width} ${this.height}`);
            this.path = document.createElementNS(SVG_NS, "polyline");
            this.path.setAttribute("fill", "none");
            this.path.setAttribute("stroke", color);
            this.path.setAttribute("stroke-width", "2");
            this.path.setAttribute("stroke-linejoin", "round");
            svg.innerHTML = "";
            svg.appendChild(this.path);
        }

        push(value) {
            if (value === null || value === undefined || Number.isNaN(value)) return;
            this.values.push(value);
            if (this.values.length > this.maxPoints) this.values.shift();
            this._render();
        }

        seed(values) {
            this.values = values.slice(-this.maxPoints);
            this._render();
        }

        _render() {
            if (this.values.length < 2) return;
            const min = Math.min(...this.values);
            const max = Math.max(...this.values);
            const range = max - min || 1;
            const step = this.width / (this.maxPoints - 1);
            const offset = this.maxPoints - this.values.length;
            const points = this.values
                .map((v, i) => {
                    const x = (offset + i) * step;
                    const y = this.height - ((v - min) / range) * (this.height - 8) - 4;
                    return `${x.toFixed(1)},${y.toFixed(1)}`;
                })
                .join(" ");
            this.path.setAttribute("points", points);
        }
    };
})();
