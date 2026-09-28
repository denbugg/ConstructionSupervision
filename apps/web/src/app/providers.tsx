import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { ApiError } from "@/shared/api/client";
import { ConfirmProvider } from "@/shared/ui/Modal";
import { ToastProvider } from "@/shared/ui/Toast";

/**
 * Серверное состояние живёт только в TanStack Query: кэш, инвалидация
 * и повторы — его работа, а не компонентов (apps/web/README.md, §5).
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      // 4xx повторять бессмысленно: ответ не изменится, а пользователь ждёт.
      retry: (failureCount, error) =>
        !(error instanceof ApiError && error.status < 500) && failureCount < 2,
    },
  },
});

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <ConfirmProvider>{children}</ConfirmProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}
