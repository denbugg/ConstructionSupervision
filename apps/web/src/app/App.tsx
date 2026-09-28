import { Navigate, Route, BrowserRouter as Router, Routes } from "react-router-dom";

import { Layout } from "@/app/Layout";
import { NotFoundScreen } from "@/app/NotFoundScreen";
import { ObjectLayout } from "@/app/ObjectLayout";
import { Providers } from "@/app/providers";
import { CamerasScreen } from "@/features/cameras/CamerasScreen";
import { DashboardScreen } from "@/features/dashboard/DashboardScreen";
import { DeviationsScreen } from "@/features/deviations/DeviationsScreen";
import { GanttScreen } from "@/features/gantt/GanttScreen";
import { ObjectsScreen } from "@/features/objects/ObjectsScreen";
import { ReportsScreen } from "@/features/reports/ReportsScreen";
import { RulesEditorScreen } from "@/features/rules-editor/RulesEditorScreen";
import { DeviationRulesScreen } from "@/features/settings/DeviationRulesScreen";
import { EquipmentClassesScreen } from "@/features/settings/EquipmentClassesScreen";
import { ObjectSettingsScreen } from "@/features/settings/ObjectSettingsScreen";
import { UploadScreen } from "@/features/upload/UploadScreen";
import { ZonesEditorScreen } from "@/features/zones-editor/ZonesEditorScreen";

/** Корень приложения: провайдеры и маршруты (apps/web/README.md, §3). */
export function App() {
  return (
    <Providers>
      <Router>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Navigate to="/objects" replace />} />
            <Route path="objects" element={<ObjectsScreen />} />
            <Route path="objects/:objectId" element={<ObjectLayout />}>
              <Route index element={<DashboardScreen />} />
              <Route path="deviations" element={<DeviationsScreen />} />
              <Route path="gantt" element={<GanttScreen />} />
              <Route path="cameras" element={<CamerasScreen />} />
              <Route path="upload" element={<UploadScreen />} />
              <Route path="reports" element={<ReportsScreen />} />
              <Route path="settings" element={<ObjectSettingsScreen />} />
              <Route path="settings/zones" element={<ZonesEditorScreen />} />
              <Route path="settings/rules" element={<RulesEditorScreen />} />
            </Route>
            <Route path="settings/deviation-rules" element={<DeviationRulesScreen />} />
            <Route path="settings/equipment" element={<EquipmentClassesScreen />} />
            <Route path="*" element={<NotFoundScreen />} />
          </Route>
        </Routes>
      </Router>
    </Providers>
  );
}
