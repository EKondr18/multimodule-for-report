import { ComponentType } from "react";
import BaggageNormPage from "./pages/BaggageNormPage";

export interface TabDefinition {
  id: string;
  label: string;
  Component: ComponentType;
}

// Каждый новый модуль/вкладка регистрируется здесь одной строкой.
export const TABS: TabDefinition[] = [
  { id: "baggage-norm", label: "Норматив выдачи багажа", Component: BaggageNormPage },
];
