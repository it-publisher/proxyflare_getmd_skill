import { cloudflareTest } from "@cloudflare/vitest-pool-workers";
import { defineConfig } from "vitest/config";

export default defineConfig({
	plugins: [cloudflareTest({
		wrangler: { configPath: "./wrangler.jsonc" },
	})],
	resolve: {
		alias: {
			// css-what exports a .d.ts file as a module — stub it out
			"css-what/lib/es/types": "/dev/null",
		},
	},
});
