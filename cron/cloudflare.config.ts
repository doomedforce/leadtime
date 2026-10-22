import { defineConfig, triggers } from "cf/config";
import * as entrypoint from "./src/index.js" with { type: "cf-worker" };

export default defineConfig({
	worker: {
		name: "trailermath-cron",
		entrypoint,
		compatibilityDate: "2026-10-01",
		// Keep in sync with WORKFLOWS in src/index.js.
		triggers: [triggers.scheduled({ schedule: "11 * * * *" }), triggers.scheduled({ schedule: "0 15 * * 1" })],
		// Needs a GITHUB_TOKEN secret, added in the dashboard: a fine-grained token for
		// doomedforce/trailermath with "Actions: Read and write". (This cf version can't declare secrets here.)
	},
});
