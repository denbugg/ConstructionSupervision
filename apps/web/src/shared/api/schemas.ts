/**
 * Короткие имена для схем API. Сами типы генерируются из снапшотов OpenAPI
 * (`scripts/contracts.py` → `packages/ts-api-client`) и руками не пишутся:
 * разошёлся контракт — сборка падает здесь, а не на демо.
 */
import type { analysis, plan, site } from "@api";

export type PlanSchema<K extends keyof plan.components["schemas"]> = plan.components["schemas"][K];

export type SiteSchema<K extends keyof site.components["schemas"]> = site.components["schemas"][K];

export type AnalysisSchema<K extends keyof analysis.components["schemas"]> =
  analysis.components["schemas"][K];
