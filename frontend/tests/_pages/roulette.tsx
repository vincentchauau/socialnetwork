import AuthGate from "@sn/compounds/AuthGate";
import RouletteGame from "../../app/roulette/RouletteGame";
import { tr } from "../../app/roulette/i18n";

export default function RoulettePage() {
  return (
    <AuthGate title={tr("roulette")} heading>
      {() => <RouletteGame />}
    </AuthGate>
  );
}
