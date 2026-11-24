import { useParams, useRouter } from "next/navigation";

import { AuthGate } from "@sn/compounds/AuthGate";
import RoomView from "../../app/werewolf/components/RoomView";
import WerewolfColumn from "../../app/werewolf/components/WerewolfColumn";
import { tr } from "../../app/werewolf/i18n";

export default function RoomPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const code = String(params.id ?? "").toUpperCase();
  return <AuthGate title={tr("ma_soi")}>{() => (
        <WerewolfColumn>
          <RoomView code={code} onExit={() => router.push("/werewolf")} />
        </WerewolfColumn>
      )}</AuthGate>;
}
