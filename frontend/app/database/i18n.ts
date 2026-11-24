import { registerScoped } from "@sn/lib/i18n";

import bundles from "./locales.json";

export const tr = registerScoped("database", bundles);
