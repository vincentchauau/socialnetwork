import { AuthGate } from "@sn/compounds/AuthGate";
import FileLibrary from "../../app/file/FileLibrary";
import { tr } from "../../app/file/i18n";

export default function FilePage() {
  return (
    <AuthGate title={tr("tep")}>
      {() => (
        <main className="maxColumnContainer">
          <FileLibrary />
        </main>
      )}
    </AuthGate>
  );
}
