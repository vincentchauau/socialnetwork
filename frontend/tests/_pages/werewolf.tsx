import { AuthGate } from "@sn/compounds/AuthGate";
import WerewolfHome from "../../app/werewolf/components/WerewolfHome";
import { tr } from "../../app/werewolf/i18n";

/** The Werewolf, as the rooms of the chat (category `werewolf`) and the buttons of the game. */
export default function WerewolfPage() {
  return <AuthGate title={tr("ma_soi")}>{(user) => <WerewolfHome user={user} />}</AuthGate>;
}
