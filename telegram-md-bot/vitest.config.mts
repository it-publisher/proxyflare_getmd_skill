import { cloudflareTest } from "@cloudflare/vitest-pool-workers";
import { defineConfig } from "vitest/config";

export default defineConfig({
	plugins: [cloudflareTest({
		wrangler: { configPath: "./wrangler.jsonc" },
	})],
	test: {
		deps: {
			optimizer: {
				ssr: {
					enabled: true,
					// css-what, pulled in through node-html-parser, has extensionless ESM imports
					// that the Workers module loader can't resolve unless Vite bundles them first
					include: ["node-html-markdown", "linkedom", "@mozilla/readability"],
				},
			},
		},
	},
});
