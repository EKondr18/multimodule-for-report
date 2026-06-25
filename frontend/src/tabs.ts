import { ComponentType } from "react";
import BaggageCommentsPage from "./pages/BaggageCommentsPage";
import BaggageNormPage from "./pages/BaggageNormPage";

export interface TabDefinition {
  id: string;
  label: string;
  Component: ComponentType;
}

// Каждый новый модуль/вкладка регистрируется здесь одной строкой.
export const TABS: TabDefinition[] = [
  { id: "baggage-norm", label: "Норматив выдачи багажа", Component: BaggageNormPage },
  { id: "baggage-comments", label: "Добавление комментариев по багажу", Component: BaggageCommentsPage },
];
