import { AuthGate } from "@sn/compounds/AuthGate";
import HistoryView from "../../app/werewolf/components/HistoryView";
import WerewolfColumn from "../../app/werewolf/components/WerewolfColumn";
import { tr } from "../../app/werewolf/i18n";

export default function HistoryPage() {
  return <AuthGate title={tr("lich_su_van_choi_2")}>{() => (
        <WerewolfColumn>
          <HistoryView />
        </WerewolfColumn>
      )}</AuthGate>;
}
