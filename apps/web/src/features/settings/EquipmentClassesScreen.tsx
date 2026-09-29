import { useState } from "react";

import { useEquipmentClasses } from "@/features/settings/useSettings";
import { label, ru } from "@/shared/locale/ru";
import { Badge } from "@/shared/ui/Badge";
import { inputClass } from "@/shared/ui/Field";
import { Icon } from "@/shared/ui/Icon";
import { PageContainer, PageHeader, Panel } from "@/shared/ui/Page";
import { ErrorBox, Loading } from "@/shared/ui/QueryState";

/**
 * Классы техники — только просмотр: класс добавляется записью в
 * `packages/contracts/equipment_classes.yaml` без правки кода (CONTRIBUTING.md, §12).
 */
export function EquipmentClassesScreen() {
  const classes = useEquipmentClasses();
  const [query, setQuery] = useState("");
  const needle = query.trim().toLowerCase();
  const items = (classes.data?.items ?? []).filter(
    (c) => !needle || `${c.code} ${c.name_ru} ${c.aliases.join(" ")}`.toLowerCase().includes(needle),
  );

  return (
    <PageContainer>
      <PageHeader
        title="Классы техники"
        description="Что умеет распознавать система и как считает присутствие. Новый класс — запись в equipment_classes.yaml и перезапуск plan- и vision-service, без правки кода."
      />
      {classes.isPending && <Loading />}
      {classes.isError && <ErrorBox error={classes.error} onRetry={() => classes.refetch()} />}
      {classes.data && (
        <Panel bodyClassName="">
          <div className="border-b border-ink/[0.07] px-5 py-3">
            <div className="relative max-w-xs">
              <Icon name="search" size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Поиск по названию или коду" className={`${inputClass} pl-9`} />
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-muted">
                <tr className="border-b border-ink/[0.07]">
                  <th className="px-5 py-2.5 font-medium">Класс</th>
                  <th className="px-3 py-2.5 font-medium">Группа</th>
                  <th className="px-3 py-2.5 font-medium">Как считается</th>
                  <th className="px-3 py-2.5 font-medium">Запросы детектору</th>
                  <th className="px-5 py-2.5 font-medium">Метки в датасетах</th>
                </tr>
              </thead>
              <tbody>
                {items.map((c) => (
                  <tr key={c.code} className="border-b border-ink/[0.06] align-top last:border-0">
                    <td className="px-5 py-3">
                      <p className="font-medium">{c.name_ru}</p>
                      <code className="text-xs text-muted">{c.code}</code>
                    </td>
                    <td className="px-3 py-3">{label(ru.equipmentGroup, c.group)}</td>
                    <td className="px-3 py-3">
                      <div className="flex flex-wrap gap-1.5">
                        {c.transient && (
                          <Badge tone="bg-sky-50 text-sky-800 ring-1 ring-inset ring-sky-600/20" size="sm">
                            приезжает рейсами
                          </Badge>
                        )}
                        {c.works_in_place && (
                          <Badge tone="bg-violet-50 text-violet-800 ring-1 ring-inset ring-violet-600/20" size="sm">
                            работает на месте
                          </Badge>
                        )}
                        {!c.transient && !c.works_in_place && <span className="text-muted">по сессиям</span>}
                      </div>
                    </td>
                    <td className="max-w-xs px-3 py-3 text-xs text-muted">{c.prompts.join(", ") || "—"}</td>
                    <td className="max-w-xs px-5 py-3 text-xs text-muted">{c.aliases.join(", ") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </PageContainer>
  );
}
