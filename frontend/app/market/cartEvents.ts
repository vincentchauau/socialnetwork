/** The cart changed (a product put in, a number changed, the cart emptied or ordered): whoever shows how many things are in it asks again. */
const CART_CHANGED = "sn:cart-changed";

export function notifyCartChanged(): void {
  window.dispatchEvent(new Event(CART_CHANGED));
}

export function onCartChanged(listener: () => void): () => void {
  window.addEventListener(CART_CHANGED, listener);
  return () => window.removeEventListener(CART_CHANGED, listener);
}
