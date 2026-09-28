import { ru } from "@/shared/locale/ru";
import { ButtonLink } from "@/shared/ui/Button";
import { PageContainer } from "@/shared/ui/Page";
import { Empty } from "@/shared/ui/QueryState";

/** Неизвестный маршрут: SPA отдаётся на любой путь, поэтому объясняем, что произошло. */
export function NotFoundScreen() {
  return (
    <PageContainer>
      <Empty
        icon="search"
        title={ru.notFound.title}
        action={
          <ButtonLink to="/objects" variant="primary" icon="building">
            К списку объектов
          </ButtonLink>
        }
      >
        {ru.notFound.hint}
      </Empty>
    </PageContainer>
  );
}
