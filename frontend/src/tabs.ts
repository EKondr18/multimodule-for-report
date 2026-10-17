import { ComponentType, lazy } from "react";
import BaggageCommentsPage from "./pages/BaggageCommentsPage";
import BaggageNormPage from "./pages/BaggageNormPage";
import KpiPage from "./pages/KpiPage";
import QualityReportPage from "./pages/QualityReportPage";

// Ленивая загрузка: TechDedupPage тянет за собой xlsx + fflate (крупная
// часть бандла), которые нужны только тому, кто реально открыл эту
// вкладку — незачем грузить их в основной бандл на старте приложения.
const TechDedupPage = lazy(() => import("./pages/TechDedupPage"));

export interface TabDefinition {
  id: string;
  label: string;
  Component: ComponentType;
}

// Каждый новый модуль/вкладка регистрируется здесь одной строкой.
export const TABS: TabDefinition[] = [
  { id: "baggage-norm", label: "Норматив выдачи багажа", Component: BaggageNormPage },
  { id: "baggage-comments", label: "Добавление комментариев по багажу", Component: BaggageCommentsPage },
  { id: "quality-report", label: "Отчёт по качеству", Component: QualityReportPage },
  { id: "kpi", label: "KPI", Component: KpiPage },
  { id: "tech-dedup", label: "Удаление дубликатов по обслуживанию техники", Component: TechDedupPage },
];
