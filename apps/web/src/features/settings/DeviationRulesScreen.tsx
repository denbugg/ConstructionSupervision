import { useState } from "react";

import { SEVERITY_ORDER, severityDot } from "@/entities/status";
import {
  scalarParams,
  useDeviationRules,
  useUpdateDeviationRule,
  type DeviationRule,
} from "@/features/settings/useSettings";
import { formatMoment } from "@/entities/format";
import { label, ru } from "@/shared/locale/ru";
import { Dot } from "@/shared/ui/Badge";
import { Button } from "@/shared/ui/Button";
import { Field, Toggle, fieldClass, inputClass, textareaClass } from "@/shared/ui/Field";
import { Icon } from "@/shared/ui/Icon";
import { PageContainer, PageHeader } from "@/shared/ui/Page";
import { ErrorBox, Loading } from "@/shared/ui/QueryState";
import { useToast } from "@/shared/ui/Toast";

/**
 * Пороги отклонений D1–D10 (methodology.md, раздел 9): включение, серьёзность, числа и
 * тексты. Логика — данные: правка здесь меняет выводы без правки кода.
 */
export function DeviationRulesScreen() {
  const rules = useDeviationRules();
  return (
    <PageContainer>
      <PageHeader
        title="Пороги отклонений"
        description="Когда система поднимает предупреждение: сколько сессий подряд, когда повышать серьёзность, какими словами писать. Настройки общие для всех объектов."
      />
      <div className="mb-5 flex gap-3 rounded-2xl bg-sky-50 p-4 text-sm text-sky-900 ring-1 ring-sky-200">
        <Icon name="info" size={18} className="mt-0.5 shrink-0" />
        <p>
          Правка действует со следующего прогона анализа. Чтобы увидеть её сразу, откройте объект и
          нажмите «Пересчитать» — лента предупреждений перестроится по новым порогам.
        </p>
      </div>
      {rules.isPending && <Loading />}
      {rules.isError && <ErrorBox error={rules.error} onRetry={() => rules.refetch()} />}
      <div className="space-y-3">
        {rules.data?.items.map((rule) => (
          <RuleCard key={`${rule.code}-${rule.updated_at}`} rule={rule} />
        ))}
      </div>
    </PageContainer>
  );
}

type Draft = {
  enabled: boolean;
  severity: string;
  params: Record<string, string>;
  title: string;
  message: string;
};

function draftOf(rule: DeviationRule): Draft {
  return {
    enabled: rule.enabled,
    severity: rule.severity,
    params: Object.fromEntries(scalarParams(rule.params as Record<string, unknown>).map(([k, v]) => [k, String(v)])),
    title: rule.title_template,
    message: rule.message_template,
  };
}

function RuleCard({ rule }: { rule: DeviationRule }) {
  const initial = draftOf(rule);
  const [draft, setDraft] = useState<Draft>(initial);
  const [texts, setTexts] = useState(false);
  const update = useUpdateDeviationRule(rule.code);
  const toast = useToast();
  const original = Object.fromEntries(scalarParams(rule.params as Record<string, unknown>));
  const changed = JSON.stringify(draft) !== JSON.stringify(initial);

  const save = () => {
    // Параметры сливаются по ключам: отправляем только изменённые, с исходным типом значения.
    const params: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(draft.params)) {
      if (value === initial.params[key]) continue;
      params[key] = typeof original[key] === "number" ? Number(value.replace(",", ".")) : value;
    }
    update.mutate(
      {
        enabled: draft.enabled,
        severity: draft.severity,
        params: Object.keys(params).length > 0 ? (params as DeviationRule["params"]) : null,
        title_template: draft.title !== initial.title ? draft.title : null,
        message_template: draft.message !== initial.message ? draft.message : null,
      },
      {
        onSuccess: () => toast.success(`${rule.code} сохранено`, "Действует со следующего прогона анализа"),
        onError: (error) => toast.error(error, `${rule.code} не сохранено`),
      },
    );
  };

  const invalid = Object.entries(draft.params).some(
    ([key, value]) => typeof original[key] === "number" && Number.isNaN(Number(value.replace(",", "."))),
  );

  return (
    <article className={`rounded-2xl bg-white shadow-sm ring-1 ring-ink/[0.07] ${draft.enabled ? "" : "opacity-75"}`}>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3 px-5 py-4">
        <div className="flex min-w-60 flex-1 items-center gap-3">
          <span className="flex h-9 w-12 shrink-0 items-center justify-center rounded-lg bg-ink font-mono text-sm font-semibold text-white">
            {rule.code}
          </span>
          <div className="min-w-0">
            <p className="font-medium">{label(ru.deviationCode, rule.code)}</p>
            <p className="text-xs text-muted">
              предикат <code>{rule.predicate}</code> · изменено {formatMoment(rule.updated_at)}
            </p>
          </div>
        </div>
        <Toggle checked={draft.enabled} onChange={(enabled) => setDraft({ ...draft, enabled })} label={draft.enabled ? "включено" : "выключено"} />
        <label className="flex items-center gap-2 text-sm">
          <Dot className={severityDot(draft.severity)} />
          <select value={draft.severity} onChange={(e) => setDraft({ ...draft, severity: e.target.value })} className={fieldClass("select", "sm", "w-auto")}>
            {SEVERITY_ORDER.map((s) => (
              <option key={s} value={s}>
                {label(ru.severity, s)}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex flex-wrap items-end gap-4 border-t border-ink/[0.06] px-5 py-4">
        {Object.keys(draft.params).length === 0 && <p className="text-sm text-muted">Числовых порогов нет — условие задано самим правилом.</p>}
        {Object.entries(draft.params).map(([key, value]) => (
          <Field key={key} label={label(ru.ruleParam, key)} className="w-44">
            {key === "escalate_to" ? (
              <select
                value={value}
                onChange={(e) => setDraft({ ...draft, params: { ...draft.params, [key]: e.target.value } })}
                className={fieldClass("select", "sm")}
              >
                {SEVERITY_ORDER.map((s) => (
                  <option key={s} value={s}>
                    {label(ru.severity, s)}
                  </option>
                ))}
              </select>
            ) : (
              <input
                value={value}
                inputMode="decimal"
                onChange={(e) => setDraft({ ...draft, params: { ...draft.params, [key]: e.target.value } })}
                className={`${fieldClass("input", "sm")} tabular-nums`}
              />
            )}
          </Field>
        ))}
        <div className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="ghost" icon={texts ? "chevronDown" : "chevronRight"} onClick={() => setTexts((v) => !v)}>
            Тексты
          </Button>
          {changed && (
            <Button size="sm" variant="ghost" onClick={() => setDraft(initial)} disabled={update.isPending}>
              Отменить
            </Button>
          )}
          <Button size="sm" variant="primary" icon="check" disabled={!changed || invalid} loading={update.isPending} onClick={save}>
            Сохранить
          </Button>
        </div>
      </div>

      {texts && (
        <div className="grid gap-4 border-t border-ink/[0.06] px-5 py-4 lg:grid-cols-2">
          <Field label="Заголовок" hint="Подстановки в фигурных скобках: {stage_name}, {equipment_name}, {area_name}">
            <input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} className={inputClass} />
          </Field>
          <Field label="Текст" hint="Числа в текст подставляются из фактов отклонения — сами они не пишутся">
            <textarea rows={3} value={draft.message} onChange={(e) => setDraft({ ...draft, message: e.target.value })} className={textareaClass} />
          </Field>
        </div>
      )}
    </article>
  );
}
