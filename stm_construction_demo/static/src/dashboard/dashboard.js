/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class ConstructionDashboard extends Component {
    static template = "stm_construction_demo.ConstructionDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = useState({
            loading: true,
            data: null,
            selectedProjectId: 0,
            aiOpen: true,
            aiLoading: false,
            aiScenario: "cost_overrun",
            aiQuery: "",
            aiResult: null,
        });

        onWillStart(async () => {
            await this.loadDashboard();
            await this.runAiScenario("cost_overrun", false);
        });
    }

    async loadDashboard() {
        this.state.loading = true;
        try {
            const projectId = this.state.selectedProjectId || false;
            this.state.data = await this.orm.call(
                "construction.dashboard.service",
                "get_dashboard_data",
                [],
                { project_id: projectId }
            );
        } finally {
            this.state.loading = false;
        }
    }

    async onProjectFilterChange(ev) {
        this.state.selectedProjectId = parseInt(ev.target.value || "0", 10) || 0;
        await this.loadDashboard();
        await this.runAiScenario(this.state.aiScenario || "cost_overrun", false);
    }

    async onRefresh() {
        await this.loadDashboard();
        if (this.state.aiResult) {
            await this.runAiScenario(this.state.aiScenario || "cost_overrun", false);
        }
    }

    toggleAiPanel() {
        this.state.aiOpen = !this.state.aiOpen;
    }

    async runAiScenario(scenarioKey, withDelay = true) {
        this.state.aiOpen = true;
        this.state.aiScenario = scenarioKey;
        this.state.aiLoading = true;
        try {
            if (withDelay) {
                await new Promise((resolve) => setTimeout(resolve, 280));
            }
            const projectId = this.state.selectedProjectId || false;
            this.state.aiResult = await this.orm.call(
                "construction.dashboard.service",
                "ask_ai_assistant",
                [],
                {
                    scenario_key: scenarioKey,
                    query_text: "",
                    project_id: projectId,
                }
            );
        } finally {
            this.state.aiLoading = false;
        }
    }

    async onSubmitAiQuery() {
        const query = (this.state.aiQuery || "").trim();
        if (!query) {
            return;
        }
        this.state.aiOpen = true;
        this.state.aiScenario = null;
        this.state.aiLoading = true;
        try {
            await new Promise((resolve) => setTimeout(resolve, 320));
            const projectId = this.state.selectedProjectId || false;
            this.state.aiResult = await this.orm.call(
                "construction.dashboard.service",
                "ask_ai_assistant",
                [],
                {
                    scenario_key: null,
                    query_text: query,
                    project_id: projectId,
                }
            );
        } finally {
            this.state.aiLoading = false;
        }
    }

    onAiKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.onSubmitAiQuery();
        }
    }

    onAlertClick(alert) {
        if (alert.scenario_key) {
            this.runAiScenario(alert.scenario_key, true);
        } else if (alert.res_model && alert.res_id) {
            this.openRecord(alert.res_model, alert.res_id);
        }
    }

    openAction(xmlId) {
        this.action.doAction(xmlId);
    }

    openModelList(resModel, title, domain = []) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: title,
            res_model: resModel,
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: domain,
        });
    }

    openRecord(resModel, resId) {
        if (!resModel || !resId) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: resModel,
            res_id: resId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    fmtNum(val) {
        const num = Number(val || 0);
        return num.toLocaleString("en-US", { maximumFractionDigits: 0 });
    }

    fmtDec(val) {
        const num = Number(val || 0);
        return num.toLocaleString("en-US", { maximumFractionDigits: 1 });
    }

    get chartMaxVal() {
        const series = this.state.data?.costs?.project_chart_series || [];
        let maxV = 1;
        for (const item of series) {
            maxV = Math.max(maxV, item.planned || 0, item.actual || 0, item.eac || 0);
        }
        return maxV;
    }

    barPct(val) {
        return Math.min(100, Math.round(((val || 0) / this.chartMaxVal) * 100));
    }

    get unitDonutSegments() {
        const avail = this.state.data?.real_estate?.availability;
        const total = avail?.total_units || 0;
        const circumference = 2 * Math.PI * 52; // r=52 -> ~326.73
        if (!total) {
            return {
                total: 0,
                circumference,
                availLen: 0,
                reservedLen: 0,
                soldLen: 0,
                reservedOffset: 0,
                soldOffset: 0,
            };
        }
        const availLen = (avail.available / total) * circumference;
        const reservedLen = (avail.reserved / total) * circumference;
        const soldLen = (avail.sold / total) * circumference;
        return {
            total,
            circumference,
            availLen,
            reservedLen,
            soldLen,
            reservedOffset: -availLen,
            soldOffset: -(availLen + reservedLen),
        };
    }

    get materialsConsumedPct() {
        const m = this.state.data?.costs?.materials;
        if (!m || !m.planned) {
            return 0;
        }
        return Math.min(100, Math.round((m.consumed / m.planned) * 100));
    }
}

registry.category("actions").add("stm_construction_dashboard", ConstructionDashboard);
