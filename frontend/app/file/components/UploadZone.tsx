"use client";

import FileDropZone from "@sn/compounds/FileTools";
import { tr } from "../i18n";

interface Props {
  busy: boolean;
  onFiles: (files: File[]) => void;
}

/** Upload button plus drag and drop target. The shared client has no progress events, so only a busy state is shown. */
export default function UploadZone({ busy, onFiles }: Props) {
  return (
    <FileDropZone variant="bar" multiple inputId="work-upload" testId="dropzone" busy={busy} onFiles={onFiles} buttonLabel={busy ? tr("dang_tai_len") : tr("tai_tep_len")}>
      {tr("hoac_keo_tha_tep_vao_day")}
    </FileDropZone>
  );
}
