// Starts the Trailer Math build every hour. GitHub's own schedule skips most hours on this repo,
// and a trailer's 24-hour view figure needs a snapshot on each side of its 24-hour mark.
const DISPATCH = "https://api.github.com/repos/doomedforce/trailermath/actions/workflows/build.yml/dispatches";

export default {
	async scheduled(controller, env) {
		const res = await fetch(DISPATCH, {
			method: "POST",
			headers: {
				Authorization: `Bearer ${env.GITHUB_TOKEN}`,
				Accept: "application/vnd.github+json",
				"X-GitHub-Api-Version": "2022-11-28",
				"User-Agent": "trailermath-cron",
			},
			body: JSON.stringify({ ref: "main" }),
		});
		// Throwing marks the run as failed in the Worker's logs, so a revoked token is visible.
		if (!res.ok) throw new Error(`GitHub dispatch failed: ${res.status} ${await res.text()}`);
	},
};
