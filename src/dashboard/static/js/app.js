(function () {
    const compassEl = document.getElementById("compass");
    Compass.init(compassEl);

    const speedChart = new TimeSeriesChart(document.getElementById("spark-speed").closest(".chart-wrap"), {
        color: "var(--cyan)", unit: "km/s", maxPoints: 120, digits: 0,
    });
    const densityChart = new TimeSeriesChart(document.getElementById("spark-density").closest(".chart-wrap"), {
        color: "var(--green)", unit: "p/cm³", maxPoints: 120, digits: 2,
    });

    const dot = document.getElementById("conn-dot");
    const label = document.getElementById("conn-label");
    const banner = document.getElementById("storm-banner");

    const kpInfoBtn = document.getElementById("kp-info-btn");
    const kpInfoText = document.getElementById("kp-info-text");
    kpInfoBtn.addEventListener("click", () => {
        const expanded = kpInfoBtn.getAttribute("aria-expanded") === "true";
        kpInfoBtn.setAttribute("aria-expanded", String(!expanded));
        kpInfoText.hidden = expanded;
    });

    function setConnected(connected) {
        dot.classList.toggle("live", connected);
        label.textContent = connected ? "Live" : "Reconnecting";
    }

    function fmt(value, digits = 1) {
        return typeof value === "number" ? value.toFixed(digits) : "--";
    }

    function applyRecord(record) {
        document.getElementById("r-speed").textContent = `${fmt(record.speed, 0)} km/s`;
        document.getElementById("r-density").textContent = `${fmt(record.density, 2)} p/cm³`;
        document.getElementById("r-temp").textContent = `${fmt(record.temperature, 0)} K`;
        document.getElementById("r-bx").textContent = `${fmt(record.bx, 2)} nT`;
        document.getElementById("r-by").textContent = `${fmt(record.by, 2)} nT`;

        const bzEl = document.getElementById("r-bz");
        bzEl.textContent = `${fmt(record.bz, 2)} nT`;
        bzEl.classList.toggle("negative", record.bz < 0);

        document.getElementById("r-bt").textContent = `${fmt(record.bt, 2)} nT`;
        document.getElementById("r-theta").textContent = `${fmt(record.clock_angle, 1)} °`;
        document.getElementById("r-coupling").textContent = fmt(record.coupling_index, 0);

        const dbzdtEl = document.getElementById("r-dbzdt");
        dbzdtEl.textContent = `${fmt(record.bz_derivative_15m, 2)} nT/min`;
        dbzdtEl.classList.toggle("negative", record.bz_derivative_15m < 0);

        document.getElementById("spark-speed-value").innerHTML = `${fmt(record.speed, 0)}<span class="sparkline-unit">km/s</span>`;
        document.getElementById("spark-density-value").innerHTML = `${fmt(record.density, 2)}<span class="sparkline-unit">p/cm³</span>`;

        document.getElementById("storm-tier").textContent = record.storm_tier;
        const tierClass = record.storm_tier.split(" ")[0].toLowerCase();
        banner.className = tierClass;

        const officialTierEl = document.getElementById("official-tier");
        const kpDetailEl = document.getElementById("kp-detail");
        if (typeof record.official_kp === "number") {
            officialTierEl.textContent = record.official_g_scale;
            kpDetailEl.textContent = `Kp ${fmt(record.official_kp, 2)} (updated ~3-hourly)`;
        } else {
            officialTierEl.textContent = "--";
            kpDetailEl.textContent = "Awaiting NOAA Kp data";
        }

        const ts = parseUtcTimestamp(record.timestamp);
        document.getElementById("last-update").textContent = ts.toISOString().substring(11, 19) + "Z";

        Compass.update(compassEl, record.bx, record.by, record.bz);
        speedChart.push(record.timestamp, record.speed);
        densityChart.push(record.timestamp, record.density);
    }

    async function seedFromHistory() {
        try {
            const response = await fetch("/api/v1/telemetry/history?hours=2");
            const data = await response.json();
            if (data.records && data.records.length) {
                speedChart.seed(data.records.map((r) => ({ t: r.timestamp, v: r.speed })));
                densityChart.seed(data.records.map((r) => ({ t: r.timestamp, v: r.density })));
                applyRecord(data.records[data.records.length - 1]);
            }
        } catch (err) {
            console.warn("Could not seed history", err);
        }
    }

    let backoff = 1000;
    const MAX_BACKOFF = 30000;

    function connect() {
        const proto = window.location.protocol === "https:" ? "wss" : "ws";
        const ws = new WebSocket(`${proto}://${window.location.host}/ws/live`);

        ws.onopen = () => {
            setConnected(true);
            backoff = 1000;
        };

        ws.onmessage = (event) => {
            const payload = JSON.parse(event.data);
            if (payload.type === "backlog") {
                if (payload.records && payload.records.length) {
                    speedChart.seed(payload.records.map((r) => ({ t: r.timestamp, v: r.speed })));
                    densityChart.seed(payload.records.map((r) => ({ t: r.timestamp, v: r.density })));
                    applyRecord(payload.records[payload.records.length - 1]);
                }
                return;
            }
            applyRecord(payload);
        };

        ws.onclose = () => {
            setConnected(false);
            setTimeout(connect, backoff);
            backoff = Math.min(backoff * 2, MAX_BACKOFF);
        };

        ws.onerror = () => ws.close();
    }

    seedFromHistory();
    connect();
})();
