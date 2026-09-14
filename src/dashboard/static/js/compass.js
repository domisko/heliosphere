// 2D IMF vector dial in the Y-Z GSM plane (where clock angle is physically defined).
// +Bz (north, closed magnetosphere) points up; +By points right.
// Bx (out-of-plane, toward/away from the Sun) is encoded as the center dot's fill.
(function () {
    const SVG_NS = "http://www.w3.org/2000/svg";
    const CENTER = 120;
    const RADIUS = 90;
    const MAX_NT = 20; // nT mapped to full radius; larger vectors are clamped visually

    function el(tag, attrs) {
        const node = document.createElementNS(SVG_NS, tag);
        for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
        return node;
    }

    function buildStaticChrome(svg) {
        svg.appendChild(el("circle", { cx: CENTER, cy: CENTER, r: RADIUS, fill: "none", stroke: "#1f2937", "stroke-width": 1 }));
        svg.appendChild(el("circle", { cx: CENTER, cy: CENTER, r: RADIUS * 0.5, fill: "none", stroke: "#1f2937", "stroke-width": 1 }));
        svg.appendChild(el("line", { x1: CENTER - RADIUS, y1: CENTER, x2: CENTER + RADIUS, y2: CENTER, stroke: "#1f2937" }));
        svg.appendChild(el("line", { x1: CENTER, y1: CENTER - RADIUS, x2: CENTER, y2: CENTER + RADIUS, stroke: "#1f2937" }));
        svg.appendChild(el("text", { x: CENTER, y: 14, fill: "#64748b", "font-size": 10, "text-anchor": "middle" })).textContent = "N (+Bz)";
        svg.appendChild(el("text", { x: CENTER, y: 234, fill: "#64748b", "font-size": 10, "text-anchor": "middle" })).textContent = "S (-Bz)";
        svg.appendChild(el("text", { x: 234, y: CENTER + 4, fill: "#64748b", "font-size": 10, "text-anchor": "end" })).textContent = "+By";
        svg.appendChild(el("text", { x: 6, y: CENTER + 4, fill: "#64748b", "font-size": 10, "text-anchor": "start" })).textContent = "-By";

        const vector = el("line", { x1: CENTER, y1: CENTER, x2: CENTER, y2: CENTER, stroke: "#22d3ee", "stroke-width": 2.5, "stroke-linecap": "round" });
        const head = el("circle", { cx: CENTER, cy: CENTER, r: 4, fill: "#22d3ee" });
        const core = el("circle", { cx: CENTER, cy: CENTER, r: 6, fill: "#94a3b8" });
        svg.appendChild(vector);
        svg.appendChild(head);
        svg.appendChild(core);
        return { vector, head, core };
    }

    window.Compass = {
        init(svg) {
            svg.innerHTML = "";
            svg.parts = buildStaticChrome(svg);
            return svg;
        },
        update(svg, bx, by, bz) {
            const { vector, head, core } = svg.parts;
            const magnitude = Math.min(Math.sqrt(by * by + bz * bz), MAX_NT * 1.5);
            const scale = (Math.min(magnitude, MAX_NT) / MAX_NT) * RADIUS;
            const angle = Math.atan2(by, bz); // 0 = north, matches clock angle convention
            const x = CENTER + scale * Math.sin(angle);
            const y = CENTER - scale * Math.cos(angle);

            vector.setAttribute("x2", x);
            vector.setAttribute("y2", y);
            head.setAttribute("cx", x);
            head.setAttribute("cy", y);

            const southward = bz < 0;
            vector.setAttribute("stroke", southward ? "#ef4444" : "#22d3ee");
            head.setAttribute("fill", southward ? "#ef4444" : "#22d3ee");

            const bxScale = Math.max(4, Math.min(14, 6 + Math.abs(bx)));
            core.setAttribute("r", bxScale);
            core.setAttribute("fill", bx >= 0 ? "#34d399" : "#f59e0b");
        },
    };
})();
