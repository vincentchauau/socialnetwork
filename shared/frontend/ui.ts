// Shared UI kit: generic building blocks only, styled with theme.css tokens. No app business logic.
//
// elements/   components that use no other component of the kit
// compounds/  components built from elements
//
// ThemePicker is not exported here: apps import it by path (`@sn/compounds/SiteSettings`).

export { default as Alert, type AlertProps, type AlertTone } from "./elements/Alert";
export { AUTH_GATE_LABELS_VI, default as AuthGate, type AuthGateLabels, type AuthGateProps } from "./compounds/AuthGate";
export { default as Button, type ButtonProps, type ButtonSize, type ButtonVariant, type ButtonEffect, type ButtonStatus } from "./elements/Button";
export { default as Card, type CardProps } from "./elements/Card";
export { default as CheckBox, type CheckBoxProps } from "./elements/CheckBox";
export { default as ConfirmModal, type ConfirmModalProps } from "./compounds/Dialogs";
export { default as FileDropZone, type FileDropZoneProps } from "./compounds/FileTools";
export { default as LabelTextBox, type LabelTextBoxProps } from "./compounds/LabelTextBox";
export { default as Icon, ICON_NAMES, type IconProps } from "./elements/Icon";
export { LanguageSwitcher, type LanguageSwitcherProps } from "./compounds/SiteSettings";
export { NumberBox, type NumberBoxProps } from "./compounds/LabelTextBox";
export { default as SchemaForm, type FieldKind, type FieldSpec, type FormValues, type SchemaFormProps } from "./compounds/SchemaForm";
export { default as Select, type SelectProps } from "./elements/Select";
export { FacetGridView, type FacetGridViewProps } from "./compounds/SplitPanel";
export { default as FacetView, type Facet, type FacetViewProps } from "./compounds/FacetView";
export { GridView } from "./compounds/GalleryView";
export { default as SplitPanel, type SplitPanelProps, type SplitPane } from "./compounds/SplitPanel";
export { TabPanel, type TabPanelProps } from "./compounds/SplitPanel";
export { TagBox, type TagBoxProps } from "./compounds/InputBox";
export { default as TextBox, type TextBoxProps } from "./elements/TextBox";
export { default as TreeView, type TreeNode, type TreeViewProps } from "./compounds/TreeView";

// not components: locale context and hooks
export { LOCALE_STORAGE_KEY, LocaleProvider, translate, useLocale, useTranslation, type Bundle } from "./lib/i18n";
export { ConfirmHost, confirmDialog } from "./compounds/Dialogs";

export { usePagedList, type Page, type PagedList } from "./lib/hooks";
