import { api } from "@/lib/api";
import { isIOS, isStandalone } from "@/lib/pwa";

const toUint8 = (base64) => {
  const padded = (base64 + "=".repeat((4 - (base64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
};

export const pushSupported = () =>
  typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

export const needsInstallFirst = () => isIOS() && !isStandalone();

export async function pushStatus() {
  if (!pushSupported()) return { supported: false, on: false, permission: "unsupported" };
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  return { supported: true, on: !!sub, permission: Notification.permission };
}

export async function enablePush() {
  if (!pushSupported()) throw new Error("This browser can't show push alerts.");
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Alerts are blocked. Allow notifications for Buddilio in your browser settings.");
  const { data } = await api.get("/push/config");
  if (!data.enabled || !data.public_key) throw new Error("Push alerts are not configured on the server yet.");
  const reg = await navigator.serviceWorker.ready;
  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: toUint8(data.public_key) });
  }
  await api.post("/push/subscribe", sub.toJSON());
  return true;
}

export async function disablePush() {
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  if (sub) {
    await api.post("/push/unsubscribe", { endpoint: sub.endpoint }).catch(() => {});
    await sub.unsubscribe();
  }
  return true;
}
