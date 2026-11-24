import Shop from "../../app/market/Shop";
import { Shell } from "../../app/market/shell";
import { tr } from "../../app/market/i18n";

export default function ShopPage() {
  return <Shell title={tr("market")}>{() => <Shop />}</Shell>;
}
