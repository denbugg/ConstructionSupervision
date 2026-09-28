import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";

import { Sidebar } from "@/app/Sidebar";
import { ru } from "@/shared/locale/ru";
import { IconButton } from "@/shared/ui/Button";

/** Общая рамка всех экранов: боковая навигация и место под содержимое. */
export function Layout() {
  const [navOpen, setNavOpen] = useState(false);
  const { pathname } = useLocation();

  // Переход по ссылке закрывает выдвинутую навигацию на узком экране.
  useEffect(() => setNavOpen(false), [pathname]);

  return (
    <div className="min-h-screen lg:pl-64">
      <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />
      <div className="sticky top-0 z-30 flex h-14 items-center gap-2 bg-ink px-2 text-white lg:hidden">
        <IconButton icon="menu" label="Меню" onClick={() => setNavOpen(true)} className="!text-white hover:!bg-white/10" />
        <span className="font-semibold">{ru.app.title}</span>
      </div>
      <main className="min-w-0">
        <Outlet />
      </main>
    </div>
  );
}
