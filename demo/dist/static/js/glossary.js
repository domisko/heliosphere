// Builds the readout list with tap/click-to-expand explanations.
// A native `title` attribute covers desktop hover, but touch devices have no
// hover state, so each label is also a button that toggles an inline
// description — that's what makes the glossary usable on mobile.
(function () {
    const FIELDS = [
        {
            id: "speed",
            label: "Solar Wind Speed",
            unit: "km/s",
            info: "Bulk velocity of the solar wind plasma measured at L1. Faster wind compresses Earth's magnetosphere and delivers more kinetic energy on arrival.",
        },
        {
            id: "density",
            label: "Proton Density",
            unit: "p/cm³",
            info: "Protons per cubic centimeter in the solar wind. Combined with speed, it sets the dynamic pressure pushing on Earth's magnetosphere.",
        },
        {
            id: "temp",
            label: "Ion Temperature",
            unit: "K",
            info: "Thermal temperature of the solar wind protons. Unusually high temperature alongside high speed and density can indicate a passing CME shock front.",
        },
        {
            id: "bx",
            label: "Bx (GSM)",
            unit: "nT",
            info: "IMF component along the Earth-Sun line, in GSM coordinates. Mostly a bookkeeping axis — unlike Bz, it doesn't directly drive reconnection.",
        },
        {
            id: "by",
            label: "By (GSM)",
            unit: "nT",
            info: "IMF component roughly along the dawn-dusk direction, in GSM coordinates. Combines with Bz to set the clock angle θ.",
        },
        {
            id: "bz",
            label: "Bz (GSM)",
            unit: "nT",
            info: "IMF component aligned with Earth's magnetic dipole. Negative (southward) Bz is the single strongest driver of geomagnetic storms — see \"Clock Angle & Southward Bz\" below.",
        },
        {
            id: "bt",
            label: "|B| Total",
            unit: "nT",
            info: "Total magnetic field magnitude, √(Bx²+By²+Bz²). A larger Bt means more field strength is available to turn southward.",
        },
        {
            id: "theta",
            label: "Clock Angle θ",
            unit: "°",
            info: "Angle of the field in the By-Bz plane: 0° = due north, 180° = due south. Southward-leaning angles favor magnetopause reconnection.",
        },
        {
            id: "coupling",
            label: "Newell Coupling",
            unit: "",
            info: "Empirical index (Newell et al. 2007) combining speed, transverse field, and clock angle into a single \"how hard is the solar wind driving the magnetosphere right now\" number. Relative, not a physical unit.",
        },
        {
            id: "dbzdt",
            label: "dBz/dt (15m)",
            unit: "nT/min",
            info: "Rate of change of Bz over the last 15 minutes. A sharp negative value can signal a storm's main phase is about to begin, ahead of what the raw Bz value alone suggests.",
        },
    ];

    const container = document.getElementById("readouts");
    if (!container) return;

    for (const field of FIELDS) {
        const row = document.createElement("div");
        row.className = "readout-row";

        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "info-btn";
        btn.setAttribute("aria-expanded", "false");
        btn.title = field.info;
        btn.innerHTML = `${field.label} <span class="info-icon">?</span>`;

        const value = document.createElement("span");
        value.className = "value";
        value.id = `r-${field.id}`;
        value.textContent = field.unit ? `-- ${field.unit}` : "--";

        row.append(btn, value);

        const info = document.createElement("p");
        info.className = "info-text";
        info.hidden = true;
        info.textContent = field.info;

        btn.addEventListener("click", () => {
            const expanded = btn.getAttribute("aria-expanded") === "true";
            btn.setAttribute("aria-expanded", String(!expanded));
            info.hidden = expanded;
        });

        container.append(row, info);
    }
})();
